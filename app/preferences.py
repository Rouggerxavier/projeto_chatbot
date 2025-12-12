import re
from typing import Optional
from app.text_utils import norm
from app.session_state import get_state, patch_state

BAIRROS_ENTREGA = ["manaíra", "intermares", "aeroclube", "tambaú", "bessa"]
CEP_REGEX = re.compile(r"\b\d{5}-?\d{3}\b")

def detect_delivery_bairro(message: str) -> Optional[str]:
    t = norm(message)
    for b in BAIRROS_ENTREGA:
        if b in t:
            return b
    return None

def maybe_register_address(message: str, session_id: str) -> bool:
    st = get_state(session_id)
    patch = {}

    m = CEP_REGEX.search(message or "")
    if m:
        cep = m.group(0).replace("-", "")
        patch["cep"] = f"{cep[:5]}-{cep[5:]}"
    t = norm(message)
    if any(k in t for k in ["rua ", "av ", "avenida", "travessa", "alameda", "nº", "numero", "número"]):
        patch["endereco"] = (message or "").strip()

    if patch:
        patch_state(session_id, patch)
        return True
    return False

def handle_preferences(message: str, session_id: str) -> bool:
    t = norm(message)
    st = get_state(session_id)
    patch = {}

    # entrega/retirada
    if "entrega" in t and st.get("preferencia_entrega") != "entrega":
        patch["preferencia_entrega"] = "entrega"

    if any(x in t for x in ["retirada", "retirar", "buscar na loja"]) and st.get("preferencia_entrega") != "retirada":
        patch["preferencia_entrega"] = "retirada"
        # ✅ se mudou para retirada, não faz sentido ficar pedindo CEP/endereço
        patch["bairro"] = None
        patch["cep"] = None
        patch["endereco"] = None

    # pagamento
    if "pix" in t and st.get("forma_pagamento") != "pix":
        patch["forma_pagamento"] = "pix"
    if any(x in t for x in ["cartao", "cartão", "credito", "crédito", "debito", "débito"]) and st.get("forma_pagamento") != "cartão":
        patch["forma_pagamento"] = "cartão"
    if "dinheiro" in t and st.get("forma_pagamento") != "dinheiro":
        patch["forma_pagamento"] = "dinheiro"

    # bairro
    b = detect_delivery_bairro(message)
    if b and st.get("bairro") != b:
        patch["bairro"] = b

    if patch:
        patch_state(session_id, patch)
        return True
    return False

def message_is_preferences_only(message: str) -> bool:
    t = norm(message).strip()
    if t in {"ok", "certo", "beleza", "pronto", "isso", "sim"}:
        return True
    if CEP_REGEX.fullmatch((message or "").strip().replace(" ", "")) is not None:
        return True
    if t in BAIRROS_ENTREGA:
        return True
    if any(k in t for k in ["entrega", "retirada", "retirar", "buscar na loja", "pix", "cartao", "cartão", "dinheiro"]):
        return True
    return False
