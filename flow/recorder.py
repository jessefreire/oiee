"""Gravação de áudio do microfone usando sounddevice.

Grava enquanto a tecla estiver pressionada e devolve um array float32
mono. Se o dispositivo não aceitar 16 kHz, grava na taxa padrão dele e
re-amostra com interpolação linear (suficiente para fala).
"""
import threading

import numpy as np
import sounddevice as sd

TARGET_RATE = 16000


class Recorder:
    def __init__(self, device: int | None = None, rate: int = TARGET_RATE):
        self.device = device
        self.rate = rate
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        try:
            self._open(self.rate)
        except Exception:
            # dispositivo não suporta a taxa pedida: usa a padrão e resample depois
            info = sd.query_devices(self.device, "input")
            self._open(int(info["default_samplerate"]))

    def _open(self, rate: int) -> None:
        self.rate = rate
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=rate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        with self._lock:
            # sounddevice entrega (frames, 1) com channels=1 — achata para 1D
            # (formato que o Whisper e a forma de onda esperam)
            self._frames.append(indata.copy().reshape(-1))

    def recent(self, duration: float = 0.5) -> np.ndarray:
        """Devolve os últimos ~`duration` segundos capturados (para a onda ao vivo).

        Barato: só concatena os blocos mais recentes do buffer.
        """
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            target = max(1, int(self.rate * duration))
            out = []
            total = 0
            for frame in reversed(self._frames):
                out.append(frame)
                total += frame.size
                if total >= target:
                    break
            return np.concatenate(out[::-1]).reshape(-1)

    def stop(self) -> np.ndarray:
        """Para a gravação e devolve o áudio capturado (float32 mono)."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        with self._lock:
            audio = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype=np.float32)
            self._frames = []
        return audio.reshape(-1)

    @staticmethod
    def resample(audio: np.ndarray, orig_rate: int, target: int = TARGET_RATE) -> np.ndarray:
        if orig_rate == target or audio.size == 0:
            return audio
        n = int(round(audio.size * target / orig_rate))
        x = np.linspace(0, audio.size - 1, n) if n > 1 else np.array([0.0])
        return np.interp(x, np.arange(audio.size), audio).astype(np.float32)

    @staticmethod
    def auto_gain(audio: np.ndarray, target_peak: float = 0.18, max_gain: float = 8.0) -> np.ndarray:
        """Aumenta voz baixa sem amplificar silêncio ou estourar o sinal."""
        if audio.size == 0:
            return audio
        peak = float(np.percentile(np.abs(audio), 95))
        if peak < 0.008:  # silêncio/ruído: não transforma em chiado alto
            return audio
        gain = min(max_gain, target_peak / peak)
        return np.clip(audio * gain, -1.0, 1.0).astype(np.float32)
