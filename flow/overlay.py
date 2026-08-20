"""Interface visual: barra flutuante minimalista estilo Wispr Flow + configurações.

Estilo Wispr Flow:
- idle: barrinha translúcida discreta no canto inferior
- hover: expande mostrando ícone + atalho
- gravando: barrinha com ondas ao vivo + botões ✕/✓
- transcrevendo: indicador compacto
"""
import queue
import threading
import time
import tkinter as tk
import traceback

import customtkinter as ctk

from .errors import log_exception
import numpy as np
import pyperclip
import sounddevice as sd
from PIL import Image, ImageDraw

from .config import LANGUAGES, MODELS, OUTPUT_MODES, Config

# -- cores ---------------------------------------------------------------
ACCENT = "#0a84ff"
ACCENT_DIM = "#3a6ab5"
CARD_BG = "#1c1c1ee0"
CARD_BORDER = "#3a3a4a"
IDLE_BG = "#1c1c1eb0"       # translúcido
IDLE_HOVER_BG = "#2c2c2ee0"
RECORDING_BG = "#1c1c1ef0"
TEXT = "#e6e6f0"
MUTED = "#9a9ab0"
RED = "#ff453a"
GREEN = "#30d158"

# -- dimensões (compactas) -----------------------------------------------
BAR_H = 8                    # idle bar height
BAR_W = 72                   # idle bar width
HOVER_W = 200                # hover pill width
HOVER_H = 36                 # hover pill height
REC_W = 240                  # recording pill width
REC_H = 40                   # recording pill height
CORNER = 20                  # corner radius for pills
MARGIN = 12                  # distance from screen edge

HOTKEY_PRESETS = [
    ("Alt Direito (segurar)", "right alt", "hold"),
    ("Ctrl + Win (segurar)", "ctrl+win", "hold"),
    ("Ctrl + Win (alternar)", "ctrl+win", "toggle"),
    ("Caps Lock (segurar)", "caps lock", "hold"),
    ("F9 (segurar)", "f9", "hold"),
    ("Ctrl + Espaço (alternar)", "ctrl+space", "toggle"),
    ("Personalizado…", None, None),
]
PRESET_LABELS = [label for label, _, _ in HOTKEY_PRESETS]
MODES = [("hold", "Segurar (aperte e segure)"), ("toggle", "Alternar (toque para ligar/desligar)")]


def _mic_icon(size: int = 20) -> Image.Image:
    """Small mic icon for the hover pill."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 20.0
    # mic body
    d.rounded_rectangle((7 * s, 2 * s, 13 * s, 10 * s), radius=3 * s, fill="white")
    # mic stand
    d.rectangle((9 * s, 10 * s, 11 * s, 13 * s), fill="white")
    d.rounded_rectangle((6 * s, 12 * s, 14 * s, 14 * s), radius=1 * s, fill="white")
    return img


def _close_icon(size: int = 16) -> Image.Image:
    """X icon for cancel."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 3
    d.line((m, m, size - m, size - m), fill=RED, width=2)
    d.line((size - m, m, m, size - m), fill=RED, width=2)
    return img


