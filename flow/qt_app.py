"""Aplicação Windows do Oiee: uma única UI Qt, sem Tk/CTk."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
import time

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QTimer, Qt, Signal, QRectF
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QMenu,
                               QHBoxLayout, QLabel, QPushButton, QSystemTrayIcon,
                               QVBoxLayout, QWidget, QPlainTextEdit, QMessageBox, QCheckBox)

from .config import LANGUAGES, MODELS, OUTPUT_MODES, Config
from .commands import parse_commands
from .engine import DictationEngine
from .errors import log_path
from . import typer


class UiBridge(QObject):
    recording = Signal(object)
    transcribing = Signal()
    error = Signal(str)
    idle = Signal()
    result = Signal(str)

    def show_recording(self, recorder): self.recording.emit(recorder)
    def show_transcribing(self): self.transcribing.emit()
    def show_error(self, message): self.error.emit(message)
    def hide(self): self.idle.emit()
    def show_result(self, text): self.result.emit(text)


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
    """Atalho global Ctrl+Win sem depender do hook da biblioteca keyboard.

    ``GetAsyncKeyState`` consulta o estado físico global das teclas, inclusive
    quando o Oiee não tem foco. Isso evita o comportamento do listener em
    thread que só passava a receber o primeiro atalho depois de um clique.
    """
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, window: QWidget):
        super().__init__()
        self.window = window
        self.registered = False
        self._chord_down = False
        self._active = False
        self._holding = False
        self._last_tap = 0.0
        self._hold_timer = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(8)
        self._poll_timer.timeout.connect(self._poll)

    def register(self) -> bool:
        if self.registered:
            return True
        try:
            # VK_CONTROL=0x11, VK_L/RWIN=0x5B/0x5C. Não registramos uma
            # hotkey no Windows porque o modo "segurar" também precisa saber
            # exatamente quando a combinação foi solta.
            ctypes.windll.user32.GetAsyncKeyState(0x11)
            self._poll_timer.start()
            self.registered = True
        except Exception:
            self.registered = False
        return self.registered

    def close(self) -> None:
        if self.registered:
            self._poll_timer.stop()
            self.registered = False
        self._chord_down = False
        self._holding = False
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None

    def rearm(self) -> bool:
        """Reinicia a leitura nativa depois da criação da janela Qt."""
        self.close()
        return self.register()

    @staticmethod
    def _key_down(vk: int) -> bool:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

    def _poll(self) -> None:
        ctrl_down = self._key_down(0x11)  # VK_CONTROL
        win_down = self._key_down(0x5B) or self._key_down(0x5C)  # VK_L/RWIN
        self._process_chord_state(ctrl_down and win_down)

    def _process_chord_state(self, chord_down: bool) -> None:
        """Parte determinística do atalho, isolada para testes sem Windows."""
        if chord_down and not self._chord_down:
            self._chord_down = True
            self._on_chord_down()
        elif not chord_down and self._chord_down:
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
        # Estado ocioso é deliberadamente um círculo pequeno: o botão fica
        # presente, mas não ocupa a tela enquanto você não está ditando.
        self.setFixedSize(48, 48)
        self.move(cfg.floating_x or 900, cfg.floating_y or 700)
        self.timer = QTimer(self); self.timer.timeout.connect(self.update); self.timer.start(60)
        if cfg.floating: self.show()

    def set_state(self, state: str, recorder=None, message=""):
        self.state, self.recorder = state, recorder
        self.message = message
        if state == "recording": self.started = time.monotonic(); self.setFixedSize(270, 54)
        elif state == "transcribing": self.setFixedSize(180, 42)
        elif state == "error": self.setFixedSize(260, 52)
        else: self.setFixedSize(48, 48)
        self.show(); self.raise_(); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        color = QColor("#172033") if self.state == "idle" else QColor("#202a3d")
        p.setBrush(color); p.setPen(QColor("#3b82f6"))
        if self.state == "idle":
            p.drawEllipse(rect)
        else:
            p.drawRoundedRect(rect, 22, 22)
        p.setPen(QColor("#e8f0ff"))
        if self.state == "idle":
            # O contorno é compacto; o glifo mantém a escala discreta do
            # botão antigo para não parecer um ícone "gigante" na tela.
            font = self.font(); font.setPointSize(10); p.setFont(font)
            p.drawText(rect, Qt.AlignCenter, "🎙")
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


class ReviewDialog(QDialog):
    """Revisão opcional: só ensina quando a pessoa confirma a mudança."""
    def __init__(self, text: str):
        super().__init__()
        self.setWindowTitle("Oiee — Revisar transcrição")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.action = "discard"
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Ajuste o texto se precisar. “Aprender” salva somente as trocas confirmadas neste computador."))
        self.editor = QPlainTextEdit(text)
        self.editor.setMinimumSize(460, 150)
        layout.addWidget(self.editor)
        buttons = QHBoxLayout()
        discard = QPushButton("Descartar")
        insert = QPushButton("Inserir")
        learn = QPushButton("Inserir e aprender")
        discard.clicked.connect(self.reject)
        insert.clicked.connect(lambda: self._finish("insert"))
        learn.clicked.connect(lambda: self._finish("learn"))
        buttons.addWidget(discard); buttons.addWidget(insert); buttons.addWidget(learn)
        layout.addLayout(buttons)

    def _finish(self, action: str):
        self.action = action
        self.accept()


class CorrectionsDialog(QDialog):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("Oiee — Correções aprendidas")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Uma correção por linha no formato: reconhecido => forma correta"))
        lines = [f"{wrong} => {right}" for wrong, right in (cfg.corrections or {}).items()]
        self.editor = QPlainTextEdit("\n".join(lines))
        self.editor.setMinimumSize(460, 220)
        layout.addWidget(self.editor)
        buttons = QHBoxLayout(); clear = QPushButton("Apagar tudo"); save = QPushButton("Salvar")
        clear.clicked.connect(lambda: self.editor.setPlainText("")); save.clicked.connect(self.save)
        buttons.addWidget(clear); buttons.addWidget(save); layout.addLayout(buttons)

    def save(self):
        corrections: dict[str, str] = {}
        for line in self.editor.toPlainText().splitlines():
            if "=>" not in line:
                continue
            wrong, right = (part.strip() for part in line.split("=>", 1))
            if wrong and right and len(wrong) <= 80 and len(right) <= 80:
                corrections[wrong] = right
        self.cfg.corrections = dict(list(corrections.items())[-300:])
        self.cfg.save()
        self.accept()


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
        self.vocabulary = QPlainTextEdit(cfg.vocabulary); self.vocabulary.setPlaceholderText("Ex.: nomes, siglas, marcas, clientes e projetos…"); self.vocabulary.setFixedHeight(70)
        form.addRow("Meu vocabulário", self.vocabulary)
        self.review = QCheckBox("Revisar antes de inserir (permite ensinar correções)"); self.review.setChecked(cfg.review_before_insert); layout.addWidget(self.review)
        learned = QPushButton(f"Gerenciar correções aprendidas ({len(cfg.corrections or {})})")
        learned.clicked.connect(controller.manage_corrections); layout.addWidget(learned)
        self.auto_gain = QCheckBox("Ajustar automaticamente voz baixa"); self.auto_gain.setChecked(cfg.auto_gain); layout.addWidget(self.auto_gain)
        info = QLabel("Atalho: toque Ctrl+Win duas vezes (toggle) ou segure para falar"); layout.addWidget(info)
        test = QPushButton("Testar microfone"); test.clicked.connect(controller.test_microphone); layout.addWidget(test)
        reset = QPushButton("Redefinir posição do botão"); reset.clicked.connect(controller.reset_overlay); layout.addWidget(reset)
        diag = QPushButton("Abrir diagnóstico"); diag.clicked.connect(controller.show_diagnostics); layout.addWidget(diag)
        save = QPushButton("Salvar"); save.clicked.connect(self.save); layout.addWidget(save)
    def save(self):
        self.cfg.model, self.cfg.language = self.model.currentText(), self.language.currentText(); self.cfg.output_mode = self.output.currentData(); self.cfg.device = self.device.currentData(); self.cfg.vocabulary = self.vocabulary.toPlainText().strip(); self.cfg.beam_size = self.beam.currentData(); self.cfg.auto_gain = self.auto_gain.isChecked(); self.cfg.review_before_insert = self.review.isChecked(); self.cfg.save(); self.controller.reload(); self.accept()


class FlowApplication(QObject):
    def __init__(self, app: QApplication, cfg: Config):
        super().__init__(); self.app, self.cfg = app, cfg; self.bridge = UiBridge(); self.overlay = Overlay(cfg)
        # Não aceite a primeira interação antes do loop Qt e do hook global
        # estarem prontos. Isso eliminia o primeiro clique/atalho perdido.
        self.overlay.hide()
        self.engine = DictationEngine(cfg, self.bridge); self.bridge.recording.connect(lambda r: self.overlay.set_state("recording", r)); self.bridge.transcribing.connect(lambda: self.overlay.set_state("transcribing")); self.bridge.error.connect(lambda e: self.overlay.set_state("error", message=e)); self.bridge.idle.connect(lambda: self.overlay.set_state("idle")); self.bridge.result.connect(self.handle_transcription)
        self.overlay.settings_requested.connect(self.open_settings)
        self.hotkey = CtrlWinHotkey(self.overlay); self.hotkey.start_requested.connect(self.engine.start_recording); self.hotkey.stop_requested.connect(self.engine.stop_recording); self.overlay.toggled.connect(self.engine.toggle)
        self.tray = QSystemTrayIcon(tray_icon(), self.overlay); menu = QMenu(); menu.addAction(QAction("Configurações", self.tray, triggered=self.open_settings)); menu.addAction(QAction("Sair", self.tray, triggered=app.quit)); self.tray.setContextMenu(menu); self.tray.setToolTip("Oiee — Ctrl+Win: duplo toque ou segurar"); self.tray.show()
        import threading
        threading.Thread(target=self.engine.transcriber.load, daemon=True).start()
        # O listener baixo nível de ``keyboard`` só fica completamente pronto
        # depois que o loop de mensagens do Qt começa. Armamos agora e uma vez
        # mais antes de exibir o botão; assim a primeira interação já usa o
        # callback definitivo, sem exigir um clique de "despertar".
        QTimer.singleShot(0, self._activate_hotkey)
        QTimer.singleShot(500, self._stabilize_hotkey)
        QTimer.singleShot(650, self._show_ready)

    def _activate_hotkey(self):
        self.hotkey.register()

    def _stabilize_hotkey(self):
        if not self.hotkey.rearm():
            self.overlay.set_state("error", message="Não foi possível registrar Ctrl + Win")

    def _show_ready(self):
        if self.cfg.floating:
            self.overlay.set_state("idle")
    def open_settings(self):
        dialog = Settings(self.cfg, self)
        QTimer.singleShot(0, lambda: (dialog.raise_(), dialog.activateWindow()))
        dialog.exec()
    def reload(self): self.engine.reload()
    def manage_corrections(self):
        dialog = CorrectionsDialog(self.cfg)
        if dialog.exec():
            self.reload()
    def handle_transcription(self, raw_text: str):
        """Roda na UI Qt: o worker nunca toca em widgets diretamente."""
        text = self.cfg.apply_corrections(raw_text)
        clean, actions = parse_commands(text, self.cfg.language)
        if self.cfg.review_before_insert and clean:
            dialog = ReviewDialog(clean)
            if not dialog.exec() or dialog.action == "discard":
                return
            revised = dialog.editor.toPlainText().strip()
            if dialog.action == "learn" and revised:
                learned = self.cfg.learn_corrections(clean, revised)
                if learned:
                    self.cfg.save()
                    self.reload()
            clean = revised
        if clean:
            typer.type_text(clean, self.cfg.output_mode)
        if actions:
            typer.apply_actions(actions)
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
