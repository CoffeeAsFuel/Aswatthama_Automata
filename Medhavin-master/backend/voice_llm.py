import whisper
import sounddevice as sd
from scipy.io.wavfile import write
import ollama
import subprocess
import re

# Record audio
fs = 16000
seconds = 10

print("Speak now...")
recording = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
sd.wait()
write("input.wav", fs, recording)

# Whisper
model = whisper.load_model("base")
result = model.transcribe("input.wav")
user_text = result["text"]

print("You said:", user_text)

# Send to LLM
response = ollama.chat(
    model="tinyllama",
    messages=[{"role": "user", "content": user_text}]
)

assistant_text = response["message"]["content"]
print("\nAssistant:\n", assistant_text)

# ---- AGENT PART ----
# Extract Python code block
code_match = re.search(r"```python(.*?)```", assistant_text, re.DOTALL)

if code_match:
    code = code_match.group(1)

    with open("generated_code.py", "w") as f:
        f.write(code)

    print("\nExecuting generated code...\n")
    subprocess.run(["python", "generated_code.py"])
else:
    print("\nNo executable Python code found.")
