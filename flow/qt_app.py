"""Aplicação Windows do Oiee: uma única UI Qt, sem Tk/CTk."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import threading
import time

import numpy as np
import sounddevice as sd
from PySide6.QtCore import (QObject, QTimer, Qt, Signal, QRect, QRectF)
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QMenu,
                               QHBoxLayout, QLabel, QPushButton, QSystemTrayIcon,
                               QVBoxLayout, QWidget, QPlainTextEdit, QMessageBox, QCheckBox)

from . import autostart
from .config import CONFIG_PATH, LANGUAGES, LANGUAGE_NAMES, MODELS, OUTPUT_MODES, Config
from .cleanup import cleanup
from .commands import parse_commands
from .engine import DictationEngine
from .errors import log_path
from .snippets import expand_snippets
from .transcriber import STATUS_ERROR, STATUS_READY
from . import typer

# Default do botão flutuante: centro inferior, um pouco acima da barra de
# tarefas — igual ao Flow Bar do Wispr Flow. Usa availableGeometry (área
# sem a barra de tarefas) e não coordenadas fixas de tela.
DEFAULT_GAP_ABOVE_TASKBAR = 16


def default_overlay_position(width: int = 64, height: int = 20, area: QRect | None = None) -> tuple[int, int]:
    """Posição padrão da barra: centro horizontal, acima da barra de tarefas."""
    if area is None:
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else None
    if area is None:
        return 900, 700  # fallback sem tela (testes/headless)
    x = area.left() + (area.width() - width) // 2
    y = area.bottom() + 1 - height - DEFAULT_GAP_ABOVE_TASKBAR
    return int(x), int(y)


class PingListener(QObject):
    """Escuta o evento nomeado criado pela instância ativa.

    A 2ª instância (clique no atalho com o app rodando) sinaliza esse evento;
    a thread de espera emite ``pinged`` na thread da UI. Fazemos isso com
    WaitForSingleObject + Signal porque o QWinEventNotifier do PySide6 6.11
    não converte o argumento HANDLE do sinal ``activated``.
    """
    pinged = Signal()

    def __init__(self, handle: int):
        super().__init__()
        self._handle = handle
        threading.Thread(target=self._wait_loop, daemon=True).start()

    def _wait_loop(self) -> None:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, wintypes.DWORD)
        k32.WaitForSingleObject.restype = wintypes.DWORD
        WAIT_OBJECT_0 = 0
        while k32.WaitForSingleObject(self._handle, 0xFFFFFFFF) == WAIT_OBJECT_0:
            self.pinged.emit()  # evento auto-reset: proxima espera bloqueia de novo


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
        self._dirty = False
        self._last_tap = 0.0
        self._ignore_release = False
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.setInterval(250)
        self._hold_timer.timeout.connect(self._start_hold_if_still_down)
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
        self._dirty = False
        self._ignore_release = False
        self._hold_timer.stop()

    def rearm(self) -> bool:
        """Reinicia a leitura nativa depois da criação da janela Qt."""
        self.close()
        return self.register()

    @staticmethod
    def _key_down(vk: int) -> bool:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

    # Teclas que não pertencem ao gesto Oiee. Qualquer uma delas junto com
    # Ctrl+Win significa um combo do Windows (Ctrl+Win+setas/D = desktops
    # virtuais), não um pedido de ditado.
    _EXTRA_VKS = tuple(range(0x41, 0x5B)) + tuple(range(0x30, 0x3A)) \
        + tuple(range(0x70, 0x7C)) + (0x25, 0x26, 0x27, 0x28,  # setas
                                      0x0D, 0x20, 0x09, 0x1B, 0x10)  # enter, space, tab, esc, shift

    def _extra_key_down(self) -> bool:
        return any(self._key_down(vk) for vk in self._EXTRA_VKS)

    def _poll(self) -> None:
        ctrl_down = self._key_down(0x11)  # VK_CONTROL
        win_down = self._key_down(0x5B) or self._key_down(0x5C)  # VK_L/RWIN
        chord_down = ctrl_down and win_down
        self._process_chord_state(chord_down, chord_down and self._extra_key_down())

    def _process_chord_state(self, chord_down: bool, extra_down: bool = False) -> None:
        """Parte determinística do atalho, isolada para testes sem Windows.

        ``extra_down``: outra tecla pressionada junto com o acorde. O acorde
        vira "sujo" — combos do Windows não podem iniciar gravação nem contar
        como toque do duplo-toque.
        """
        if chord_down and not self._chord_down:
            self._chord_down = True
            self._on_chord_down()
        elif not chord_down and self._chord_down:
            self._chord_down = False
            self._on_chord_up()
        if chord_down and extra_down:
            self._dirty = True
            self._hold_timer.stop()
            if self._holding:
                # a gravação por hold já tinha começado, mas o combo mostra
                # que não era ditado — parar antes de transcrever ruído.
                self._holding = False
                self.stop_requested.emit()

    def _on_chord_down(self) -> None:
        if self._active:
            self._active = False
            # A soltura deste toque encerrou uma gravação: não pode contar
            # como "primeiro tap" (senão parar com toque duplo reiniciava).
            self._ignore_release = True
            self.stop_requested.emit()
            return
        # Um toque curto pode fazer parte do gesto de dois toques. Só inicia
        # o push-to-talk se o acorde permanecer pressionado por 250 ms.
        self._hold_timer.start()

    def _start_hold_if_still_down(self) -> None:
        if self._chord_down and not self._active and not self._dirty:
            self._holding = True
            self.start_requested.emit()

    def _on_chord_up(self) -> None:
        self._hold_timer.stop()
        now = time.monotonic()
        if self._dirty:
            # Soltura de um combo do Windows: não conta como tap nem arma o
            # próximo toque duplo (um tap limpo logo antes também é cancelado).
            self._dirty = False
            self._ignore_release = False
            self._last_tap = 0.0
            return
        if self._holding:
            self._holding = False
            self.stop_requested.emit()
            # Um hold concluído também arma o toque duplo: assim um primeiro
            # tap lento (que virou hold) + um segundo tap rápido alterna.
            self._last_tap = now
            return
        if self._active:
            return
        if self._ignore_release:
            # Soltura do toque que parou uma gravação: consome sem armar.
            self._ignore_release = False
            return
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
        self._hover = False
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Estado ocioso é deliberadamente uma barrinha horizontal minúscula
        # (estilo Flow Bar do Wispr Flow): presente, mas quase invisível na
        # tela enquanto você não está ditando.
        self.setFixedSize(64, 20)
        if cfg.floating_x is not None and cfg.floating_y is not None:
            self.move(cfg.floating_x, cfg.floating_y)
        else:
            self.move(*default_overlay_position(self.width(), self.height()))
        self.timer = QTimer(self); self.timer.timeout.connect(self.update); self.timer.start(60)
        if cfg.floating: self.show()

    def set_state(self, state: str, recorder=None, message=""):
        self.state, self.recorder = state, recorder
        self.message = message
        if state == "recording": self.started = time.monotonic(); self.setFixedSize(270, 54)
        elif state == "transcribing": self.setFixedSize(180, 42)
        elif state == "error": self.setFixedSize(260, 52)
        else: self.setFixedSize(64, 20)
        self.show(); self.raise_(); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        if self.state == "idle":
            # Pílula azul da marca; no hover clareia para dar feedback de clique.
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#3da9ff") if self._hover else QColor("#0a84ff"))
            pill = QRectF(self.rect()).adjusted(4, 5, -4, -5)
            p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            return
        p.setBrush(QColor("#202a3d")); p.setPen(QColor("#3b82f6"))
        p.drawRoundedRect(rect, 22, 22)
        p.setPen(QColor("#e8f0ff"))
        if self.state == "recording":
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

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

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


class SnippetsDialog(QDialog):
    """Editor de snippets no formato simples: atalho => texto (\\n = quebra)."""

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("Oiee — Snippets")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Um snippet por linha no formato: <b>atalho =&gt; texto</b><br>"
            "Dite <b>snippet</b> + o atalho para inserir. Use \\n para quebra de linha."
        ))
        lines = [
            f"{name} => {str(body).replace(chr(10), chr(92) + 'n')}"
            for name, body in (cfg.snippets or {}).items()
        ]
        self.editor = QPlainTextEdit("\n".join(lines))
        self.editor.setPlaceholderText("Ex.: agenda => Reunião de 30 min? https://calendly.com/seu-link")
        self.editor.setMinimumSize(520, 240)
        layout.addWidget(self.editor)
        buttons = QHBoxLayout()
        clear = QPushButton("Apagar tudo")
        save = QPushButton("Salvar")
        clear.clicked.connect(lambda: self.editor.setPlainText(""))
        save.clicked.connect(self.save)
        buttons.addWidget(clear)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def save(self):
        snippets: dict[str, str] = {}
        for line in self.editor.toPlainText().splitlines():
            if "=>" not in line:
                continue
            name, body = (part.strip() for part in line.split("=>", 1))
            body = body.replace("\\n", "\n")
            if name and body and len(name) <= 60 and len(body) <= 2000:
                snippets[name] = body
        self.cfg.snippets = dict(list(snippets.items())[-200:])
        self.cfg.save()
        self.accept()


class PrivacyDialog(QDialog):
    """Declaração de privacidade — o diferencial do Oiee contra serviços na nuvem."""

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("Oiee — Privacidade e dados")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        layout = QVBoxLayout(self)
        body = QLabel(
            "<b>Sua fala e seu texto nunca saem do seu computador.</b><br><br>"
            "• A transcrição roda <b>100% local</b> (modelo Whisper no seu PC) — sem servidores.<br>"
            "• Sem conta, sem cadastro, sem limite de palavras e sem telemetria.<br>"
            "• Único acesso à internet: o download do modelo na primeira execução "
            "(Hugging Face). Depois, tudo offline.<br>"
            "• Vocabulário, correções e snippets ficam só neste computador.<br>"
            "• Único arquivo de log: <b>oiee-error.log</b> (erros técnicos, local)."
        )
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        body.setMinimumWidth(480)
        layout.addWidget(body)
        layout.addWidget(QLabel(f"Configuração: {CONFIG_PATH}"))
        buttons = QHBoxLayout()
        folder = QPushButton("Abrir pasta da configuração")
        close = QPushButton("Fechar")
        folder.clicked.connect(lambda: os.startfile(os.path.dirname(CONFIG_PATH)))
        close.clicked.connect(self.accept)
        buttons.addWidget(folder)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)


class OnboardingTip(QWidget):
    """Balão da primeira execução: ensina o gesto do atalho.

    O atalho é invisível e a descoberta por tentativa gera confusão ("será
    que quebrou?"). Some ao clicar em "Entendi" ou sozinho após 30 s.
    """

    def __init__(self, cfg: Config, x: int, y: int):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.cfg = cfg
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        label = QLabel(
            "Primeira vez? Toque <b>Ctrl+Win duas vezes</b> para ditar — "
            "ou <b>segure</b> para falar enquanto fala.<br>"
            "O texto entra no app que estiver em foco. Botão direito na barra "
            "azul abre as Configurações."
        )
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setStyleSheet("color: #e8f0ff; background: transparent;")
        layout.addWidget(label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("Entendi")
        ok.setCursor(Qt.PointingHandCursor)
        ok.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; border: none;"
            " border-radius: 8px; padding: 6px 16px; font-weight: bold; }"
            "QPushButton:hover { background: #2563eb; }"
        )
        ok.clicked.connect(self.dismiss)
        buttons.addWidget(ok)
        layout.addLayout(buttons)
        self.setFixedWidth(340)
        self.move(max(20, x), max(20, y))
        QTimer.singleShot(30_000, self.dismiss)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#172033"))
        painter.setPen(QColor("#3b82f6"))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

    def dismiss(self):
        if not self.cfg.onboarded:
            self.cfg.onboarded = True
            self.cfg.save()
        self.close()


class Settings(QDialog):
    def __init__(self, cfg: Config, controller):
        super().__init__(); self.cfg, self.controller = cfg, controller; self.setWindowTitle("Oiee — Configurações")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.ApplicationModal)
        layout = QVBoxLayout(self); form = QFormLayout(); layout.addLayout(form)
        self.model = QComboBox(); self.model.addItems(MODELS); self.model.setCurrentText(cfg.model); form.addRow("Modelo", self.model)
        self.language = QComboBox()
        for code in LANGUAGES:
            self.language.addItem(f"{code} — {LANGUAGE_NAMES.get(code, code)}", code)
        self.language.setCurrentIndex(max(0, self.language.findData(cfg.language)))
        form.addRow("Idioma", self.language)
        self.output = QComboBox(); [self.output.addItem(label, key) for key, label in OUTPUT_MODES.items()]; self.output.setCurrentIndex(self.output.findData(cfg.output_mode)); form.addRow("Inserção", self.output)
        self.beam = QComboBox(); self.beam.addItem("Rápido (1)", 1); self.beam.addItem("Equilibrado (3)", 3); self.beam.addItem("Mais preciso (5)", 5); self.beam.setCurrentIndex(max(0, self.beam.findData(cfg.beam_size))); form.addRow("Qualidade", self.beam)
        self.device = QComboBox(); self.device.addItem("Padrão do sistema", None)
        for i,d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0: self.device.addItem(d["name"], i)
        self.device.setCurrentIndex(max(0, self.device.findData(cfg.device))); form.addRow("Microfone", self.device)
        self.vocabulary = QPlainTextEdit(cfg.vocabulary); self.vocabulary.setPlaceholderText("Ex.: Kubernetes, PostgreSQL, Power BI, Oiee, sprint, pull request…"); self.vocabulary.setFixedHeight(70)
        form.addRow("Meu vocabulário", self.vocabulary)
        self.review = QCheckBox("Revisar antes de inserir (permite ensinar correções)"); self.review.setChecked(cfg.review_before_insert); layout.addWidget(self.review)
        learned = QPushButton(f"Gerenciar correções aprendidas ({len(cfg.corrections or {})})")
        learned.clicked.connect(controller.manage_corrections); layout.addWidget(learned)
        snippets = QPushButton(f"Gerenciar snippets ({len(cfg.snippets or {})})")
        snippets.clicked.connect(controller.manage_snippets); layout.addWidget(snippets)
        self.auto_gain = QCheckBox("Ajustar automaticamente voz baixa"); self.auto_gain.setChecked(cfg.auto_gain); layout.addWidget(self.auto_gain)
        self.smart_cleanup = QCheckBox("Limpar texto automaticamente (muletas, repetições, maiúsculas)"); self.smart_cleanup.setChecked(cfg.smart_cleanup); layout.addWidget(self.smart_cleanup)
        self.autostart = QCheckBox("Iniciar com o Windows"); self.autostart.setChecked(autostart.is_enabled())
        if not autostart.available():
            self.autostart.setEnabled(False)
            self.autostart.setToolTip("Disponível apenas no Oiee instalado (.exe)")
        layout.addWidget(self.autostart)
        info = QLabel("Atalho: toque Ctrl+Win duas vezes (toggle) ou segure para falar"); layout.addWidget(info)
        test = QPushButton("Testar microfone"); test.clicked.connect(controller.test_microphone); layout.addWidget(test)
        reset = QPushButton("Redefinir posição do botão"); reset.clicked.connect(controller.reset_overlay); layout.addWidget(reset)
        diag = QPushButton("Abrir diagnóstico"); diag.clicked.connect(controller.show_diagnostics); layout.addWidget(diag)
        privacy = QPushButton("Privacidade e dados"); privacy.clicked.connect(controller.show_privacy); layout.addWidget(privacy)
        save = QPushButton("Salvar"); save.clicked.connect(self.save); layout.addWidget(save)
    def save(self):
        self.cfg.model, self.cfg.language = self.model.currentText(), self.language.currentData(); self.cfg.output_mode = self.output.currentData(); self.cfg.device = self.device.currentData(); self.cfg.vocabulary = self.vocabulary.toPlainText().strip(); self.cfg.beam_size = self.beam.currentData(); self.cfg.auto_gain = self.auto_gain.isChecked(); self.cfg.review_before_insert = self.review.isChecked(); self.cfg.smart_cleanup = self.smart_cleanup.isChecked(); self.cfg.save()
        if self.autostart.isEnabled():
            autostart.set_enabled(self.autostart.isChecked())
        self.controller.reload(); self.accept()


class FlowApplication(QObject):
    def __init__(self, app: QApplication, cfg: Config, ping_event=None):
        super().__init__(); self.app, self.cfg = app, cfg; self.bridge = UiBridge(); self.overlay = Overlay(cfg)
        # Não aceite a primeira interação antes do loop Qt e do hook global
        # estarem prontos. Isso eliminia o primeiro clique/atalho perdido.
        self.overlay.hide()
        self.engine = DictationEngine(cfg, self.bridge); self.bridge.recording.connect(lambda r: self.overlay.set_state("recording", r)); self.bridge.transcribing.connect(lambda: self.overlay.set_state("transcribing")); self.bridge.error.connect(lambda e: self.overlay.set_state("error", message=e)); self.bridge.idle.connect(lambda: self.overlay.set_state("idle")); self.bridge.result.connect(self.handle_transcription)
        self.overlay.settings_requested.connect(self.open_settings)
        self.hotkey = CtrlWinHotkey(self.overlay); self.hotkey.start_requested.connect(self.engine.start_recording); self.hotkey.stop_requested.connect(self.engine.stop_recording); self.overlay.toggled.connect(self.engine.toggle)
        self.tray = QSystemTrayIcon(tray_icon(), self.overlay); menu = QMenu(); menu.addAction(QAction("Configurações", self.tray, triggered=self.open_settings)); menu.addAction(QAction("Sair", self.tray, triggered=app.quit)); self.tray.setContextMenu(menu); self.tray.setToolTip("Oiee — Ctrl+Win: duplo toque ou segurar"); self.tray.show(); self._watching_model = False
        # A barra só aparece depois que a leitura nativa já está ativa. Não
        # reiniciamos o monitor depois disso: um reinício atrasado podia apagar
        # justamente a primeira combinação pressionada pelo usuário.
        self._loading_polls = 0
        self._ping_notifier = None
        if ping_event is not None:
            # clique no atalho com o app já rodando: 2ª instância sinaliza aqui
            self._ping_handle = ping_event  # mantém o handle vivo durante o app
            self._ping_listener = PingListener(ping_event)
            self._ping_listener.pinged.connect(self._on_ping)
        QTimer.singleShot(0, self._become_ready)

    def _on_ping(self, *_):
        """Feedback do clique no atalho: o app já está ativo — destaca a barra."""
        self.tray.showMessage("Oiee", "Já estou por aqui — destaquei a barra azul na tela.",
                              QSystemTrayIcon.Information, 3000)
        if self.overlay.state == "idle":
            if not self.overlay.isVisible() and self.cfg.floating:
                self.overlay.set_state("idle")
            if self.overlay.isVisible():
                self.overlay.raise_()
                self._flash_overlay()

    def _flash_overlay(self) -> None:
        """Pulso de opacidade na barra para o clique não passar despercebido."""
        steps = [0.3, 1.0, 0.3, 1.0, 0.3, 1.0]

        def step(i: int = 0) -> None:
            if i >= len(steps):
                return
            self.overlay.setWindowOpacity(steps[i])
            QTimer.singleShot(150, lambda: step(i + 1))

        step()

    def _become_ready(self):
        if not self.hotkey.register():
            self.overlay.set_state("error", message="Não foi possível registrar Ctrl + Win")
        elif self.cfg.floating:
            self.overlay.set_state("idle")
        # Pré-carrega o modelo em background: sem isso a primeira fala
        # parecia "morta" (modelo baixando/carregando no Transcrevendo…).
        self.engine.preload()
        self._watch_model_status()
        if not self.cfg.onboarded:
            # espera a tela assentar para posicionar a balinha perto do botão
            QTimer.singleShot(2000, self._show_onboarding)

    def _show_onboarding(self):
        if self.cfg.onboarded:
            return
        self._onboarding = OnboardingTip(self.cfg, self.overlay.x() + self.overlay.width() + 8, self.overlay.y() - 16)
        self._onboarding.show()
        self._onboarding.raise_()

    def _watch_model_status(self) -> None:
        """Mostra o carregamento do modelo no tooltip/balão da bandeja."""
        if self._watching_model:
            return
        self._watching_model = True
        self._loading_polls = 0
        self._poll_model_status()

    def _poll_model_status(self) -> None:
        status = self.engine.transcriber.status
        if status == STATUS_READY:
            self.tray.setToolTip("Oiee — Ctrl+Win: duplo toque ou segurar")
            self._watching_model = False
            return
        if status == STATUS_ERROR:
            # sem esse ramo o tooltip ficava preso em "carregando modelo…" para
            # sempre quando o download/carregamento falhava.
            self.tray.setToolTip("Oiee — modelo de voz não carregou (veja oiee-error.log)")
            self.tray.showMessage("Oiee", "Não consegui carregar o modelo de voz. Veja oiee-error.log ao lado do app.",
                                  QSystemTrayIcon.Warning, 5000)
            self._watching_model = False
            return
        self.tray.setToolTip("Oiee — carregando modelo…")
        self._loading_polls += 1
        if self._loading_polls == 2:
            #2s e ainda carregando: avisa o usuário (a 1ª vez baixa ~460 MB)
            self.tray.showMessage("Oiee", "Preparando modelo de voz… (a 1ª vez baixa ~460 MB)",
                                  QSystemTrayIcon.Information, 4000)
        QTimer.singleShot(1000, self._poll_model_status)
    def open_settings(self):
        dialog = Settings(self.cfg, self)
        QTimer.singleShot(0, lambda: (dialog.raise_(), dialog.activateWindow()))
        dialog.exec()
    def reload(self): self.engine.reload(); self._watch_model_status()
    def manage_corrections(self):
        dialog = CorrectionsDialog(self.cfg)
        if dialog.exec():
            self.reload()

    def manage_snippets(self):
        dialog = SnippetsDialog(self.cfg)
        if dialog.exec():
            self.reload()

    def show_privacy(self):
        PrivacyDialog(self.cfg).exec()

    def handle_transcription(self, raw_text: str):
        """Roda na UI Qt: o worker nunca toca em widgets diretamente."""
        text = self.cfg.apply_corrections(raw_text)
        if self.cfg.smart_cleanup:
            text = cleanup(text, self.cfg.language)
        clean, actions = parse_commands(text, self.cfg.language)
        if clean:
            clean, _ = expand_snippets(clean, self.cfg.snippets)
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
    def reset_overlay(self):
        self.cfg.floating_x, self.cfg.floating_y = None, None
        self.cfg.save()
        self.overlay.move(*default_overlay_position(self.overlay.width(), self.overlay.height()))
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
