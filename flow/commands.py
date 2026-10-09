"""Comandos por voz.

Depois da transcrição, o texto é varrido por frases de comando:
- pontuação explícita:  "vírgula" -> ",", "ponto final" -> ".", ...
- nova linha/parágrafo: "nova linha" -> "\\n", "novo parágrafo" -> "\\n\\n"
- ações de edição:      "apagar última palavra" -> Ctrl+Backspace,
                        "mover cursor para cima" -> seta para cima, ...

As ações viram teclas no app focado; o resto vira texto digitado.

A detecção é por tokens (palavras inteiras), insensível a maiúsculas e
acentos, e tolerante à pontuação que o Whisper já tiver inserido.
"""
import re
import unicodedata

WORD_RE = re.compile(r"\w+(?:['’]\w+)*")

# frases -> substituição. "action:<nome>" vira ação de teclado; senão, texto.
_COMMANDS_PT = [
    # pontuação (frases mais longas primeiro, para casar antes das curtas)
    ("ponto de interrogação", "?"),
    ("ponto de exclamação", "!"),
    ("ponto e vírgula", ";"),
    ("ponto final", "."),
    ("dois pontos", ":"),
    ("reticências", "…"),
    ("interrogação", "?"),
    ("exclamação", "!"),
    ("abre aspas", '"'),
    ("fecha aspas", '"'),
    ("vírgula", ","),
    ("barra", "/"),
    ("arroba", "@"),
    # linhas e parágrafos (viram texto, não teclas)
    ("nova linha", "\n"),
    ("quebrar linha", "\n"),
    ("novo parágrafo", "\n\n"),
    # edição
    ("apagar a última palavra", "action:delete_last_word"),
    ("apagar última palavra", "action:delete_last_word"),
    ("mover cursor para cima", "action:cursor_up"),
    ("mover cursor para baixo", "action:cursor_down"),
    ("mover cursor para a esquerda", "action:cursor_left"),
    ("mover cursor para a direita", "action:cursor_right"),
    ("cursor para cima", "action:cursor_up"),
    ("cursor para baixo", "action:cursor_down"),
    ("cursor para a esquerda", "action:cursor_left"),
    ("cursor para a direita", "action:cursor_right"),
    ("cursor para esquerda", "action:cursor_left"),
    ("cursor para direita", "action:cursor_right"),
    ("início da linha", "action:home"),
    ("fim da linha", "action:end"),
]

_COMMANDS_EN = [
    ("question mark", "?"),
    ("exclamation mark", "!"),
    ("full stop", "."),
    ("period", "."),
    ("semicolon", ";"),
    ("colon", ":"),
    ("ellipsis", "…"),
    ("comma", ","),
    ("slash", "/"),
    ("at sign", "@"),
    ("open quote", '"'),
    ("close quote", '"'),
    ("new line", "\n"),
    ("new paragraph", "\n\n"),
    ("delete the last word", "action:delete_last_word"),
    ("delete last word", "action:delete_last_word"),
    ("move cursor up", "action:cursor_up"),
    ("move cursor down", "action:cursor_down"),
    ("move cursor left", "action:cursor_left"),
    ("move cursor right", "action:cursor_right"),
    ("cursor up", "action:cursor_up"),
    ("cursor down", "action:cursor_down"),
    ("cursor left", "action:cursor_left"),
    ("cursor right", "action:cursor_right"),
    ("start of line", "action:home"),
    ("end of line", "action:end"),
]

