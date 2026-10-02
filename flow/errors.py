"""Log de erros do app.

O .exe roda sem console e a thread da UI pode morrer em silêncio — todo erro
é registrado em oiee-error.log (ao lado do executável) para diagnóstico.
"""
import os
import sys
import traceback


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log_path() -> str:
    return os.path.join(_base_dir(), "oiee-error.log")


def log_exception(context: str = "") -> None:
    """Grava a exceção atual em oiee-error.log (nunca levanta)."""
    try:
        from datetime import datetime
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(f"\n===== {context} ===== {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            f.write(traceback.format_exc())
    except Exception:
        pass
