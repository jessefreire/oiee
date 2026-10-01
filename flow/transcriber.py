"""Transcrição local com faster-whisper.

O modelo é carregado de forma preguiçosa após a primeira gravação.
Tudo roda em CPU com quantização int8 — no Windows, sem GPU é o caminho mais
rápido e leve.
"""
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

STATUS_IDLE = "modelo não carregado"
STATUS_LOADING = "carregando modelo…"
STATUS_READY = "modelo pronto"


class Transcriber:
    def __init__(self, model_name: str = "small", language: str = "pt", vocabulary: str = "", beam_size: int = 3):
        self.model_name = model_name
        self.language = language
        self.vocabulary = vocabulary.strip()
        self.beam_size = max(1, min(5, int(beam_size)))
        self.status = STATUS_IDLE
        self._model: Any | None = None
        self._lock = threading.Lock()

    def load(self) -> "WhisperModel":
        with self._lock:
            if self._model is None:
                self.status = STATUS_LOADING
                # Import pesado adiado: a interface e o atalho global ficam
                # prontos antes de carregar CTranslate2/Faster Whisper.
                from faster_whisper import WhisperModel
                # Na primeira execução baixa o modelo do Hugging Face e cacheia.
                # Falhas transitórias (download/materialização do cache) são
                # comuns: tenta até 3 vezes antes de desistir.
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                        time.sleep(2 * (attempt + 1))
                if self._model is None:
                    self.status = STATUS_IDLE
                    raise last_error  # type: ignore[misc]
                self.status = STATUS_READY
        return self._model

    def transcribe(self, audio) -> str:
        """Transcreve um array float32 mono a 16 kHz e devolve o texto com pontuação.

        O vocabulário do usuário entra como ``hotwords`` (prioridade de
        decoding). Nada de ``initial_prompt``: no faster-whisper o prompt é
        tratado como prefixo "já falado" e, quando presente, anula os
        ``hotwords`` — foi por isso que os termos do vocabulário chegavam
        errados. Tudo roda local; nada sai da máquina.
        """
        model = self.load()
        lang = None if self.language == "auto" else self.language
        segments, _ = model.transcribe(
            audio,
            language=lang,
            beam_size=self.beam_size,
            vad_filter=True,
            without_timestamps=True,
            hotwords=self.vocabulary or None,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def matches(self, model_name: str, language: str, vocabulary: str = "", beam_size: int = 3) -> bool:
        return (self.model_name == model_name and self.language == language
                and self.vocabulary == vocabulary.strip() and self.beam_size == int(beam_size))
