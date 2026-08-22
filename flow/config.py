"""Configuração do app, salva em JSON ao lado do projeto."""
import json
import os
import sys
import re
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
    version: int = 3
    model: str = "base"            # tamanho do modelo Whisper
    language: str = "pt"           # "auto" ou código de idioma (ex.: "pt", "en")
    hotkey: str = "ctrl+win"
    hotkey_mode: str = "hold"
    output_mode: str = "paste"
    vocabulary: str = ""           # nomes, siglas e termos preferidos
    corrections: dict[str, str] | None = None  # fala reconhecida -> forma preferida
    review_before_insert: bool = False  # permite corrigir e ensinar antes de colar
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
                if not isinstance(cfg.corrections, dict):
                    cfg.corrections = {}
                return cfg
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    def learned_vocabulary(self) -> str:
        """Contexto adicional para o Whisper, mantido pequeno e privado."""
        words = [self.vocabulary.strip()]
        words.extend(str(value).strip() for value in (self.corrections or {}).values())
        unique: list[str] = []
        seen: set[str] = set()
        for word in words:
            key = word.casefold()
            if word and key not in seen:
                unique.append(word)
                seen.add(key)
        return ", ".join(unique)[:1800]

    def apply_corrections(self, text: str) -> str:
        """Aplica somente correções que o usuário confirmou explicitamente."""
        for wrong, right in sorted((self.corrections or {}).items(), key=lambda pair: len(pair[0]), reverse=True):
            wrong, right = wrong.strip(), right.strip()
            if wrong and right:
                text = re.sub(rf"(?<!\\w){re.escape(wrong)}(?!\\w)", right, text, flags=re.IGNORECASE)
        return text

    def learn_corrections(self, original: str, revised: str) -> int:
        """Extrai trocas simples entre a versão ouvida e a corrigida.

        Não aprende frases inteiras: registra apenas trechos alterados, que são
        mais úteis e reduzem o risco de trocar texto indevidamente no futuro.
        """
        from difflib import SequenceMatcher

        original_words, revised_words = original.split(), revised.split()
        changes = 0
        learned = dict(self.corrections or {})
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, original_words, revised_words).get_opcodes():
            if tag != "replace":
                continue
            wrong = " ".join(original_words[i1:i2]).strip()
            right = " ".join(revised_words[j1:j2]).strip()
            if wrong and right and wrong.casefold() != right.casefold() and len(wrong) <= 80 and len(right) <= 80:
                learned[wrong] = right
                changes += 1
        # Evita que um uso muito longo gere um arquivo de configuração sem limite.
        self.corrections = dict(list(learned.items())[-300:])
        return changes
