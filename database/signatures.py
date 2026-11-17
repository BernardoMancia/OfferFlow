from __future__ import annotations

import re
import unicodedata

_SIG_STOPWORDS = {
    "de",
    "da",
    "do",
    "das",
    "dos",
    "para",
    "com",
    "sem",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "um",
    "uma",
    "e",
    "ou",
    "a",
    "o",
    "as",
    "os",
    "nota",
    "fiscal",
    "nf",
    "nfe",
    "original",
    "oficial",
    "envio",
    "imediato",
    "pronta",
    "entrega",
    "promocao",
    "oferta",
    "desconto",
    "lancamento",
}


def build_title_signature(title: str) -> str:
    if not title:
        return ""
    nfkd = unicodedata.normalize("NFKD", title.lower())
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = re.sub(r"\bsmartphones?\b", "celular", clean)
    clean = re.sub(r"\bsmart\s+tv\b", "tv", clean)
    clean = re.sub(
        r"\b(?:air\s+fryer|fritadeira\s+eletrica|fritadeira\s+sem\s+oleo)\b",
        "airfryer",
        clean,
    )
    clean = re.sub(r"\b(\d+)\s*litros?\b", r"\1l", clean)
    clean = re.sub(r"\b(\d+)\s*ml\b", r"\1ml", clean)
    clean = re.sub(r"\b(\d+)\s*(?:gramas|gr|g)\b", r"\1g", clean)
    clean = re.sub(r"\b(\d+)\s*(?:unidades|unid|und|un)\b", r"\1un", clean)
    clean = re.sub(r"\b(\d+)\s*(?:polegadas|pol)\b", r"\1pol", clean)

    tokens = re.findall(r"[a-z0-9]+", clean)
    filtered = [
        t for t in tokens if t not in _SIG_STOPWORDS and (len(t) > 1 or t.isdigit())
    ]
    if not filtered:
        return " ".join(tokens[:6])
    return " ".join(filtered[:7])
