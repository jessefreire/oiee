"""Oiee — ditado por voz 100% local.

Uso:  python main.py
Depois: segure a tecla configurada (padrão: Alt Direito), fale, solte —
o texto transcrito é digitado no aplicativo em foco.
"""
import os
import sys
import threading
import time

# Antes de importar o faster-whisper: desativa o backend "xet" do Hugging Face.
# O xet guarda os modelos em um armazenamento especial que pode ficar
# "materializando" o arquivo enquanto o app tenta abri-lo (erro "Unable to
# open file 'model.bin'"). Com o download clássico, o modelo é um arquivo
# pronto e estável — muito mais confiável no .exe.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from flow.config import Config, _base_dir
from flow.errors import log_exception
from flow.qt_app import FlowApplication
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# no .exe empacotado, fica ao lado do executável; senão, na raiz do projeto
LOCK_PATH = os.path.join(_base_dir(), ".oiee.lock")


_SINGLE_INSTANCE_MUTEX = None


def _acquire_single_instance() -> bool:
    """Impede duas instâncias do app (senão os hooks de teclado brigam).

    No Windows usa um mutex nomeado do kernel (canônico e confiável); em
    outras plataformas, um arquivo de lock com PID.
    """
    global _SINGLE_INSTANCE_MUTEX
    if sys.platform == "win32":
        import ctypes

        # ``ctypes.windll`` não preserva GetLastError de forma confiável entre
        # chamadas. Sem ``use_last_error=True``, duas instâncias podiam passar
        # por este teste e disputar o hook global do teclado.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        ctypes.set_last_error(0)
        _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, "Oiee_SingleInstance")
        # ERROR_ALREADY_EXISTS = 183: outra instância já criou o mutex
        return bool(_SINGLE_INSTANCE_MUTEX) and ctypes.get_last_error() != 183
    # fallback não-Windows: lock com PID
    if os.path.exists(LOCK_PATH):
        try:
            with open(LOCK_PATH, encoding="utf-8") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # levanta OSError se o processo não existe
        except (OSError, ValueError):
            pass  # lock velho de um processo morto: pode prosseguir
        else:
            return False
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return True


def _release_lock() -> None:
    if sys.platform == "win32":
        return  # o mutex é liberado quando o processo termina
    try:
        os.remove(LOCK_PATH)
    except OSError:
        pass


def main() -> None:
    if not _acquire_single_instance():
        return  # já existe outra instância rodando
    cfg = Config.load()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    flow = FlowApplication(app, cfg)

    # flags de depuração (usadas nos testes do .exe congelado)
    if "--debug-mark" in sys.argv:
        try:
            with open(os.path.join(_base_dir(), "debug-argv.txt"), "w", encoding="utf-8") as f:
                f.write(repr(sys.argv))
        except OSError:
            pass
    if "--debug-settings" in sys.argv:
        QTimer.singleShot(3000, flow.open_settings)
    if "--debug-dictate" in sys.argv:
        def _debug_dictate() -> None:
            flow.engine.toggle()
            time.sleep(3)
            flow.engine.toggle()
        threading.Timer(3.0, _debug_dictate).start()

    def quit_app() -> None:
        flow.close()
        _release_lock()
        # encerramento simples: o processo não tem estado para persistir
        os._exit(0)  # noqa: PLR1722

    app.aboutToQuit.connect(quit_app)
    app.exec()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # útil para usuários do .exe: o erro vai para um arquivo ao lado do app
        log_exception("main")
        raise
