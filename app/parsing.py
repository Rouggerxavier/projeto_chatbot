import re
from typing import Optional, Tuple
from app.text_utils import norm
from app.preferences import CEP_REGEX

CHECKOUT_WORDS = ("finalizar", "fechar", "concluir", "confirmar")

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
    txt = norm(message)

    # ✅ checkout nunca vira produto
    if any(w in txt for w in CHECKOUT_WORDS):
        return None

    # ✅ cep/endereço nunca vira produto
    if CEP_REGEX.search(message or ""):
        return None

    # pega o que vem depois de “quero/preciso…”
    m = re.search(r"\b(quero|queria|preciso|gostaria|comprar|pedido)\b\s+(.*)$", txt)
    rest = m.group(2) if m else txt

    # remove coisas de entrega/pagamento
    rest = re.split(r"\b(entrega|retirada|pix|cartao|cartão|dinheiro)\b", rest)[0].strip()

    # remove quantidades no começo
    rest = re.sub(r"^\d+[,.]?\d*\s*(kg|quilo|quilos|m|m3|m³|saco|sacos|un|unidade|unidades)\s*(de\s+)?", "", rest).strip()

    # tokens simples
    tokens = [t for t in rest.split() if len(t) > 1 and not re.fullmatch(r"\d+[,.]?\d*", t)]
    if not tokens:
        return None
    return " ".join(tokens[:6]).strip()
