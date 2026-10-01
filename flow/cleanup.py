"""Limpeza do texto ditado — "edita enquanto você fala".

Regras locais e determinísticas, sem rede e sem modelo extra:
- remove muletas de fala (fillers) como "hum", "ah", "um,"
- deduplica frases repetidas e palavras repetidas em sequência
- capitaliza o início de cada frase

O objetivo é reduzir edições manuais: o texto sai pronto para enviar.
Ativado/desativado por Config.smart_cleanup.
"""
import re

# Muletas por idioma. Cuidado com palavras comuns: em português "um"/"uma"
# são artigos e "é" é verbo — nunca entram na lista.
_FILLERS_PT = {"ah", "ahn", "eh", "hum", "hmm", "hm", "ham"}
_FILLERS_EN = {"um", "umm", "ummm", "uh", "uhh", "hmm", "hm", "mmm", "ah", "er", "erm", "eh"}
# Em "auto" (idioma desconhecido) usamos só o conjunto neutro — sem "um",
# que em português é artigo e sumiria com "um carro".
_FILLERS_NEUTRAL = (_FILLERS_PT | _FILLERS_EN) - {"um", "umm", "ummm"}

_FILLERS = {"pt": _FILLERS_PT, "en": _FILLERS_EN, "auto": _FILLERS_NEUTRAL}


def _filler_pattern(language: str) -> re.Pattern:
    words = sorted(_FILLERS.get(language, _FILLERS_NEUTRAL), key=len, reverse=True)
    alternatives = "|".join(re.escape(word) for word in words)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def remove_fillers(text: str, language: str = "pt") -> str:
    if not text:
        return text
    text = _filler_pattern(language).sub(" ", text)
    # pontuação órfã que sobra onde estava o filler (ex.: ", então")
    text = re.sub(r"(^|\n)[ \t]*[,;:.!?…]+[ \t]*", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,;:.!?…])", r"\1", text)
    return text.strip()


def _sentence_key(part: str) -> str:
    return re.sub(r"[^\w\s]", "", part).strip().casefold()


def dedupe(text: str) -> str:
    """Remove repetições típicas do Whisper (frases e palavras repetidas)."""
    if not text:
        return text

    # linhas idênticas adjacentes (frase a frase, parágrafo a parágrafo)
    lines: list[str] = []
    for line in text.split("\n"):
        key = _sentence_key(line)
        if lines and key and key == _sentence_key(lines[-1]):
            continue
        lines.append(line)
    text = "\n".join(lines)

    # frases idênticas adjacentes ("Vou lá. Vou lá." -> "Vou lá.")
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        key = _sentence_key(sentence)
        if kept and key and key == _sentence_key(kept[-1]):
            continue
        kept.append(sentence)
    text = " ".join(kept)

    # 3+ palavras idênticas seguidas ("eu eu eu gosto" -> "eu gosto").
    # Duas ocorrências podem ser legítimas ("que que", "had had").
    text = re.sub(r"\b(\w+)(?:\s+\1){2,}\b", r"\1", text, flags=re.IGNORECASE)
    return re.sub(r" {2,}", " ", text).strip()


def capitalize_sentences(text: str, language: str = "pt") -> str:
    """Capitaliza o início de cada frase sem tocar no resto das palavras."""
    if not text:
        return text

    def _upper(match: re.Match) -> str:
        return match.group(1) + match.group(2) + match.group(3).upper()

    text = re.sub(r"(^|[.!?…][\"'“‘)\]]*[ \t]+)([\"'“‘(]*)([a-zà-ÿ])", _upper, text)
    text = re.sub(r"(\n[ \t]*)([\"'“‘(]*)([a-zà-ÿ])", _upper, text)
    if language == "en":
        # pronome "i" isolado vira "I" (ex.: "and i think" -> "and I think")
        text = re.sub(r"(?<!\w)i(?!\w)", "I", text)
    return text


def cleanup(text: str, language: str = "pt") -> str:
    """Pipeline completo de limpeza, na ordem em que deve ser aplicado."""
    if not text:
        return text
    text = remove_fillers(text, language)
    text = dedupe(text)
    return capitalize_sentences(text, language)