_COMMANDS_ES = [
    ("punto de interrogación", "?"),
    ("signo de interrogación", "?"),
    ("punto de exclamación", "!"),
    ("signo de exclamación", "!"),
    ("punto y coma", ";"),
    ("punto final", "."),
    ("punto", "."),
    ("dos puntos", ":"),
    ("coma", ","),
    ("abrir comillas", '"'),
    ("cerrar comillas", '"'),
    ("barra", "/"),
    ("arroba", "@"),
    ("nueva línea", "\n"),
    ("nuevo párrafo", "\n\n"),
    ("borrar la última palabra", "action:delete_last_word"),
    ("borrar última palabra", "action:delete_last_word"),
    ("cursor arriba", "action:cursor_up"),
    ("cursor abajo", "action:cursor_down"),
    ("cursor izquierda", "action:cursor_left"),
    ("cursor derecha", "action:cursor_right"),
    ("inicio de la línea", "action:home"),
    ("final de la línea", "action:end"),
]

_COMMANDS_FR = [
    ("point d'interrogation", "?"),
    ("point interrogatif", "?"),
    ("point d'exclamation", "!"),
    ("point virgule", ";"),
    ("point final", "."),
    ("point", "."),
    ("deux points", ":"),
    ("virgule", ","),
    ("ouvrir les guillemets", '"'),
    ("fermer les guillemets", '"'),
    ("barre oblique", "/"),
    ("arobase", "@"),
    ("nouvelle ligne", "\n"),
    ("nouveau paragraphe", "\n\n"),
    ("effacer le dernier mot", "action:delete_last_word"),
    ("curseur vers le haut", "action:cursor_up"),
    ("curseur vers le bas", "action:cursor_down"),
    ("curseur vers la gauche", "action:cursor_left"),
    ("curseur vers la droite", "action:cursor_right"),
    ("début de la ligne", "action:home"),
    ("fin de la ligne", "action:end"),
]


_COMMANDS_DE = [
    ("fragezeichen", "?"),
    ("ausrufezeichen", "!"),
    ("semikolon", ";"),
    ("punkt", "."),
    ("doppelpunkt", ":"),
    ("auslassungspunkte", "…"),
    ("komma", ","),
    ("schrägstrich", "/"),
    ("at-zeichen", "@"),
    ("öffnende anführungszeichen", '"'),
    ("schließende anführungszeichen", '"'),
    ("neue zeile", "\n"),
    ("neuer absatz", "\n\n"),
    ("letztes wort löschen", "action:delete_last_word"),
    ("cursor nach oben", "action:cursor_up"),
    ("cursor nach unten", "action:cursor_down"),
    ("cursor nach links", "action:cursor_left"),
    ("cursor nach rechts", "action:cursor_right"),
    ("zeilenanfang", "action:home"),
    ("zeilenende", "action:end"),
]

_COMMANDS_IT = [
    ("punto interrogativo", "?"),
    ("punto esclamativo", "!"),
    ("punto e virgola", ";"),
    ("punto", "."),
    ("due punti", ":"),
    ("puntini di sospensione", "…"),
    ("virgola", ","),
    ("barra", "/"),
    ("chiocciola", "@"),
    ("apri virgolette", '"'),
    ("chiudi virgolette", '"'),
    ("nuova riga", "\n"),
    ("nuovo paragrafo", "\n\n"),
    ("cancella l'ultima parola", "action:delete_last_word"),
    ("cancella ultima parola", "action:delete_last_word"),
    ("cursore su", "action:cursor_up"),
    ("cursore giù", "action:cursor_down"),
    ("cursore a sinistra", "action:cursor_left"),
    ("cursore a destra", "action:cursor_right"),
    ("inizio riga", "action:home"),
    ("fine riga", "action:end"),
]

_COMMANDS_NL = [
    ("vraagteken", "?"),
    ("uitroepteken", "!"),
    ("puntkomma", ";"),
    ("punt", "."),
    ("dubbele punt", ":"),
    ("beletselteken", "…"),
    ("komma", ","),
    ("schuine streep", "/"),
    ("apenstaartje", "@"),
    ("open aanhalingsteken", '"'),
    ("sluit aanhalingsteken", '"'),
    ("nieuwe regel", "\n"),
    ("nieuwe alinea", "\n\n"),
    ("laatste woord wissen", "action:delete_last_word"),
    ("cursor omhoog", "action:cursor_up"),
    ("cursor omlaag", "action:cursor_down"),
    ("cursor naar links", "action:cursor_left"),
    ("cursor naar rechts", "action:cursor_right"),
    ("begin van de regel", "action:home"),
    ("einde van de regel", "action:end"),
]

