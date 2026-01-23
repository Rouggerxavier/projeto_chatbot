from __future__ import annotations

import re
from typing import Optional

from app.text_utils import norm


NUM_WORDS = {
    "zero": 0,
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "três": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
}


def _parse_int_word(text: str) -> Optional[int]:
    t = norm(text)
    if t in NUM_WORDS:
        return NUM_WORDS[t]
    return None


def parse_expected_field(field: str, message: str) -> Optional[str]:
    """
    Tenta consumir a resposta do usuário para o campo esperado.
    Retorna string normalizada ou None se não conseguiu.
    """
    field = field or ""
    msg = message or ""
    t = norm(msg)

    # Quantidade (qty)
    if field in {"quantidade", "qty"}:
        # numero digitado
        m = re.search(r"\b\d+\b", t)
        if m:
            return m.group(0)
        # numero por extenso
        val = _parse_int_word(t)
        if val is not None:
            return str(val)
        return None

    # Bitola/diametro
    if field in {"bitola", "diametro"}:
        m = re.search(r"\b(\d{1,3}(?:[.,]\d{1,2})?)\s*(mm|cm|pol|\"|')?\b", msg, re.IGNORECASE)
        if not m:
            # tenta numero puro
            m = re.search(r"\b\d{1,3}\b", msg)
        if m:
            num = m.group(1) if len(m.groups()) >= 1 else m.group(0)
            unit = ""
            if len(m.groups()) >= 2:
                unit = m.group(2) or ""
            num = num.replace(",", ".")
            unit = unit.lower()
            if unit in {"", "mm"}:
                return f"{num}mm"
            if "pol" in unit or '"' in unit or "'" in unit:
                return f'{num}"'
            return f"{num}{unit}"
        # numero por extenso nao faz sentido para bitola -> None
        return None

    # fallback: se campo string e mensagem curta, aceita
    if len(t.split()) <= 4:
        return msg.strip()

    return None
