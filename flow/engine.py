"""Motor de ditado: segura a tecla, fala, solta — o texto aparece no app focado.

O hook do teclado roda na thread da biblioteca `keyboard`; o ditado em si roda
em uma thread própria para não travar a escuta de teclas.
"""
import threading
import time

import keyboard

from . import typer
from .commands import parse_commands
from .config import Config
from .errors import log_exception
from .recorder import Recorder
from .transcriber import Transcriber

MIN_AUDIO_SECONDS = 0.3  # ignora toques acidentais sem fala
MAX_RECORDING_SECONDS = 300  # trava de segurança: para a gravação sozinha


class DictationEngine:
    def __init__(self, config: Config, overlay):
        self.cfg = config
        self.overlay = overlay
        self.transcriber = Transcriber(config.model, config.language, config.learned_vocabulary(), config.beam_size)
        self._recording = False
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pressed: set[str] = set()  # teclas da combinação atualmente pressionadas

    # ------------------------------------------------------------------ vida
    def start(self) -> None:
        keyboard.on_press(self._on_press, suppress=False)
        keyboard.on_release(self._on_release)
        # pré-carrega o modelo em background para a primeira fala ser rápida
        threading.Thread(target=self.transcriber.load, daemon=True).start()

    def reload(self) -> None:
        """Recarrega configuração (modelo/idioma) após salvar nas configurações."""
        vocabulary = self.cfg.learned_vocabulary()
        if not self.transcriber.matches(self.cfg.model, self.cfg.language, vocabulary, self.cfg.beam_size):
            self.transcriber = Transcriber(self.cfg.model, self.cfg.language, vocabulary, self.cfg.beam_size)
            threading.Thread(target=self.transcriber.load, daemon=True).start()

    # ------------------------------------------------------------------ hooks
    def _on_press(self, event) -> None:
        keys = self._chord_keys()
        try:
            if event.name not in keys:
                return
        except AttributeError:
            return
        # rastreia as teclas da combinação pelos próprios eventos (is_pressed
        # não enxerga a tecla recém-pressionada — bug real de timing)
        self._pressed.add(event.name)
        if self.cfg.hotkey_mode == "toggle":
            # um toque (combinação completa) inicia; o próximo para e processa
            if len(self._pressed) == len(keys):
                self.toggle()
        elif len(keys) == 1 or len(self._pressed) == len(keys):
            # hold: inicia quando a combinação está completa (ou tecla única)
            self._start()

    def _on_release(self, event) -> None:
        try:
            self._pressed.discard(event.name)
            if self.cfg.hotkey_mode == "toggle":
                return
            if event.name in self._chord_keys():
                self._stop.set()
        except AttributeError:
            pass

    def _chord_keys(self) -> list[str]:
        return [keyboard.normalize_name(k.strip()) for k in self.cfg.hotkey.split("+")]

    def _start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._recording = True
        self._stop.clear()
        threading.Thread(target=self._dictate, daemon=True).start()

    def toggle(self) -> None:
        """Alterna gravação (usado pelo botão flutuante e pelo modo alternar)."""
        with self._lock:
            if self._recording:
                self._stop.set()  # para e processa o que já foi falado
                return
            self._recording = True
        self._stop.clear()
        threading.Thread(target=self._dictate, daemon=True).start()

    def start_recording(self) -> None:
        """Inicia o ditado para um atalho de pressionar-e-segurar."""
        self._start()

    def stop_recording(self) -> None:
        """Encerra o ditado iniciado por um atalho de pressionar-e-segurar."""
        self._stop.set()

    # ------------------------------------------------------------------ ditado
    def _dictate(self) -> None:
        recorder = Recorder(device=self.cfg.device)
        text = ""
        failed = False
        try:
            recorder.start()
            self.overlay.show_recording(recorder)
            t0 = time.monotonic()
            while not self._stop.wait(0.05):
                if time.monotonic() - t0 > MAX_RECORDING_SECONDS:
                    break  # trava de segurança p/ modo alternar esquecido
            audio = recorder.stop()
            self.overlay.show_transcribing()
            if audio.size >= int(recorder.rate * MIN_AUDIO_SECONDS):
                if self.cfg.auto_gain:
                    audio = Recorder.auto_gain(audio)
                audio16 = Recorder.resample(audio, recorder.rate)
                text = self.transcriber.transcribe(audio16)
        except Exception as exc:  # noqa: BLE001 — mostra o erro e segue a vida
            failed = True
            log_exception("ditado")
            self.overlay.show_error(str(exc))
        finally:
            recorder.stop()
            if not failed:
                self.overlay.hide()

        if text:
            # No app Qt, a entrega vai para a thread de interface. O fallback
            # preserva o motor testável e o uso com overlays antigos.
            if hasattr(self.overlay, "show_result"):
                self.overlay.show_result(text)
            else:
                self._insert_text(text)

        with self._lock:
            self._recording = False

    def _insert_text(self, text: str) -> None:
        clean, actions = parse_commands(self.cfg.apply_corrections(text), self.cfg.language)
        if clean:
            typer.type_text(clean, self.cfg.output_mode)
        if actions:
            typer.apply_actions(actions)
