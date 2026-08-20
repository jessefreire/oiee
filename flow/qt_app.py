"""Aplicação Windows do Oiee: uma única UI Qt, sem Tk/CTk."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
import time

import numpy as np
import sounddevice as sd
import keyboard
from PySide6.QtCore import QObject, QTimer, Qt, Signal, QRectF
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QMenu,
                               QHBoxLayout, QLabel, QPushButton, QSystemTrayIcon,
                               QVBoxLayout, QWidget, QPlainTextEdit, QMessageBox, QCheckBox)

from .config import LANGUAGES, MODELS, OUTPUT_MODES, Config
from .engine import DictationEngine
from .errors import log_path


class UiBridge(QObject):
    recording = Signal(object)
    transcribing = Signal()
    error = Signal(str)
    idle = Signal()

    def show_recording(self, recorder): self.recording.emit(recorder)
    def show_transcribing(self): self.transcribing.emit()
    def show_error(self, message): self.error.emit(message)
    def hide(self): self.idle.emit()


def tray_icon() -> QIcon:
    """Ícone visível na bandeja, sem depender de arquivo externo no .exe."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#0a84ff"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(17, 7, 30, 35, 15, 15)
    painter.drawRoundedRect(13, 39, 38, 7, 3, 3)
    painter.drawRoundedRect(29, 35, 6, 19, 3, 3)
    painter.end()
    return QIcon(pixmap)


class CtrlWinHotkey(QObject):
    """Toque duplo alterna; segurar Ctrl+Win funciona como push-to-talk."""
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, window: QWidget):
        super().__init__()
        self.window = window
        self.registered = False
        self._pressed = set()
        self._chord_down = False
        self._active = False
        self._holding = False
        self._last_tap = 0.0
        self._hold_timer = None

    def register(self) -> bool:
        try:
            # O pacote keyboard inicia o hook em threads preguiçosamente. Ao
            # aquecê-lo antes de registrar o callback, a primeira combinação
            # logo após abrir o Oiee não se perde.
            keyboard._listener.start_if_necessary()  # type: ignore[attr-defined]
            time.sleep(0.15)
            self._hook = keyboard.hook(self._on_event, suppress=False)
            self.registered = True
        except Exception:
            self.registered = False
        return self.registered

    def close(self) -> None:
        if self.registered:
            keyboard.unhook(self._hook)
            self.registered = False

    def _on_event(self, event) -> None:
        name = "windows" if event.name in {"windows", "left windows", "right windows", "win"} else event.name
        if name not in {"ctrl", "windows", "left ctrl", "right ctrl"}:
            return
        if event.event_type == "down":
            if name in {"left ctrl", "right ctrl"}: name = "ctrl"
            self._pressed.add(name)
            if self._chord_down or not {"ctrl", "windows"}.issubset(self._pressed):
                return
            self._chord_down = True
            self._on_chord_down()
        else:
            if name in {"left ctrl", "right ctrl"}: name = "ctrl"
            self._pressed.discard(name)
            if self._chord_down and name in {"ctrl", "windows"}:
                self._chord_down = False
                self._on_chord_up()

    def _on_chord_down(self) -> None:
        if self._active:
            self._active = False
            self.stop_requested.emit()
            return
        # Um toque curto pode fazer parte do gesto de dois toques. Só inicia
        # o push-to-talk se o acorde permanecer pressionado por 250 ms.
        self._hold_timer = threading.Timer(0.25, self._start_hold_if_still_down)
        self._hold_timer.daemon = True
        self._hold_timer.start()

    def _start_hold_if_still_down(self) -> None:
        if self._chord_down and not self._active:
            self._holding = True
            self.start_requested.emit()

    def _on_chord_up(self) -> None:
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None
        if self._holding:
            self._holding = False
            self.stop_requested.emit()
            return
        if self._active:
            return
        now = time.monotonic()
        if now - self._last_tap <= 0.35:
            self._last_tap = 0.0
            self._active = True
            self.start_requested.emit()
        else:
            self._last_tap = now



