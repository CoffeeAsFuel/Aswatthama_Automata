import sys
import os
import uuid
import queue
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from medhavin_agent import run_medhavin

# ─────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────

WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

app = FastAPI(title="Medhavin AI Backend", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Text-to-Speech  (pyttsx3) — dedicated thread
# ─────────────────────────────────────────────

_tts_queue: queue.Queue = queue.Queue()

def _tts_worker():
    try:
        import pyttsx3
        engine = pyttsx3.init()
        while True:
            text = _tts_queue.get()
            if text is None:
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print(f"[TTS] Error: {e}")
            finally:
                _tts_queue.task_done()
    except Exception as e:
        print(f"[TTS] pyttsx3 unavailable: {e} — voice output disabled.")

_tts_thread = threading.Thread(target=_tts_worker, daemon=True, name="tts-worker")
_tts_thread.start()

def speak(text: str):
    if text and text.strip():
        _tts_queue.put(text.strip()[:500])

# ─────────────────────────────────────────────
# Whisper — lazy loaded on first use
# ─────────────────────────────────────────────

_whisper_model = None

def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        print("[Medhavin] Loading Whisper model (first request, ~10s)...")
        _whisper_model = whisper.load_model("small")
        print("[Medhavin] Whisper ready.")
    return _whisper_model


def transcribe_wav_numpy(wav_path: str) -> str:
    """
    FIX: Transcribe a WAV file by loading it as a numpy array and passing it
    directly to Whisper. This completely bypasses Whisper's internal ffmpeg
    call, which causes [WinError 2] on Windows when ffmpeg is not installed.

    Whisper's transcribe() accepts either a file path OR a float32 numpy
    array at 16 kHz. We use scipy to load the WAV (which needs no ffmpeg),
    convert it to float32, and hand it straight to Whisper.
    """
    import numpy as np
    from scipy.io.wavfile import read as wav_read

    sample_rate, audio_data = wav_read(wav_path)

    # Convert to float32 in [-1.0, 1.0] range as Whisper expects
    if audio_data.dtype == np.int16:
        audio_float = audio_data.astype(np.float32) / 32768.0
    elif audio_data.dtype == np.int32:
        audio_float = audio_data.astype(np.float32) / 2147483648.0
    else:
        audio_float = audio_data.astype(np.float32)

    # If stereo, average to mono
    if audio_float.ndim == 2:
        audio_float = audio_float.mean(axis=1)

    # Whisper always expects 16 kHz — resample if needed
    if sample_rate != 16000:
        try:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(16000, sample_rate)
            audio_float = resample_poly(audio_float, 16000 // g, sample_rate // g)
        except Exception:
            pass  # Best effort — Whisper may still handle it

    model = get_whisper()
    result = model.transcribe(audio_float, fp16=False)
    return (result.get("text") or "").strip()

# ─────────────────────────────────────────────
# Recording state  (one session at a time)
# ─────────────────────────────────────────────

_recording_lock  = threading.Lock()
_is_recording    = False

# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class PromptRequest(BaseModel):
    prompt: str

class RecordRequest(BaseModel):
    duration: int = 7   # seconds to record (default 7)

# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "Medhavin backend running ✅", "version": "3.0"}


@app.post("/ask")
def ask(request: PromptRequest):
    """Accept a text prompt → run Medhavin agent → speak reply → return JSON."""
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    try:
        result     = run_medhavin(request.prompt.strip())
        reply_text = result.get("output") or result.get("message") or ""
        speak(reply_text)
        return {"status": "success", "data": result}
    except EnvironmentError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────
# /record  — Records from the SERVER machine's
# microphone using sounddevice.
#
# FIX: Whisper transcription now uses numpy array
# (not file path) to avoid [WinError 2] caused by
# missing ffmpeg on Windows.
# ─────────────────────────────────────────────

@app.post("/record")
def record_and_process(request: RecordRequest):
    """
    Record audio directly from the server machine's microphone,
    transcribe with Whisper (no ffmpeg required), run Medhavin agent.
    """
    global _is_recording

    # Prevent overlapping recordings
    if not _recording_lock.acquire(blocking=False):
        return {"status": "error", "message": "Already recording. Please wait."}

    tmp_path = os.path.join(
        os.path.dirname(__file__),
        f"rec_{uuid.uuid4().hex}.wav"
    )

    try:
        # ── Import sounddevice + scipy ──────────────────────────────
        try:
            import sounddevice as sd
            from scipy.io.wavfile import write as wav_write
        except ImportError as ie:
            return {
                "status": "error",
                "message": (
                    f"Missing library: {ie}\n"
                    "Run: pip install sounddevice scipy"
                )
            }

        sample_rate = 16000   # Whisper expects 16 kHz
        duration    = max(1, min(request.duration, 30))  # clamp 1–30s

        print(f"[Medhavin] 🎙️  Recording {duration}s from server microphone…")
        _is_recording = True

        try:
            recording = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="int16"
            )
            sd.wait()   # blocks until recording finishes
        except Exception as rec_err:
            _is_recording = False
            return {
                "status": "error",
                "message": (
                    f"Microphone recording failed: {rec_err}\n"
                    "Make sure a microphone is connected and not in use by another app."
                )
            }

        _is_recording = False
        print(f"[Medhavin] Recording complete, saving to {tmp_path}")
        wav_write(tmp_path, sample_rate, recording)

        # ── Whisper transcription (numpy path — no ffmpeg needed) ───
        print("[Medhavin] Transcribing with Whisper (numpy mode)…")
        try:
            transcript = transcribe_wav_numpy(tmp_path)
        except Exception as t_err:
            return {
                "status": "error",
                "message": (
                    f"Transcription failed: {t_err}\n"
                    "Make sure whisper is installed: pip install openai-whisper"
                )
            }

        print(f"[Medhavin] Transcript: {transcript!r}")

        if not transcript:
            return {"status": "error", "message": "No speech detected. Please speak clearly and try again."}

        # ── Agent ───────────────────────────────────────────────────
        agent_result = run_medhavin(transcript)
        reply_text   = agent_result.get("output") or agent_result.get("message") or ""
        speak(reply_text)

        return {
            "status":     "success",
            "transcript": transcript,
            "agent":      agent_result
        }

    except Exception as e:
        _is_recording = False
        print(f"[Medhavin] Unexpected record error: {e}")
        return {"status": "error", "message": str(e)}

    finally:
        _is_recording = False   # FIX: always reset flag, even on exception
        _recording_lock.release()
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.get("/record/status")
def record_status():
    """Check if a recording is currently in progress."""
    return {"recording": _is_recording}


# ─────────────────────────────────────────────
# /transcribe  — kept for compatibility
# Accepts an uploaded audio file (webm/wav)
# ─────────────────────────────────────────────

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Upload audio file → Whisper → Medhavin agent."""
    original_name = audio.filename or "audio.webm"
    suffix   = os.path.splitext(original_name)[1] or ".webm"
    tmp_path = os.path.join(
        os.path.dirname(__file__),
        f"tmp_{uuid.uuid4().hex}{suffix}"
    )
    try:
        contents = await audio.read()
        if len(contents) < 500:
            return {"status": "error", "message": "Audio file too small — please record longer."}

        with open(tmp_path, "wb") as f:
            f.write(contents)

        # Use numpy path for WAV files to avoid ffmpeg dependency
        if suffix.lower() == ".wav":
            try:
                transcript = transcribe_wav_numpy(tmp_path)
            except Exception as e:
                return {"status": "error", "message": f"Transcription failed: {e}"}
        else:
            # For non-WAV formats (webm, mp4, etc.) ffmpeg IS required.
            # If ffmpeg is not installed, this will fail with a clear message.
            try:
                model         = get_whisper()
                transcription = model.transcribe(tmp_path)
                transcript    = (transcription.get("text") or "").strip()
            except Exception as e:
                if "WinError 2" in str(e) or "ffmpeg" in str(e).lower():
                    return {
                        "status": "error",
                        "message": (
                            "ffmpeg is required to process non-WAV audio files.\n"
                            "Install ffmpeg: https://ffmpeg.org/download.html\n"
                            "Or use the /record endpoint instead (WAV, no ffmpeg needed)."
                        )
                    }
                return {"status": "error", "message": str(e)}

        if not transcript:
            return {"status": "error", "message": "No speech detected in audio."}

        agent_result = run_medhavin(transcript)
        reply_text   = agent_result.get("output") or agent_result.get("message") or ""
        speak(reply_text)

        return {"status": "success", "transcript": transcript, "agent": agent_result}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
