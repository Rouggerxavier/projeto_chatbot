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
