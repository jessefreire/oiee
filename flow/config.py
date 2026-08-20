"""Configuração do app, salva em JSON ao lado do projeto."""
import json
import os
import sys
from dataclasses import asdict, dataclass, fields


def _base_dir() -> str:
    """Diretório onde ficam config.json e logs.

    No .exe empacotado (PyInstaller onefile), __file__ aponta para a pasta
    temporária de extração (_MEIxxxxx), que é apagada ao fechar — por isso,
    nesse caso usamos o diretório do próprio executável.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CONFIG_PATH = os.path.join(_base_dir(), "config.json")

MODELS = ["tiny", "base", "small", "medium", "large-v3"]
LANGUAGES = ["auto", "pt", "en", "es", "fr", "de", "it", "ja", "zh", "ru"]
OUTPUT_MODES = {"type": "Digitar", "paste": "Colar (Ctrl+V)"}


@dataclass
class Config:
    version: int = 2
    model: str = "base"            # tamanho do modelo Whisper
    language: str = "pt"           # "auto" ou código de idioma (ex.: "pt", "en")
    hotkey: str = "ctrl+win"
    hotkey_mode: str = "hold"
    output_mode: str = "paste"
    vocabulary: str = ""           # nomes, siglas e termos preferidos
    beam_size: int = 3              # qualidade x velocidade da decodificação
    auto_gain: bool = True          # aumenta voz baixa com limite seguro
    device: int | None = None      # índice do dispositivo de entrada; None = padrão
    pix_key: str = ""              # chave Pix exibida no card de doação
    floating: bool = True           # mostra o botão flutuante de microfone
    floating_x: int | None = None   # posição do botão flutuante (None = padrão)
    floating_y: int | None = None

    @classmethod
    def load(cls) -> "Config":
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                valid = {field.name for field in fields(cls)}
                cfg = cls(**{k: v for k, v in data.items() if k in valid})
                if data.get("hotkey") == "ctrl":
                    cfg.hotkey, cfg.hotkey_mode = "ctrl+win", "toggle"
                if data.get("output_mode") not in OUTPUT_MODES:
                    cfg.output_mode = "paste"
                if cfg.model not in MODELS:
                    cfg.model = "base"
                if cfg.language not in LANGUAGES:
                    cfg.language = "pt"
                return cfg
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
