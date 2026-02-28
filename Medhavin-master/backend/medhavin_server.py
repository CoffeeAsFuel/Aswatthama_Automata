import sys
import os

# ✅ FIX: Backend folder ko sys.path mein add karo
# Isse chahe kahi se bhi uvicorn run karo, import hamesha kaam karega
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from medhavin_agent import run_medhavin  # ✅ Ab yeh hamesha resolve hoga
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import whisper
import uuid
import pyttsx3

# -------------------------
# Configuration
# -------------------------

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
os.makedirs(BASE_DIR, exist_ok=True)

app = FastAPI()

# ✅ Sirf EK baar engine init karo — duplicate remove kar diya
engine = pyttsx3.init()

def speak(text):
    if not text:
        return
    engine.say(text)
    engine.runAndWait()

whisper_model = whisper.load_model("small")
SAMPLE_RATE = 16000

def record_until_silence():
    silence_threshold = 500
    silence_limit_seconds = 3
    chunk_duration = 0.5

    frames = []
    silent_chunks = 0
    required_silent_chunks = int(silence_limit_seconds / chunk_duration)

    print("Listening...")

    while True:
        chunk = sd.rec(
            int(chunk_duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16"
        )
        sd.wait()
        frames.append(chunk)
        volume = np.abs(chunk).mean()

        if volume < silence_threshold:
            silent_chunks += 1
        else:
            silent_chunks = 0

        if silent_chunks >= required_silent_chunks:
            break

    print("Silence detected. Stopping.")
    return np.concatenate(frames)

# -------------------------
# Enable CORS
# -------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Request Schema
# -------------------------

class PromptRequest(BaseModel):
    prompt: str

# -------------------------
# Main Endpoint
# -------------------------

@app.post("/ask")
def ask(request: PromptRequest):
    try:
        result = run_medhavin(request.prompt)
        if "output" in result:
            speak(result["output"])
        elif "message" in result:
            speak(result["message"])

        return {
            "status": "success",
            "data": result
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

# -------------------------
# Record Endpoint
# -------------------------

@app.post("/record")
def record_and_process():
    try:
        recording = record_until_silence()

        filename = f"temp_{uuid.uuid4().hex}.wav"
        filepath = os.path.join(os.path.dirname(__file__), filename)

        write(filepath, SAMPLE_RATE, recording)

        print("Transcribing...")
        result = whisper_model.transcribe(filepath)
        transcript = result["text"]
        os.remove(filepath)

        print("Transcript:", transcript)

        agent_result = run_medhavin(transcript)
        if isinstance(agent_result, dict):
            if "output" in agent_result:
                speak(agent_result["output"])
            elif "message" in agent_result:
                speak(agent_result["message"])
        elif isinstance(agent_result, str):
            speak(agent_result)

        return {
            "status": "success",
            "transcript": transcript,
            "agent": agent_result
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

# -------------------------
# Health Check
# -------------------------

@app.get("/")
def root():
    return {"status": "Medhavin backend running"}