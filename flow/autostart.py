"""Iniciar com o Windows (chave HKCU ...\\CurrentVersion\\Run).

Só faz sentido no .exe instalado: em desenvolvimento (python main.py) não há
o que registrar. Toda operação é defensiva — falha de registro nunca deve
quebrar o app.
"""
import sys

APP_NAME = "Oiee"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def available() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def _command() -> str:
    return f'"{sys.executable}"'


def _open(write: bool = False):
    import winreg

    access = winreg.KEY_QUERY_VALUE | (winreg.KEY_SET_VALUE if write else 0)
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, access)


def is_enabled() -> bool:
    if not available():
        return False
    try:
        import winreg

        with _open() as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    if not available():
        return False
    try:
        if enabled:
            with _open(write=True) as key:
                import winreg

                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
        else:
            with _open(write=True) as key:
                import winreg

                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
