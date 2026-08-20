"""Smoke test: carrega o Whisper e transcreve o wav de exemplo."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from faster_whisper import WhisperModel  # noqa: E402

wav = os.path.join(os.environ.get("TEMP", "/tmp"), "flow_test.wav")
if not os.path.exists(wav):
    sys.exit("wav de teste não encontrado: " + wav)

t0 = time.time()
model = WhisperModel("tiny", device="cpu", compute_type="int8")
print(f"modelo carregado em {time.time() - t0:.1f}s")

t0 = time.time()
segments, info = model.transcribe(wav, language="pt", beam_size=1)
text = " ".join(s.text.strip() for s in segments)
print(f"transcrição em {time.time() - t0:.1f}s")
print("LANG:", info.language, "| prob:", round(info.language_probability, 2))
print("TEXTO:", repr(text))
