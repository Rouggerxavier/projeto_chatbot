import re
from typing import Optional, Tuple
from app.text_utils import norm


def extract_phone(message: str) -> Optional[str]:
    t = message or ""
    digits = re.sub(r"\D", "", t)
    if 10 <= len(digits) <= 13:
        return digits
    return None


def extract_delivery_preference(message: str) -> Optional[str]:
    """Extrai 'entrega' ou 'retirada' da mensagem."""
    t = norm(message or "")
    if "entrega" in t:
        return "entrega"
    if "retira" in t:
        return "retirada"
    return None


def extract_payment_method(message: str) -> Optional[str]:
    """Extrai 'pix', 'cartão' ou 'dinheiro' da mensagem."""
    t = norm(message or "")
    if "pix" in t:
        return "pix"
    if "cartao" in t or "cartão" in t:
        return "cartão"
    if "dinhe" in t:
        return "dinheiro"
    return None


def extract_name(message: str) -> Optional[str]:
    raw = (message or "").strip()
    if not raw or len(raw) > 160:
        return None

    def _clean_candidate(text: str) -> Optional[str]:
        cleaned = re.sub(r"[^A-Za-zÀ-ÿ\s'-]", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 2:
            return None
        stop_words = {
            "numero",
            "número",
            "telefone",
            "celular",
            "zap",
            "whatsapp",
            "entrega",
            "retirada",
            "pix",
            "cartao",
            "cartão",
            "dinheiro",
            "endereco",
            "endereço",
            "rua",
            "bairro",
            "cep",
            "e",
            "o",
            "a",
            "com",
            "em",
            "para",
        }
        filtered = []
        for tok in cleaned.split():
            norm_tok = norm(tok)
            if norm_tok not in stop_words and len(tok) >= 2:
                filtered.append(tok)
        candidate = " ".join(filtered).strip()
        if len(candidate) < 2 or not re.search(r"[A-Za-zÀ-ÿ]", candidate):
            return None
        if len(candidate) > 80:
            candidate = candidate[:80].rstrip()
        return candidate

    patterns = [
        r"meu\s+nome\s+e\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s'-]{0,78})",
        r"meu\s+nome\s+é\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s'-]{0,78})",
        r"me\s+cham[oa]\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s'-]{0,78})",
        r"eu\s+sou\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s'-]{0,78})",
        r"sou\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s'-]{0,78})",
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            cand = _clean_candidate(m.group(1))
            if cand:
                return cand

    if re.search(r"\d", raw):
        return None

    return _clean_candidate(raw)


def split_first_last(full_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not full_name:
        return None, None
    parts = full_name.strip().split()
    if not parts:
        return None, None
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else None
    return first, last
