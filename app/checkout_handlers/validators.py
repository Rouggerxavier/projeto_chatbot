from app.session_state import get_state
from app.cart_service import get_open_orcamento
from app.text_utils import norm


FINALIZE_INTENTS = [
    "finalizar",
    "fechar",
    "fechar pedido",
    "finalizar pedido",
    "fechar o pedido",
    "finalizar o pedido",
    "pode fechar",
    "pode finalizar",
    "confirmar",
]


def is_finalize_intent(message: str) -> bool:
    t = norm(message or "")
    return any(x in t for x in FINALIZE_INTENTS)


def ready_to_checkout(session_id: str) -> bool:
    st = get_state(session_id)

    orc = get_open_orcamento(session_id)
    if not orc:
        return False

    if not st.get("preferencia_entrega"):
        return False
    if not st.get("forma_pagamento"):
        return False

    # se entrega, exige endereço
    if st.get("preferencia_entrega") == "entrega":
        if not st.get("endereco"):
            return False

    # exige nome, email e telefone
    if not st.get("cliente_nome"):
        return False
    if not st.get("cliente_email"):
        return False
    if not st.get("cliente_telefone"):
        return False

    return True
