"""Insere o texto transcrito no aplicativo que estiver em foco.

Dois modos:
- "type":  digita caractere por caractere (como o Oiee).
- "paste": copia para a área de transferência e envia Ctrl+V — mais robusto
           com acentos em alguns apps.

Também executa as ações dos comandos por voz (apagar última palavra, mover
cursor etc.), sempre em relação ao cursor atual do app.
"""
import time

import keyboard
import pyperclip

# ação -> sequência de teclas
ACTION_KEYS = {
    "delete_last_word": ("ctrl+backspace",),
    "cursor_up": ("up",),
    "cursor_down": ("down",),
    "cursor_left": ("left",),
    "cursor_right": ("right",),
    "home": ("home",),
    "end": ("end",),
}


def type_text(text: str, mode: str = "paste") -> None:
    if not text:
        return
    if mode == "paste":
        _paste(text)
    else:
        _type_slow(text)


def apply_actions(actions: list[str]) -> None:
    """Executa ações de teclado na ordem (Ctrl+Backspace, setas, Home/End)."""
    for name in actions:
        for key in ACTION_KEYS.get(name, ()):
            keyboard.send(key)
            time.sleep(0.03)


def _type_slow(text: str, delay: float = 0.004) -> None:
    # quebras de linha viram Enter; um pequeno atraso evita perder caracteres
    # em apps que não aceitam rajadas rápidas de teclas.
    for i, part in enumerate(text.split("\n")):
        if i:
            keyboard.send("enter")
            time.sleep(delay)
        if part:
            keyboard.write(part, delay=delay)


def _paste(text: str) -> None:
    old = pyperclip.paste()
    try:
        pyperclip.copy(text)
        time.sleep(0.05)
        keyboard.send("ctrl+v")
    finally:
        # devolve a área de transferência ao estado anterior
        time.sleep(0.05)
        pyperclip.copy(old)
