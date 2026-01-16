import re
import re
import unicodedata

from app.constants import (
    FORBIDDEN_REPLY_REGEX,
    GREETINGS,
    CART_SHOW_KEYWORDS,
    CART_RESET_KEYWORDS,
    INTENT_KEYWORDS,
)

from app.guardrails import apply_guardrails, SAFE_NOTE


# Heurística simples para detectar quando a mensagem "parece um pedido" mesmo sem "quero".
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


def _ensure_safe_note_once(text: str) -> str:
    if not text:
        return text
    if SAFE_NOTE.lower() in text.lower():
        return text
    return text.rstrip() + "\n\n" + SAFE_NOTE


def sanitize_reply(text: str) -> str:
    """
    Ordem:
    1) filtro legado por FORBIDDEN_REPLY_REGEX (remove linhas suspeitas/indesejadas)
    2) guardrails (remove claims tipo email/rastreio/qr pix e adiciona SAFE_NOTE se necessário)

    Importante: NÃO anexar nota duas vezes.
    """
    if not text:
        return text

    cleaned = text

    # 1) filtro legado (apenas remove linhas)
    if FORBIDDEN_REPLY_REGEX.search(cleaned):
        kept = []
        for ln in cleaned.splitlines():
            if FORBIDDEN_REPLY_REGEX.search(ln):
                continue
            kept.append(ln)
        cleaned = "\n".join(kept).strip()

        if not cleaned:
            cleaned = "Certo! Me diga qual produto e quantidade você quer."

    # 2) guardrails (pode remover e/ou anexar nota segura)
    cleaned, changed = apply_guardrails(cleaned)

    # Se o filtro legado removeu coisas mas guardrails não anexou nota,
    # ainda assim garantimos nota UMA vez para evitar “alucinação recorrente”.
    # (opcional, mas ajuda)
    if FORBIDDEN_REPLY_REGEX.search(text) and SAFE_NOTE.lower() not in cleaned.lower():
        cleaned = _ensure_safe_note_once(cleaned)

    return cleaned


def is_greeting(message: str) -> bool:
    t = norm(message)

    if not t:
        return True

    # igualzinho
    if t in GREETINGS:
        return True

    # variações curtas
    for g in GREETINGS:
        if t.startswith(g) and len(t) <= len(g) + 6:
            return True

    # "xbom dia" / "x bom dia"
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
    # Se for só preferências (entrega/pix/cep/bairro), não é produto
    if any(w in t for w in ["pix", "cartao", "dinheiro", "entrega", "retirada", "bairro", "cep", "endereco"]):
        # mas se também tiver palavra de produto, pode ser pedido
        if any(pw in t for pw in BASE_PRODUCT_WORDS):
            return False
        return True

    # se for basicamente um CEP
    if CEP_REGEX_SIMPLE.search(t) and len(t.split()) <= 2:
        return True

    return False


def is_consultive_question(message: str) -> bool:
    """
    Detecta se a mensagem é uma pergunta consultiva (ex: "serve pra laje?").

    Retorna True se for pergunta aberta sobre produtos/aplicações.
    Retorna False se for ação direta de compra ou preferência.
    """
    t = norm(message)

    if not t:
        return False

    # Nunca é consultiva se for ação explícita de compra/carrinho/checkout
    if is_greeting(message) or is_cart_show_request(message) or is_cart_reset_request(message):
        return False

    # Não é consultiva se for preferências isoladas
    if _looks_like_preferences_only(t):
        return False

    # Não é consultiva se tiver intenção EXPLÍCITA de compra
    if any(k in t for k in ["quero", "adiciona", "coloca", "vou levar", "me da", "preciso de"]):
        return False

    # Não é consultiva se tiver quantidade específica (ex: "2 sacos de cimento")
    if QTY_UNITS_REGEX.search(t):
        return False

    # PATTERNS CONSULTIVOS (perguntas abertas)
    consultive_patterns = [
        # Perguntas sobre uso/aplicação
        r"\b(serve|funciona|pode usar|posso usar|aplica|uso|usar)\b",
        # Perguntas comparativas
        r"\b(qual|melhor|diferenca|comparar|comparacao|escolher)\b",
        # Perguntas sobre características
        r"\b(e bom|e boa|e resistente|e duravel|qualidade|tipo)\b",
        # Perguntas sobre adequação
        r"\b(indicado|recomenda|adequado|ideal|apropriado)\b",
        # Perguntas gerais
        r"\b(como|onde|quando|porque|pra que|para que)\b",
    ]

    # Se tiver padrão consultivo + interrogação ou dúvida
    has_consultive_pattern = any(re.search(pat, t) for pat in consultive_patterns)
    has_question_marker = "?" in message or any(w in t for w in ["sera", "será", "talvez", "duvida"])

    if has_consultive_pattern or has_question_marker:
        # Confirma que tem alguma palavra relacionada a produto/construção
        has_product_context = (
            any(re.search(rf"\b{re.escape(w)}\b", t) for w in BASE_PRODUCT_WORDS) or
            any(w in t for w in ["laje", "parede", "piso", "teto", "banheiro", "cozinha", "area externa", "obra"])
        )

        if has_product_context or has_consultive_pattern:
            return True

    return False


def has_product_intent(message: str) -> bool:
    t = norm(message)

    if not t:
        return False

    # Nunca considerar produto se for cumprimento/horário
    if is_greeting(message) or is_hours_question(message):
        return False

    # Carrinho: só rejeitar se for APENAS visualização/reset (sem adicionar produto)
    if is_cart_reset_request(message):
        return False
    if is_cart_show_request(message) and not any(k in t for k in INTENT_KEYWORDS):
        return False

    # Preferências isoladas não são produto
    if _looks_like_preferences_only(t):
        return False

    # Se for literalmente só palavras "não-produto" (ex.: "pix", "entrega", "ok")
    tokens = set(t.split())
    if tokens and tokens.issubset(NON_PRODUCT_WORDS):
        return False

    # Se for pergunta consultiva, NÃO é intenção de compra
    if is_consultive_question(message):
        return False

    # Intenção explícita
    if any(k in t for k in INTENT_KEYWORDS):
        return True

    # Quantidade/unidade -> provavelmente pedido
    if QTY_UNITS_REGEX.search(t):
        return True

    # Contém palavra-base de produto
    if any(re.search(rf"\b{re.escape(w)}\b", t) for w in BASE_PRODUCT_WORDS):
        return True

    return False
