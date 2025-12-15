import re
import unicodedata

from app.constants import (
    FORBIDDEN_REPLY_REGEX,
    GREETINGS,
    CART_SHOW_KEYWORDS,
    CART_RESET_KEYWORDS,
    INTENT_KEYWORDS,
)


# Heurística simples para detectar quando a mensagem "parece um pedido" mesmo sem "quero".
# (coloque aqui o básico do seu domínio; isso reduz erros do tipo "bairro bessa" virar busca)
BASE_PRODUCT_WORDS = {
    "cimento", "areia", "brita", "tijolo", "bloco",
    "trena", "cabo", "fio", "cano", "pvc", "tinta",
    "massa", "argamassa", "rejunte", "parafuso", "prego", "pregos",
    "colher", "desempenadeira", "martelo", "serrote",
}

# Palavras que NÃO devem acionar busca de produto (preferências/fluxo)
NON_PRODUCT_WORDS = {
    "entrega", "retirada", "pix", "cartao", "cartão", "dinheiro",
    "bairro", "cep", "endereco", "endereço",
    "finalizar", "fechar", "checkout", "pedido", "ok", "certo",
}

QTY_UNITS_REGEX = re.compile(
    r"\b\d+([.,]\d+)?\s*(kg|quilo|quilos|g|grama|gramas|m3|m2|m|metro|metros|un|unidade|unidades|saco|sacos|rolo|rolos|l)\b"
)

CEP_REGEX_SIMPLE = re.compile(r"\b\d{5}-?\d{3}\b")


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join([c for c in s if not unicodedata.combining(c)])


def norm(s: str) -> str:
    s = strip_accents((s or "").lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # normalizações comuns pra cimento
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

    if not t:
        return True

    # exatamente igual aos greetings
    if t in GREETINGS:
        return True

    # pega variações como: "xbom dia", "bom diaaa", "bom dia!!"
    # regra: se começa com um cumprimento conhecido e a mensagem é curta, trata como cumprimento
    for g in GREETINGS:
        if t.startswith(g) and len(t) <= len(g) + 6:
            return True

    # caso específico: "x bom dia" ou "xbom dia"
    if re.match(r"^x+\s*(bom dia|boa tarde|boa noite)\b", t) and len(t.split()) <= 3:
        return True

    return False


def is_cart_show_request(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in CART_SHOW_KEYWORDS)


def is_cart_reset_request(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in CART_RESET_KEYWORDS)


def is_hours_question(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in ["horario", "hora", "funciona", "aberto", "fechado"])


def _looks_like_preferences_only(t: str) -> bool:
    # se a mensagem for só preferências (entrega/pix/cep/bairro), não é intenção de produto
    if any(w in t for w in ["pix", "cartao", "dinheiro", "entrega", "retirada", "bairro", "cep", "endereco"]):
        # mas se tiver também palavra de produto, deixa passar como produto
        if any(pw in t for pw in BASE_PRODUCT_WORDS):
            return False
        # ou se tiver quantidade e unidade + palavra de produto (já coberto acima)
        return True
    # se for basicamente um CEP
    if CEP_REGEX_SIMPLE.search(t) and len(t.split()) <= 2:
        return True
    return False


def has_product_intent(message: str) -> bool:
    t = norm(message)

    if not t:
        return False

    # Nunca considerar como produto se for cumprimento/horário/carrinho
    if is_greeting(message) or is_hours_question(message) or is_cart_show_request(message) or is_cart_reset_request(message):
        return False

    # Preferências/fluxo isolados não são produto
    if _looks_like_preferences_only(t):
        return False

    # Intenção explícita (ex.: "quero", "preciso", etc.)
    if any(k in t for k in INTENT_KEYWORDS):
        return True

    # Heurística: quantidade/unidade -> provavelmente pedido ("cimento 200kg", "areia 3m3", "trena 2 un")
    if QTY_UNITS_REGEX.search(t):
        return True

    # Heurística: contém palavra-base de produto ("cimento", "areia", "trena"...)
    if any(re.search(rf"\b{re.escape(w)}\b", t) for w in BASE_PRODUCT_WORDS):
        return True

    return False
