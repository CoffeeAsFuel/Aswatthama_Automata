"""
voice_llm.py — Standalone CLI voice interface for Medhavin.

FIXED: The original file used `ollama` (tinyllama) + `sounddevice` which are
completely incompatible with the rest of the project (which uses Groq + Whisper).
This version is now consistent: it uses Whisper for STT and Groq (llama) for LLM,
and delegates to the same run_medhavin() agent as the server does.

Usage:
    export GROQ_API_KEY=gsk_xxxx
    python voice_llm.py
"""

import os
import sys
import tempfile

# ── Optional: sounddevice for microphone recording ──────────────────────────
try:
    import sounddevice as sd
    from scipy.io.wavfile import write as wav_write
    HAS_MIC = True
except ImportError:
    HAS_MIC = False
    print("[voice_llm] sounddevice/scipy not installed — mic recording disabled.")
    print("[voice_llm] Install with: pip install sounddevice scipy")

# ── Whisper ──────────────────────────────────────────────────────────────────
try:
    import whisper
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False
    print("[voice_llm] whisper not installed. Install with: pip install openai-whisper")

# ── Medhavin agent (same one the server uses) ─────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from medhavin_agent import run_medhavin

# ── Optional: TTS (pyttsx3) ──────────────────────────────────────────────────
try:
    import pyttsx3
    _tts_engine = pyttsx3.init()
    HAS_TTS = True
except Exception:
    _tts_engine = None
    HAS_TTS = False
    print("[voice_llm] pyttsx3 not available — TTS disabled.")

SAMPLE_RATE = 16000  # Hz — Whisper expects 16 kHz
RECORD_SECONDS = 10   # Max recording duration


def record_audio(seconds: int = RECORD_SECONDS) -> str:
    """Record from microphone and save to a temp WAV file. Returns file path."""
    if not HAS_MIC:
        raise RuntimeError("sounddevice not installed. Cannot record audio.")

    print(f"[voice_llm] 🎙️  Speak now… (recording for up to {seconds}s)")
    recording = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
    sd.wait()
    print("[voice_llm] ✅ Recording complete.")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav_write(tmp.name, SAMPLE_RATE, recording)
    return tmp.name


_whisper_model_cache = None

def transcribe_audio(audio_path: str) -> str:
    """Transcribe an audio file using Whisper. Returns transcript text."""
    if not HAS_WHISPER:
        raise RuntimeError("whisper not installed. Cannot transcribe.")

    # FIX: Cache the model so it loads only once per session (saves ~10s per call)
    global _whisper_model_cache
    if _whisper_model_cache is None:
        print("[voice_llm] 🔍 Loading Whisper model (first run only)…")
        _whisper_model_cache = whisper.load_model("base")
    print("[voice_llm] 🔍 Transcribing with Whisper…")
    result = _whisper_model_cache.transcribe(audio_path)
    transcript = (result.get("text") or "").strip()
    print(f"[voice_llm] You said: {transcript!r}")
    return transcript


def speak(text: str):
    """Speak text aloud via pyttsx3 (if available)."""
    if HAS_TTS and _tts_engine and text.strip():
        _tts_engine.say(text.strip()[:500])
        _tts_engine.runAndWait()


def main():
    """Interactive voice loop: record → transcribe → Medhavin agent → speak."""
    print("=" * 50)
    print("  Medhavin Voice CLI")
    print("  Say something — Ctrl+C to quit")
    print("=" * 50)

    if not HAS_MIC or not HAS_WHISPER:
        print("\n[voice_llm] ❌ Missing dependencies. Please install:")
        if not HAS_MIC:
            print("  pip install sounddevice scipy")
        if not HAS_WHISPER:
            print("  pip install openai-whisper")
        sys.exit(1)

    while True:
        try:
            input("\nPress Enter to start recording (Ctrl+C to quit)…")
        except KeyboardInterrupt:
            print("\n[voice_llm] Bye!")
            break

        audio_path = None
        try:
            audio_path = record_audio()
            transcript = transcribe_audio(audio_path)

            if not transcript:
                print("[voice_llm] ⚠️  No speech detected. Try again.")
                continue

            print(f"\n[voice_llm] 🤖 Sending to Medhavin: {transcript!r}")
            result = run_medhavin(transcript)

            # Extract reply from the same structure as the server
            reply = result.get("output") or result.get("message") or ""
            print(f"\n[Medhavin]\n{reply}")
            speak(reply)

        except Exception as e:
            print(f"[voice_llm] ❌ Error: {e}")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)


if __name__ == "__main__":
    main()