# Idiomas sem tabela própria caem na PT (comandos são palavras exatas:
# raramente casam em outro idioma, e "arroba"/"barra" funcionam nos dois).
COMMANDS = {"pt": _COMMANDS_PT, "en": _COMMANDS_EN, "es": _COMMANDS_ES, "fr": _COMMANDS_FR,
            "de": _COMMANDS_DE, "it": _COMMANDS_IT, "nl": _COMMANDS_NL}


def _norm(word: str) -> str:
    word = unicodedata.normalize("NFKD", word)
    word = "".join(c for c in word if not unicodedata.combining(c))
    return word.lower()


def _tokenize(text: str) -> list[list]:
    """Tokens (palavra, start, end, é_palavra). Pontuação vira token separado."""
    tokens = []
    pos = 0
    for m in WORD_RE.finditer(text):
        if m.start() > pos:
            tokens.append([text[pos:m.start()], pos, m.start(), False])
        tokens.append([m.group(), m.start(), m.end(), True])
        pos = m.end()
    if pos < len(text):
        tokens.append([text[pos:], pos, len(text), False])
    return tokens


def polish(text: str) -> str:
    """Ajeita espaçamento: colapsa espaços, remove espaço antes de pontuação,
    garante espaço depois de vírgula/ponto, junta barras e arrobas."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*([,;:])(?=\S)", r"\1 ", text)            # espaço após , ; :
    text = re.sub(r"\s*([/:@])\s*", r"\1", text)                 # junta / e @
    text = re.sub(r"\s+([,;:.!?…])", r"\1", text)                # sem espaço antes
    text = re.sub(r"([.!?…])(?=[A-Za-zÀ-ÿ0-9(])", r"\1 ", text)  # espaço após .!?
    text = re.sub(r"([,;:.!?…])\1+", r"\1", text)                # sem pontuação dupla
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(" \t")


def parse_commands(text: str, language: str = "pt") -> tuple[str, list[str]]:
    """Separa comandos do texto ditado.

    Devolve (texto_limpo, ações): o que deve ser digitado e as ações de teclado
    (na ordem em que apareceram na fala).
    """
    if not text:
        return "", []
    table = COMMANDS.get(language, COMMANDS["pt"])

    tokens = _tokenize(text)
    word_idx = [i for i, t in enumerate(tokens) if t[3]]

    matches = []  # (start, end, substituição, frase)
    for phrase, repl in table:
        pwords = [_norm(w) for w in phrase.split()]
        n = len(pwords)
        for k in range(len(word_idx) - n + 1):
            idxs = word_idx[k : k + n]  # palavras consecutivas na fala
            if [_norm(tokens[i][0]) for i in idxs] == pwords:
                matches.append((tokens[idxs[0]][1], tokens[idxs[-1]][2], repl))

    matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))

    merged = []
    for m in matches:
        if merged and m[0] < merged[-1][1]:
            continue  # sobreposição: fica a primeira (frase mais longa)
        merged.append(m)

    parts = []
    actions = []
    cursor = 0
    for start, end, repl in merged:
        parts.append(text[cursor:start])
        if repl.startswith("action:"):
            actions.append(repl.removeprefix("action:"))
        else:
            parts.append(repl)
        cursor = end
    parts.append(text[cursor:])

    clean = polish("".join(parts))
    # comando puro com pontuação residual do Whisper (ex.: "apagar última palavra.")
    if clean and not any(c.isalnum() for c in clean) and "\n" not in clean:
        clean = ""
    return clean, actions
