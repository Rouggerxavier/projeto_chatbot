import re
from typing import Optional
from app.text_utils import norm
from app.session_state import get_state, patch_state

BAIRROS_ENTREGA = ["manaíra", "intermares", "aeroclube", "tambaú", "bessa"]
CEP_REGEX = re.compile(r"\b\d{5}-?\d{3}\b")


def detect_delivery_bairro(message: str) -> Optional[str]:
    t = norm(message)
    # aceita "bairro bessa" também
    if t.startswith("bairro "):
        t = t.replace("bairro ", "", 1).strip()

    for b in BAIRROS_ENTREGA:
        if b in t:
            return b
    return None


def maybe_register_address(message: str, session_id: str) -> bool:
    patch = {}
    raw = (message or "").strip()

    m = CEP_REGEX.search(raw)
    if m:
        cep = m.group(0).replace("-", "")
        patch["cep"] = f"{cep[:5]}-{cep[5:]}"

    t = norm(raw)
    if any(k in t for k in ["rua ", "av ", "avenida", "travessa", "alameda", "nº", "numero", "número"]):
        patch["endereco"] = raw

    b = detect_delivery_bairro(raw)
    if b:
        patch["bairro"] = b

    if patch:
        patch_state(session_id, patch)
        return True
    return False


def handle_preferences(message: str, session_id: str) -> bool:
    t = norm(message)
    st = get_state(session_id)
    patch = {}

    # entrega x retirada
    if "entrega" in t and st.get("preferencia_entrega") != "entrega":
        patch["preferencia_entrega"] = "entrega"

    if any(x in t for x in ["retirada", "retirar", "buscar na loja"]) and st.get("preferencia_entrega") != "retirada":
        patch["preferencia_entrega"] = "retirada"
        patch["bairro"] = None
        patch["cep"] = None
        patch["endereco"] = None

    # pagamento
    if "pix" in t and st.get("forma_pagamento") != "pix":
        patch["forma_pagamento"] = "pix"
    if any(x in t for x in ["cartao", "credito", "debito"]) and st.get("forma_pagamento") != "cartao":
        patch["forma_pagamento"] = "cartao"
    if "dinheiro" in t and st.get("forma_pagamento") != "dinheiro":
        patch["forma_pagamento"] = "dinheiro"

    # bairro (inclui "bairro bessa")
    b = detect_delivery_bairro(message)
    if b and st.get("bairro") != b:
        patch["bairro"] = b

    if patch:
        patch_state(session_id, patch)
        return True
    return False


def message_is_preferences_only(message: str, session_id: str) -> bool:
    """
    True quando a mensagem parece só atualizar preferências/endereço
    (sem intenção de produto).
    """
    st = get_state(session_id)

    # se estamos esperando quantidade, "sim" não pode ser interceptado aqui
    if st.get("awaiting_qty"):
        return False

    t = norm(message).strip()
    raw = (message or "").strip()

    # ack simples
    if t in {"ok", "certo", "beleza", "pronto", "isso"}:
        return True

    # CEP puro
    raw_no_space = raw.replace(" ", "")
    if CEP_REGEX.fullmatch(raw_no_space) is not None:
        return True

    # "bairro bessa"
    if t.startswith("bairro "):
        return True

    # bairro puro
    if t in BAIRROS_ENTREGA:
        return True

    # palavras de preferência
    if any(k in t for k in ["entrega", "retirada", "retirar", "buscar na loja", "pix", "cartao", "cartão", "dinheiro"]):
        return True

    # endereco (rua, avenida, etc) - verifica se maybe_register_address conseguiu capturar
    if any(k in t for k in ["rua ", "av ", "avenida", "travessa", "alameda"]):
        return True

    # numero de endereco (ex: "rua tal, 15" ou "numero 123")
    if any(k in t for k in ["nº", "numero", "número"]) or re.search(r",\s*\d+", raw):
        return True

    return False