def _check_icon(size: int = 16) -> Image.Image:
    """Checkmark icon for confirm."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line((4, 9, 7, 12, 12, 4), fill=GREEN, width=2)
    return img


class Overlay:
    def __init__(self, config: Config, engine_getter):
        self.cfg = config
        self.engine_getter = engine_getter
        self._q: "queue.Queue[callable]" = queue.Queue()
        self.root: ctk.CTk | None = None
        self.win: ctk.CTkToplevel | None = None
        self._state = "idle"  # idle | hover | recording | transcribing | error
        self._cx = 0.0
        self._cy = 0.0
        self._recorder = None
        self._t0: float | None = None
        self._hide_after: str | None = None
        self._dragging = False
        self._drag_off = (0, 0)
        self._canvas: tk.Canvas | None = None
        self._status: ctk.CTkLabel | None = None
        self._hover_timer: str | None = None
        self._mic_ctk = ctk.CTkImage(light_image=_mic_icon(), dark_image=_mic_icon(), size=(16, 16))
        self._close_ctk = ctk.CTkImage(light_image=_close_icon(), dark_image=_close_icon(), size=(14, 14))
        self._check_ctk = ctk.CTkImage(light_image=_check_icon(), dark_image=_check_icon(), size=(14, 14))
        threading.Thread(target=self._run, daemon=True).start()
        self._call(self._start)

    # -- thread Tk --------------------------------------------------------
    def _run(self) -> None:
        try:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
            self.root.withdraw()
            self._poll()
            self.root.mainloop()
        except Exception:
            log_exception("thread da UI")
            raise

    def _poll(self) -> None:
        try:
            while True:
                self._q.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            log_exception("chamada da fila da UI")
        self.root.after(100, self._poll)

    def _call(self, fn) -> None:
        self._q.put(fn)

    # -- floating bar -----------------------------------------------------
    def _start(self) -> None:
        if not self.cfg.floating:
            return
        self.win = ctk.CTkToplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.85)  # translúcido
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        # posição: canto inferior direito
        self._cx = self.cfg.floating_x if self.cfg.floating_x is not None else sw - 60
        self._cy = self.cfg.floating_y if self.cfg.floating_y is not None else sh - MARGIN - BAR_H // 2
        self._clamp(sw, sh)
        self._render_idle()

    def _clamp(self, sw: int, sh: int) -> None:
        self._cx = max(BAR_W // 2 + MARGIN, min(sw - BAR_W // 2 - MARGIN, self._cx))
        self._cy = max(BAR_H // 2 + MARGIN, min(sh - BAR_H // 2 - MARGIN, self._cy))

    def _geometry(self, w: int, h: int) -> None:
        x = int(self._cx - w / 2)
        y = int(self._cy - h / 2)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _clear_children(self) -> None:
        for child in self.win.winfo_children():
            child.destroy()

    # -- idle: barrinha translúcida fina ----------------------------------
    def _render_idle(self) -> None:
        self._clear_children()
        self._state = "idle"
        self.win.geometry(f"{BAR_W}x{BAR_H}")
        self.win.attributes("-alpha", 0.55)

        bar = tk.Canvas(self.win, width=BAR_W, height=BAR_H, bg="#1c1c1e", highlightthickness=0)
        bar.pack()
        # barrinha arredondada
        r = BAR_H // 2
        bar.create_arc(0, 0, BAR_H, BAR_H, start=90, extent=180, fill=ACCENT_DIM, outline="")
        bar.create_rectangle(r, 0, BAR_W - r, BAR_H, fill=ACCENT_DIM, outline="")
        bar.create_arc(BAR_W - BAR_H, 0, BAR_W, BAR_H, start=270, extent=180, fill=ACCENT_DIM, outline="")

        # hover: expande pra mostrar controles
        self.win.bind("<Enter>", self._on_enter_idle)
        self._bind_drag(bar)
        self._geometry(BAR_W, BAR_H)

    def _on_enter_idle(self, _event=None) -> None:
        """Mouse entrou na barra -> expande pro hover."""
        if self._state != "idle":
            return
        self._render_hover()

    # -- hover: mostra mic + atalho ---------------------------------------
    def _render_hover(self) -> None:
        self._clear_children()
        self._state = "hover"
        self.win.attributes("-alpha", 0.92)

        pill = ctk.CTkFrame(self.win, corner_radius=CORNER, fg_color=IDLE_HOVER_BG,
                            border_width=1, border_color=CARD_BORDER, cursor="hand2")
        pill.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(pill, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=10, pady=6)

        # ícone de mic
        mic_label = ctk.CTkLabel(inner, text="", image=self._mic_ctk, width=20)
        mic_label.pack(side="left", padx=(0, 6))

        # texto do atalho
        hk = self.cfg.hotkey or "right alt"
        hk_display = hk.replace("ctrl", "Ctrl").replace("win", "Win").replace("alt", "Alt").replace("right ", "R")
        mode_display = "+" if self.cfg.hotkey_mode == "hold" else ""
        label_text = f"Gravar  {hk_display}{mode_display}"
        text_label = ctk.CTkLabel(inner, text=label_text, text_color=TEXT,
                                  font=ctk.CTkFont(size=11))
        text_label.pack(side="left")

        # mouse saiu -> volta pro idle
        self.win.bind("<Leave>", self._on_leave_hover)

        # Arrastar ou clicar. O mesmo bind não pode ser aplicado duas vezes:
        # tkinter substitui o callback anterior, o que fazia o botão parar de
        # responder ao clique depois de receber os binds de arrastar.
        toggle = lambda: self.engine_getter().toggle()
        self._bind_drag(pill, on_click=toggle)
        self._bind_drag(mic_label, on_click=toggle)
        self._bind_drag(text_label, on_click=toggle)

        self._geometry(HOVER_W, HOVER_H)

    def _on_leave_hover(self, _event=None) -> None:
        """Mouse saiu do hover -> volta pro idle (com delay pra não piscar)."""
        if self._state != "hover":
            return
        # pequeno delay antes de voltar (evita flicker)
        if self._hover_timer:
            self.root.after_cancel(self._hover_timer)
        self._hover_timer = self.root.after(200, self._check_leave)

    def _check_leave(self) -> None:
        self._hover_timer = None
        if self._state == "hover":
            # verifica se o mouse ainda está sobre a janela
            try:
                x = self.root.winfo_pointerx()
                y = self.root.winfo_pointery()
                wx = self.win.winfo_rootx()
                wy = self.win.winfo_rooty()
                ww = self.win.winfo_width()
                wh = self.win.winfo_height()
                if not (wx <= x <= wx + ww and wy <= y <= wy + wh):
                    self._render_idle()
            except Exception:
                self._render_idle()

    # -- recording: barrinha com ondas ------------------------------------
    def _render_recording(self) -> None:
        self._clear_children()
        self._state = "recording"
        self.win.attributes("-alpha", 0.95)

        pill = ctk.CTkFrame(self.win, corner_radius=CORNER, fg_color=RECORDING_BG,
                            border_width=1, border_color=ACCENT, cursor="hand2")
        pill.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(pill, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=8, pady=6)

        # botão cancelar (X)
        btn_cancel = ctk.CTkButton(inner, text="", image=self._close_ctk, width=24, height=24,
                                   fg_color="transparent", hover_color="#ff453a30",
                                   command=lambda: self.engine_getter().toggle())
        btn_cancel.pack(side="left", padx=(2, 4))

        # canvas de ondas
        self._canvas = tk.Canvas(inner, width=140, height=28, bg="#1c1c1e", highlightthickness=0)
        self._canvas.pack(side="left", padx=4)

        # botão confirmar (✓)
        btn_ok = ctk.CTkButton(inner, text="", image=self._check_ctk, width=24, height=24,
                               fg_color="transparent", hover_color="#30d15830",
                               command=lambda: self.engine_getter().toggle())
        btn_ok.pack(side="right", padx=(4, 2))

        self._geometry(REC_W, REC_H)
        self._wave_tick()

    # -- transcribing / error ---------------------------------------------
    def _render_transcribing(self) -> None:
        self._clear_children()
        self._state = "transcribing"
        self.win.attributes("-alpha", 0.92)

        pill = ctk.CTkFrame(self.win, corner_radius=CORNER, fg_color=RECORDING_BG,
                            border_width=1, border_color=CARD_BORDER)
        pill.pack(fill="both", expand=True)
        label = ctk.CTkLabel(pill, text="Transcrevendo...", text_color=MUTED,
                             font=ctk.CTkFont(size=11))
        label.pack(expand=True, padx=12, pady=4)
        self._geometry(140, 32)

    def _render_error(self, message: str) -> None:
        self._clear_children()
        self._state = "error"
        self.win.attributes("-alpha", 0.92)

        pill = ctk.CTkFrame(self.win, corner_radius=CORNER, fg_color=RECORDING_BG,
                            border_width=1, border_color=RED)
        pill.pack(fill="both", expand=True)
        label = ctk.CTkLabel(pill, text=f"Erro: {message[:36]}", text_color=RED,
                             font=ctk.CTkFont(size=10), wraplength=180)
        label.pack(expand=True, padx=10, pady=4)
        self._geometry(200, 32)

    # -- arrastar ---------------------------------------------------------
    def _bind_drag(self, widget, on_click=None) -> None:
        widget.bind("<Button-1>", self._on_press)
        widget.bind("<B1-Motion>", self._on_drag)
        widget.bind("<ButtonRelease-1>", lambda event: self._on_release(event, on_click))

    def _on_press(self, event) -> None:
        self._dragging = False
        self._drag_off = (event.x_root - self._cx, event.y_root - self._cy)

    def _on_drag(self, event) -> None:
        self._dragging = True
        self._cx = event.x_root - self._drag_off[0]
        self._cy = event.y_root - self._drag_off[1]
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self._clamp(sw, sh)
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        self._geometry(w, h)

    def _on_release(self, event, on_click=None) -> None:
        if self._dragging:
            self._dragging = False
            self.cfg.floating_x = int(self._cx)
            self.cfg.floating_y = int(self._cy)
            self.cfg.save()
        elif on_click is not None:
            on_click()

    # -- estados públicos -------------------------------------------------
    def show_recording(self, recorder) -> None:
        def f():
            self._recorder = recorder
            self._t0 = time.monotonic()
            # A barra pode estar desativada nas configurações. Nesse caso a UI
            # é opcional, mas o ditado continua funcionando normalmente.
            if self.win is not None:
                self._render_recording()
        self._call(f)

    def show_transcribing(self) -> None:
        def f():
            self._t0 = None
            if self.win is not None:
                self._render_transcribing()
        self._call(f)

    def show_error(self, message: str) -> None:
        def f():
            self._t0 = None
            if self.win is not None:
                self._render_error(message)
                self._hide_after = self.root.after(4000, self._hide)
        self._call(f)

    def hide(self) -> None:
        def f():
            if self._hide_after:
                self.root.after_cancel(self._hide_after)
                self._hide_after = None
            self._hide()
        self._call(f)

    def _hide(self) -> None:
        self._t0 = None
        self._recorder = None
        if self.win is not None and self._state != "idle":
            self._render_idle()

    def set_floating(self, show: bool) -> None:
        def f():
            if show and self.win is None:
                self._start()
            elif not show and self.win is not None:
                self.win.destroy()
                self.win = None
        self._call(f)

    # -- onda sonora ao vivo ----------------------------------------------
    def _wave_tick(self) -> None:
        if self._state != "recording":
            return
        audio = self._recorder.recent(0.45) if self._recorder is not None else np.zeros(0, dtype=np.float32)
        canvas = self._canvas
        if canvas is not None:
            self._draw_wave(canvas, audio)
        self.root.after(60, self._wave_tick)

    def _draw_wave(self, canvas: tk.Canvas, audio: np.ndarray) -> None:
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 10 or h < 10:
            w, h = 140, 28
        canvas.delete("all")
        mid = h / 2
        audio = np.asarray(audio).reshape(-1)
        if audio.size == 0:
            # linha plana
            canvas.create_line(4, mid, w - 4, mid, fill="#3a3a4a", width=1)
            return
        peak = max(0.02, float(np.max(np.abs(audio))))
        n = min(audio.size, w * 3)
        step = max(1, audio.size // n)
        amp = h / 2 - 3
        pts = []
        for i in range(0, audio.size, step):
            x = 4 + (w - 8) * i / audio.size
            val = float(audio[i]) / peak
            y = mid - val * amp
            pts.append((x, y))
        if len(pts) < 2:
            pts = [(4, mid), (w - 4, mid)]
        canvas.create_line(*[c for p in pts for c in p], fill=ACCENT, width=2, smooth=True)

    # -- configurações ----------------------------------------------------
    def open_settings(self) -> None:
        def f():
            SettingsWindow(self.root, self.cfg, self.engine_getter, self)
        self._call(f)


class SettingsWindow:
    """Janela de configurações — minimalista."""

    def __init__(self, root: ctk.CTk, cfg: Config, engine_getter, overlay: Overlay):
        self.cfg = cfg
        self.engine_getter = engine_getter
        self.overlay = overlay
        self._input_devices = self._query_devices()

        self.win = ctk.CTkToplevel(root)
        self.win.title("Flow Local — Configurações")
        self.win.resizable(False, False)

        body = ctk.CTkFrame(self.win, corner_radius=0, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)

        self._section(body, "Atalho de ditado")
        self.hotkey_var = tk.StringVar(value=cfg.hotkey)
        self.mode_var = tk.StringVar(value=cfg.hotkey_mode)
        self.preset_var = tk.StringVar(value=self._preset_for(cfg))
        self.preset_menu = ctk.CTkOptionMenu(body, values=PRESET_LABELS, variable=self.preset_var,
                                             command=self._on_preset, width=230)
        self.preset_menu.pack(anchor="w", pady=(2, 6))
        self._hotkey_entry = ctk.CTkEntry(body, textvariable=self.hotkey_var, width=230,
                                          placeholder_text="ex.: ctrl+alt+f7")
        self._hotkey_entry.pack(anchor="w", pady=(0, 6))
        self._hotkey_entry.configure(state="disabled" if self.preset_var.get() != "Personalizado…" else "normal")
        self._label(body, "Modo:")
        for value, label in MODES:
            ctk.CTkRadioButton(body, text=label, variable=self.mode_var, value=value,
                               command=self._sync_preset).pack(anchor="w", pady=1)

        self._section(body, "Transcrição")
        self._combo(body, "Modelo do Whisper:", MODELS, "model")
        self._combo(body, "Idioma:", LANGUAGES, "language")
        self._label(body, "Como inserir o texto:")
        self.output_var = tk.StringVar(value=cfg.output_mode)
        for value, label in OUTPUT_MODES.items():
            ctk.CTkRadioButton(body, text=label, variable=self.output_var, value=value).pack(anchor="w", pady=1)
        self._label(body, "Microfone:")
        names = ["Padrão do sistema"] + [n for _, n in self._input_devices]
        self.device_var = tk.StringVar(value=self._device_name_for(cfg))
        ctk.CTkOptionMenu(body, values=names, variable=self.device_var, width=230).pack(anchor="w", pady=(2, 10))

        self._section(body, "Interface")
        self.floating_var = tk.BooleanVar(value=cfg.floating)
        ctk.CTkSwitch(body, text="Barra flutuante (minimalista, estilo Wispr Flow)",
                      variable=self.floating_var, command=self._on_floating_toggle).pack(anchor="w")

        self._section(body, "Apoie o projeto 💚")
        ctk.CTkLabel(body, text="Chave Pix:", text_color=MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(0, 4))
        pix_row = ctk.CTkFrame(body, fg_color="transparent")
        pix_row.pack(fill="x", pady=(0, 4))
        self.pix_var = tk.StringVar(value=cfg.pix_key)
        self.pix_entry = ctk.CTkEntry(pix_row, textvariable=self.pix_var, width=230,
                                      placeholder_text="sua chave Pix aqui")
        self.pix_entry.pack(side="left")
        ctk.CTkButton(pix_row, text="Copiar", width=80, command=self._copy_pix).pack(side="left", padx=(6, 0))
        self.pix_msg = ctk.CTkLabel(body, text="", text_color=GREEN, font=ctk.CTkFont(size=12))
        self.pix_msg.pack(anchor="w")

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(16, 0))
        ctk.CTkButton(buttons, text="Salvar", width=110, command=self._save).pack(side="right")
        self.msg = ctk.CTkLabel(body, text="", text_color=GREEN, font=ctk.CTkFont(size=12))
        self.msg.pack(anchor="e", pady=(6, 0))

        self.win.transient(root)
        self.win.grab_set()
        self.win.focus_force()
        self.win.after(60, lambda: (self.win.lift(), self.win.focus_force()))

    # -- helpers ----------------------------------------------------------
    def _section(self, parent, title: str) -> None:
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ACCENT).pack(anchor="w", pady=(12, 6))

    def _label(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, text_color="#c9c9d8", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(2, 0))

    def _combo(self, parent, text: str, values: list[str], attr: str) -> None:
        self._label(parent, text)
        var = tk.StringVar(value=getattr(self.cfg, attr))
        setattr(self, f"{attr}_var", var)
        ctk.CTkOptionMenu(parent, values=values, variable=var, width=230).pack(anchor="w", pady=(2, 8))

    def _query_devices(self) -> list[tuple[int, str]]:
        try:
            return [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
        except Exception:
            return []

    def _device_name_for(self, cfg: Config) -> str:
        if cfg.device is not None:
            for idx, name in self._input_devices:
                if idx == cfg.device:
                    return name
        return "Padrão do sistema"

    def _preset_for(self, cfg: Config) -> str:
        for label, hotkey, mode in HOTKEY_PRESETS:
            if hotkey is not None and hotkey == cfg.hotkey and mode == cfg.hotkey_mode:
                return label
        return "Personalizado…"

    def _on_preset(self, label: str) -> None:
        for lab, hotkey, mode in HOTKEY_PRESETS:
            if lab == label and hotkey is not None:
                self.hotkey_var.set(hotkey)
                self.mode_var.set(mode)
                break
        self._hotkey_entry.configure(state="disabled" if label != "Personalizado…" else "normal")

    def _sync_preset(self) -> None:
        for lab, hotkey, mode in HOTKEY_PRESETS:
            if hotkey == self.hotkey_var.get() and mode == self.mode_var.get():
                self.preset_var.set(lab)
                return
        self.preset_var.set("Personalizado…")
        self._hotkey_entry.configure(state="normal")

    def _on_floating_toggle(self) -> None:
        self.overlay.set_floating(self.floating_var.get())

    def _copy_pix(self) -> None:
        value = self.pix_var.get().strip()
        if not value:
            self.pix_msg.configure(text="Adicione sua chave Pix primeiro.", text_color="#ffd60a")
            return
        pyperclip.copy(value)
        self.pix_msg.configure(text="Copiado! ✓", text_color=GREEN)

    def _save(self) -> None:
        self.cfg.model = self.model_var.get()
        self.cfg.language = self.language_var.get()
        self.cfg.hotkey = self.hotkey_var.get().strip().lower()
        self.cfg.hotkey_mode = self.mode_var.get()
        self.cfg.output_mode = self.output_var.get()
        self.cfg.pix_key = self.pix_var.get().strip()
        self.cfg.floating = self.floating_var.get()
        name = self.device_var.get()
        self.cfg.device = next((i for i, n in self._input_devices if n == name), None) if name != "Padrão do sistema" else None
        self.cfg.save()
        self.engine_getter().reload()
        self.msg.configure(text="Salvo ✓")
        self.win.after(1200, self.win.destroy)
