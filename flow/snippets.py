"""Snippets: fale o atalho e o texto pronto aparece.

Dito "snippet agenda" no meio do ditado -> o corpo do snippet é inserido no
lugar de "snippet agenda". Regras:

- o marcador é a palavra "snippet" (PT e EN), seguida do nome;
- o nome casa sem diferenciar maiúsculas/acentos ("AGENDA" == "agenda");
- nomes com várias palavras são tentados do mais longo para o mais curto;
- nome desconhecido: o texto fica como está (nada some);
- a expansão roda DEPOIS dos comandos por voz, então o corpo do snippet é
  texto final e nunca é reprocessado como comando.
"""
from .commands import WORD_RE, _norm, _tokenize

MARKER = "snippet"
MAX_NAME_WORDS = 8


def _name_key(name: str) -> str:
    """Normaliza o nome de um snippet para casar com o falado."""
    words = [_norm(word) for word in WORD_RE.findall(name)]
    return " ".join(words)


def expand_snippets(text: str, snippets: dict[str, str] | None) -> tuple[str, int]:
    """Devolve (texto, quantidade_de_expansões)."""
    if not text or not snippets:
        return text, 0
    table: dict[str, str] = {}
    for name, body in snippets.items():
        key = _name_key(str(name))
        if key and str(body).strip():
            table[key] = str(body)
    if not table:
        return text, 0

    tokens = _tokenize(text)
    word_tokens = [token for token in tokens if token[3]]

    parts: list[str] = []
    cursor = 0
    expanded = 0
    index = 0
    while index < len(word_tokens):
        token = word_tokens[index]
        if _norm(token[0]) == MARKER:
            following = word_tokens[index + 1 : index + 1 + MAX_NAME_WORDS]
            body, matched = None, 0
            for length in range(len(following), 0, -1):
                key = " ".join(_norm(item[0]) for item in following[:length])
                if key in table:
                    body, matched = table[key], length
                    break
            if body is not None:
                start, end = token[1], following[matched - 1][2]
                parts.append(text[cursor:start])
                parts.append(body)
                cursor = end
                expanded += 1
                index += 1 + matched
                continue
        index += 1
    parts.append(text[cursor:])
    return "".join(parts), expanded
