"""Reproduz o fluxo do app: inicia engine + UI, abre Configurações, verifica."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flow.config import Config  # noqa: E402
from flow.engine import DictationEngine  # noqa: E402
from flow.overlay import Overlay  # noqa: E402

cfg = Config(model="tiny", language="pt")
engine_ref: dict = {}
ov = Overlay(cfg, lambda: engine_ref["engine"])
engine = DictationEngine(cfg, ov)
engine_ref["engine"] = engine
engine.start()
time.sleep(2.0)

# 1. botão flutuante deve estar visível
assert ov.win is not None and ov.win.winfo_ismapped(), "bolha flutuante não apareceu"
print("1. bolha flutuante OK")

# 2. abre Configurações (como o clique no menu/ícone faz)
ov.open_settings()
time.sleep(1.5)

# procura a janela de configurações entre os Toplevels do root
settings_win = None
for child in ov.root.winfo_children():
    if isinstance(child, type(ov.root)) and child is not ov.win:
        settings_win = child
if settings_win is None or not settings_win.winfo_viewable():
    # tenta pegar a última Toplevel criada
    tops = [c for c in ov.root.winfo_children() if c.winfo_class() == "Toplevel"]
    print("toplevels:", [c.winfo_class() for c in tops], "viewable:", [c.winfo_viewable() for c in tops])
    if not tops or not any(c.winfo_viewable() for c in tops):
        print("ERRO: janela de configurações NÃO abriu")
        sys.exit(1)
print("2. Configurações abriu OK")

# 3. erro pendente na fila da UI? (a thread Tk registra em flow-local-error.log)
ov.root.update()
time.sleep(0.5)
log = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flow-local-error.log")
if os.path.exists(log):
    print("ERRO: há log de erro da UI:")
    print(open(log, encoding="utf-8").read()[-1500:])
    sys.exit(1)
print("3. sem erros na thread da UI")
print("TUDO OK")
os._exit(0)
