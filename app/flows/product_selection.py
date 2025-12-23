from typing import Optional

from app.session_state import get_state, patch_state
from app.product_search import db_get_product_by_id, parse_choice_indices

from .quantity import set_pending_for_qty


def handle_suggestions_choice(session_id: str, message: str) -> Optional[str]:
    st = get_state(session_id)
    suggestions = st.get("last_suggestions") or []
    if not suggestions:
        return None

    # parse_choice_indices retorna 1-based
    indices_1based = parse_choice_indices(message, max_n=len(suggestions))
    if not indices_1based:
        return None

    idx0 = indices_1based[0] - 1
    if idx0 < 0 or idx0 >= len(suggestions):
        return None

    chosen_id = suggestions[idx0]["id"]
    requested_kg = st.get("last_requested_kg")

    patch_state(session_id, {"last_suggestions": [], "last_hint": None, "last_requested_kg": None})

    produto = db_get_product_by_id(int(chosen_id))
    if not produto:
        return "Não consegui localizar essa opção agora. Pode tentar de novo?"

    return set_pending_for_qty(session_id, produto, requested_kg=requested_kg)