class Overlay(QWidget):
    toggled = Signal()
    settings_requested = Signal()

    def __init__(self, cfg: Config):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.cfg, self.state, self.recorder, self.started = cfg, "idle", None, 0.0
        self.drag_offset = None
        self.dragged = False
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(76, 48)
        self.move(cfg.floating_x or 900, cfg.floating_y or 700)
        self.timer = QTimer(self); self.timer.timeout.connect(self.update); self.timer.start(60)
        if cfg.floating: self.show()

    def set_state(self, state: str, recorder=None, message=""):
        self.state, self.recorder = state, recorder
        self.message = message
        if state == "recording": self.started = time.monotonic(); self.setFixedSize(270, 54)
        elif state == "transcribing": self.setFixedSize(180, 42)
        elif state == "error": self.setFixedSize(260, 52)
        else: self.setFixedSize(76, 48)
        self.show(); self.raise_(); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        color = QColor("#172033") if self.state == "idle" else QColor("#202a3d")
        p.setBrush(color); p.setPen(QColor("#3b82f6")); p.drawRoundedRect(rect, 22, 22)
        p.setPen(QColor("#e8f0ff"))
        if self.state == "idle":
            p.setFont(self.font()); p.drawText(rect, Qt.AlignCenter, "🎙")
        elif self.state == "recording":
            elapsed = int(time.monotonic() - self.started); p.drawText(14, 33, f"● Gravando  {elapsed:02d}s")
            audio = self.recorder.recent(.35) if self.recorder is not None else np.zeros(0, dtype=np.float32)
            self._draw_wave_bars(p, audio)
            p.drawText(210, 33, "Parar")
        elif self.state == "transcribing": p.drawText(rect, Qt.AlignCenter, "Transcrevendo…")
        else: p.drawText(rect, Qt.AlignCenter, f"Erro: {self.message[:28]}")

    def _draw_wave_bars(self, painter: QPainter, audio: np.ndarray) -> None:
        """Onda compacta com barras arredondadas, inspirada em apps de ditado."""
        x0, y_mid, width, count = 108, 27, 92, 24
        gap, bar_w, min_h, max_h = 2.0, 2.0, 4.0, 25.0
        levels = np.zeros(count, dtype=np.float32)
        audio = np.asarray(audio).reshape(-1)
        if audio.size and float(np.max(np.abs(audio))) >= 0.003:
            chunks = np.array_split(audio, count)
            levels = np.array([np.sqrt(np.mean(chunk * chunk)) if chunk.size else 0 for chunk in chunks])
            reference = max(0.008, float(np.percentile(levels, 90)))
            levels = np.clip(levels / reference, 0, 1)
        painter.setPen(Qt.NoPen)
        for i, level in enumerate(levels):
            height = min_h + (max_h - min_h) * float(level)
            ratio = i / max(1, count - 1)
            # azul no início, ciano no final: vivo sem chamar mais atenção que o texto.
            color = QColor.fromRgbF(0.18 + 0.05 * ratio, 0.48 + 0.30 * ratio, 1.0, 0.38 + 0.62 * float(level))
            painter.setBrush(color)
            x = x0 + i * (bar_w + gap)
            painter.drawRoundedRect(QRectF(x, y_mid - height / 2, bar_w, height), 1.0, 1.0)

    def mousePressEvent(self, event):
        self.drag_offset = event.globalPosition().toPoint() - self.pos()
        self.dragged = False
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            target = event.globalPosition().toPoint() - self.drag_offset
            if (target - self.pos()).manhattanLength() > 3:
                self.dragged = True
            self.move(target)
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.settings_requested.emit()
            return
        if not self.dragged:
            self.toggled.emit()
        self.cfg.floating_x, self.cfg.floating_y = self.x(), self.y(); self.cfg.save()


class Settings(QDialog):
    def __init__(self, cfg: Config, controller):
        super().__init__(); self.cfg, self.controller = cfg, controller; self.setWindowTitle("Oiee — Configurações")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.ApplicationModal)
        layout = QVBoxLayout(self); form = QFormLayout(); layout.addLayout(form)
        self.model = QComboBox(); self.model.addItems(MODELS); self.model.setCurrentText(cfg.model); form.addRow("Modelo", self.model)
        self.language = QComboBox(); self.language.addItems(LANGUAGES); self.language.setCurrentText(cfg.language); form.addRow("Idioma", self.language)
        self.output = QComboBox(); [self.output.addItem(label, key) for key, label in OUTPUT_MODES.items()]; self.output.setCurrentIndex(self.output.findData(cfg.output_mode)); form.addRow("Inserção", self.output)
        self.beam = QComboBox(); self.beam.addItem("Rápido (1)", 1); self.beam.addItem("Equilibrado (3)", 3); self.beam.addItem("Mais preciso (5)", 5); self.beam.setCurrentIndex(max(0, self.beam.findData(cfg.beam_size))); form.addRow("Qualidade", self.beam)
        self.device = QComboBox(); self.device.addItem("Padrão do sistema", None)
        for i,d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0: self.device.addItem(d["name"], i)
        self.device.setCurrentIndex(max(0, self.device.findData(cfg.device))); form.addRow("Microfone", self.device)
        self.vocabulary = QPlainTextEdit(cfg.vocabulary); self.vocabulary.setPlaceholderText("Ex.: nomes, siglas, marcas e clientes…"); self.vocabulary.setFixedHeight(70)
        form.addRow("Vocabulário pessoal", self.vocabulary)
        self.auto_gain = QCheckBox("Ajustar automaticamente voz baixa"); self.auto_gain.setChecked(cfg.auto_gain); layout.addWidget(self.auto_gain)
        info = QLabel("Atalho: toque Ctrl+Win duas vezes (toggle) ou segure para falar"); layout.addWidget(info)
        test = QPushButton("Testar microfone"); test.clicked.connect(controller.test_microphone); layout.addWidget(test)
        reset = QPushButton("Redefinir posição do botão"); reset.clicked.connect(controller.reset_overlay); layout.addWidget(reset)
        diag = QPushButton("Abrir diagnóstico"); diag.clicked.connect(controller.show_diagnostics); layout.addWidget(diag)
        save = QPushButton("Salvar"); save.clicked.connect(self.save); layout.addWidget(save)
    def save(self):
        self.cfg.model, self.cfg.language = self.model.currentText(), self.language.currentText(); self.cfg.output_mode = self.output.currentData(); self.cfg.device = self.device.currentData(); self.cfg.vocabulary = self.vocabulary.toPlainText().strip(); self.cfg.beam_size = self.beam.currentData(); self.cfg.auto_gain = self.auto_gain.isChecked(); self.cfg.save(); self.controller.reload(); self.accept()


