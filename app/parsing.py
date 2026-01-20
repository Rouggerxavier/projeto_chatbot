import re
from typing import Optional, Tuple

from app.text_utils import norm, is_greeting, is_hours_question, is_cart_show_request, is_cart_reset_request
from app.preferences import CEP_REGEX

CHECKOUT_WORDS = ("finalizar", "fechar", "concluir", "confirmar", "encaminhar")

# Palavras que NÃO devem virar hint de produto
NON_HINT_WORDS = {
    "entrega", "retirada",
    "pix", "cartao", "cartão", "dinheiro",
    "bairro", "cep", "endereco", "endereço",
    "ok", "certo", "isso", "sim", "nao", "não",
    "pedido", "orcamento", "orçamento",
}

INTENT_WORDS = ("quero", "queria", "preciso", "precisando", "gostaria", "comprar", "pedido", "pedir", "to", "tô", "ta", "tá")

# Remove quantidades com unidades (em qualquer parte da frase)
QTY_ANYWHERE_RE = re.compile(
    r"\b\d+[,.]?\d*\s*(kg|quilo|quilos|g|grama|gramas|m3|m³|m2|m²|m|metro|metros|un|unidade|unidades|saco|sacos|rolo|rolos|l)\b"
)
# Remove multiplicadores tipo "4x" "2 x"
MULT_RE = re.compile(r"\b\d+\s*x\b")

STOPWORDS = {
    "de", "da", "do", "das", "dos",
    "para", "pra", "pro",
    "um", "uma", "uns", "umas",
    "tambem", "também",
    "ai", "aí", "por", "favor",
    "quero", "queria", "preciso", "precisando", "gostaria", "comprar", "pedido", "pedir",
    "no", "na", "nos", "nas",
    "com", "sem",
    "to", "tô", "ta", "tá",
    "obra",
}


def extract_kg_quantity(message: str) -> Optional[float]:
    t = norm(message)
    m = re.search(r"(\d+[,.]?\d*)\s*kg\b", t)
    return float(m.group(1).replace(",", ".")) if m else None


def extract_units_quantity(message: str) -> Optional[float]:
    t = norm(message)
    m = re.search(r"(\d+[,.]?\d*)\s*(saco|sacos|un|unidade|unidades)\b", t)
    return float(m.group(1).replace(",", ".")) if m else None


def extract_plain_number(message: str) -> Optional[float]:
    t = norm(message)
    if re.fullmatch(r"\d+[,.]?\d*", t):
        return float(t.replace(",", "."))
    return None


def packaging_kg_in_name(prod_name: str) -> Optional[int]:
    n = norm(prod_name)
    m = re.search(r"\b(20|25|50)\s*kg\b", n) or re.search(r"\b(20|25|50)kg\b", n)
    return int(m.group(1)) if m else None


def suggest_units_from_packaging(prod_name: str, kg_qty: float) -> Optional[Tuple[float, str]]:
    pkg = packaging_kg_in_name(prod_name)
    if not pkg:
        return None
    units = kg_qty / float(pkg)
    units_rounded = round(units)
    if abs(units - units_rounded) < 1e-6:
        units = float(units_rounded)
    return units, f"{kg_qty:.0f}kg ≈ {units:.0f} saco(s) de {pkg}kg"


def extract_product_hint(message: str) -> Optional[str]:
    """
    Extrai um 'hint' (texto curto) do que o usuário quer comprar.

    Exemplos:
      - "cimento 200kg" -> "cimento"
      - "quero 4 sacos de cimento cp ii" -> "cimento cp ii"
      - "finalizar" -> None
      - "58036-130" -> None
      - "entrega e pix" -> None
      - "bom dia" -> None
    """
    if not message:
        return None

    # nunca tentar produto em saudações / horário / carrinho
    if is_greeting(message) or is_hours_question(message) or is_cart_show_request(message) or is_cart_reset_request(message):
        return None

    txt = norm(message)
    if not txt:
        return None

    # checkout nunca vira produto
    if any(w in txt for w in CHECKOUT_WORDS):
        return None

    # cep/endereço nunca vira produto
    if CEP_REGEX.search(message or ""):
        return None

    # mensagens curtas só de preferências/fluxo
    if txt in NON_HINT_WORDS or all(tok in NON_HINT_WORDS for tok in txt.split()):
        return None

    # pega o que vem depois de “quero/preciso…”, senão usa a frase inteira
    m = re.search(rf"\b({'|'.join(INTENT_WORDS)})\b\s+(.*)$", txt)
    rest = m.group(2).strip() if m else txt

    # corta em entrega/pagamento (o que vem depois geralmente é preferência)
    rest = re.split(r"\b(entrega|retirada|pix|cartao|cartão|dinheiro|bairro|cep|endereco|endereço)\b", rest)[0].strip()

    # remove multiplicadores "4x"
    rest = MULT_RE.sub(" ", rest)

    # remove quantidades com unidade em qualquer lugar: "cimento 200kg", "areia 3m3", "trena 5m"
    rest = QTY_ANYWHERE_RE.sub(" ", rest)

    # remove números soltos
    rest = re.sub(r"\b\d+[,.]?\d*\b", " ", rest)

    # limpa espaços
    rest = re.sub(r"\s+", " ", rest).strip()
    if not rest:
        return None

    # tokens simples (remove stopwords)
    tokens = []
    for tok in rest.split():
        if tok in STOPWORDS:
            continue
        if tok in NON_HINT_WORDS:
            continue
        if len(tok) <= 1:
            continue
        tokens.append(tok)

    if not tokens:
        return None

    hint = " ".join(tokens[:6]).strip()

    # segurança extra: se por algum motivo virar cumprimento, não retorna
    if hint in ("bom dia", "boa tarde", "boa noite", "oi", "ola", "olá"):
        return None

    return hint
