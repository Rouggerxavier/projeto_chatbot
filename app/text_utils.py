import re
import unicodedata
from app.constants import FORBIDDEN_REPLY_REGEX, GREETINGS, CART_SHOW_KEYWORDS, CART_RESET_KEYWORDS, INTENT_KEYWORDS

def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join([c for c in s if not unicodedata.combining(c)])

def norm(s: str) -> str:
    s = strip_accents((s or "").lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("cpii", "cp ii").replace("cp2", "cp ii")
    s = s.replace("cpiii", "cp iii").replace("cp3", "cp iii")
    return s

def sanitize_reply(text: str) -> str:
    if not text:
        return text
    if not FORBIDDEN_REPLY_REGEX.search(text):
        return text
    kept = []
    for ln in text.splitlines():
        if FORBIDDEN_REPLY_REGEX.search(ln):
            continue
        kept.append(ln)
    cleaned = "\n".join(kept).strip()
    if not cleaned:
        cleaned = "Certo! Me diga qual produto e quantidade você quer."
    cleaned += "\n\nObs.: Eu não envio e-mail nem rastreio; eu apenas monto o orçamento/pedido aqui no chat."
    return cleaned

def is_greeting(message: str) -> bool:
    t = norm(message)
    if t in GREETINGS:
        return True
    return any(t.startswith(g) and len(t) <= len(g) + 2 for g in GREETINGS)

def is_cart_show_request(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in CART_SHOW_KEYWORDS)

def is_cart_reset_request(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in CART_RESET_KEYWORDS)

def has_product_intent(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in INTENT_KEYWORDS)

def is_hours_question(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in ["horario", "hora", "funciona", "aberto", "fechado"])