class FlowApplication(QObject):
    def __init__(self, app: QApplication, cfg: Config):
        super().__init__(); self.app, self.cfg = app, cfg; self.bridge = UiBridge(); self.overlay = Overlay(cfg)
        # Não aceite a primeira interação antes do loop Qt e do hook global
        # estarem prontos. Isso eliminia o primeiro clique/atalho perdido.
        self.overlay.hide()
        self.engine = DictationEngine(cfg, self.bridge); self.bridge.recording.connect(lambda r: self.overlay.set_state("recording", r)); self.bridge.transcribing.connect(lambda: self.overlay.set_state("transcribing")); self.bridge.error.connect(lambda e: self.overlay.set_state("error", message=e)); self.bridge.idle.connect(lambda: self.overlay.set_state("idle"))
        self.overlay.settings_requested.connect(self.open_settings)
        self.hotkey = CtrlWinHotkey(self.overlay); self.hotkey.start_requested.connect(self.engine.start_recording); self.hotkey.stop_requested.connect(self.engine.stop_recording); self.overlay.toggled.connect(self.engine.toggle)
        self.tray = QSystemTrayIcon(tray_icon(), self.overlay); menu = QMenu(); menu.addAction(QAction("Configurações", self.tray, triggered=self.open_settings)); menu.addAction(QAction("Sair", self.tray, triggered=app.quit)); self.tray.setContextMenu(menu); self.tray.setToolTip("Oiee — Ctrl+Win: duplo toque ou segurar"); self.tray.show()
        if not self.hotkey.register(): self.overlay.set_state("error", message="Não foi possível registrar Ctrl + Win")
        import threading
        threading.Thread(target=self.engine.transcriber.load, daemon=True).start()
        QTimer.singleShot(350, self._show_ready)

    def _show_ready(self):
        if self.cfg.floating:
            self.overlay.set_state("idle")
    def open_settings(self):
        dialog = Settings(self.cfg, self)
        QTimer.singleShot(0, lambda: (dialog.raise_(), dialog.activateWindow()))
        dialog.exec()
    def reload(self): self.engine.reload()
    def reset_overlay(self): self.overlay.move(900, 700); self.cfg.floating_x, self.cfg.floating_y = 900, 700; self.cfg.save()
    def test_microphone(self):
        try:
            rate = 16000
            audio = sd.rec(int(rate * 0.6), samplerate=rate, channels=1, device=self.cfg.device, dtype="float32")
            sd.wait()
            level = float(np.sqrt(np.mean(np.square(audio))))
            message = "Volume muito baixo — aproxime o microfone ou aumente o ganho do Windows." if level < 0.008 else "Microfone OK. Volume detectado: " + f"{level:.3f}"
            QMessageBox.information(None, "Teste de microfone", message)
        except Exception as exc:
            QMessageBox.warning(None, "Teste de microfone", str(exc))
    def show_diagnostics(self):
        device = "Padrão do sistema" if self.cfg.device is None else str(self.cfg.device)
        QMessageBox.information(
            None,
            "Oiee — Diagnóstico",
            "Aplicativo em execução.\n"
            f"Modelo: {self.cfg.model} ({self.engine.transcriber.status})\n"
            f"Idioma: {self.cfg.language}\n"
            f"Microfone: {device}\n"
            "Atalho: Ctrl + Win\n"
            f"Log: {log_path()}",
        )
    def close(self): self.hotkey.close(); self.tray.hide()
