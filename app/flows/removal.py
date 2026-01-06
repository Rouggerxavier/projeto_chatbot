from typing import Optional, List, Dict, Any

from app.session_state import get_state, patch_state
from app.cart_service import list_orcamento_items, remove_item_from_orcamento, format_orcamento
from app.text_utils import norm
from app.product_search import parse_choice_indices


def is_remove_intent(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in ["remover", "tirar", "excluir", "deletar", "retirar"]) or "tirar do" in t


def build_remove_options_text(options: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, opt in enumerate(options, start=1):
        lines.append(
            f"{idx}) {opt['nome']} - {opt['quantidade']:.0f} {opt['unidade']} (R$ {opt['subtotal']:.2f})"
        )
    return "\n".join(lines)


def start_remove_flow(session_id: str) -> str:
    items = list_orcamento_items(session_id)
    if not items:
        return "Seu orcamento esta vazio. Nao ha itens para remover."

    patch_state(
        session_id,
        {
            "awaiting_remove_choice": True,
            "remove_options": [
                {
                    "product_id": it["product_id"],
                    "nome": it["nome"],
                    "quantidade": it["quantidade"],
                    "unidade": it["unidade"],
                    "subtotal": it["subtotal"],
                }
                for it in items
            ],
        },
    )

    options_text = build_remove_options_text(items)
    return (
        "Quer remover algum item do orcamento? Se quiser, responda o numero correspondente. "
        "Se nao quiser remover nada, diga **nao**.\n\n" + options_text
    )


def handle_remove_choice(session_id: str, message: str) -> Optional[str]:
    st = get_state(session_id)
    if not st.get("awaiting_remove_choice"):
        return None

    opts: List[Dict[str, Any]] = st.get("remove_options") or []
    t = norm(message)

    if t in {"nao", "nenhum", "n"}:
        patch_state(session_id, {"awaiting_remove_choice": False, "remove_options": None})
        return "Certo, mantive todos os itens do orcamento."

    if not opts:
        patch_state(session_id, {"awaiting_remove_choice": False, "remove_options": None})
        return "Nao encontrei itens para remover agora."

    choice = parse_choice_indices(message, max_n=len(opts))
    if not choice:
        options_text = build_remove_options_text(opts)
        return (
            "Me diga o numero do item que quer remover ou responda **nao** para manter tudo.\n\n"
            + options_text
        )

    idx0 = choice[0] - 1
    if idx0 < 0 or idx0 >= len(opts):
        options_text = build_remove_options_text(opts)
        return (
            "Opcao invalida. Escolha um numero da lista ou responda **nao** para manter tudo.\n\n"
            + options_text
        )

    product_id = opts[idx0]["product_id"]
    max_qty = opts[idx0]["quantidade"]
    produto_nome = opts[idx0]["nome"]

    patch_state(session_id, {
        "awaiting_remove_choice": False,
        "remove_options": None,
        "awaiting_remove_qty": True,
        "pending_remove_product_id": product_id,
        "pending_remove_max_qty": max_qty,
    })

    return (
        f"Voce tem **{max_qty:.0f} unidade(s)** de **{produto_nome}** no orcamento.\n\n"
        f"Quantas unidades voce quer remover? (ou diga **tudo** para remover todas)"
    )


def handle_remove_qty(session_id: str, message: str) -> Optional[str]:
    st = get_state(session_id)
    if not st.get("awaiting_remove_qty"):
        return None

    product_id = st.get("pending_remove_product_id")
    max_qty = st.get("pending_remove_max_qty")

    if not product_id or max_qty is None:
        patch_state(session_id, {
            "awaiting_remove_qty": False,
            "pending_remove_product_id": None,
            "pending_remove_max_qty": None,
        })
        return "Nao consegui identificar o item para remover. Tente novamente."

    t = norm(message)

    if t in {"tudo", "todos", "todas", "completo"}:
        _, msg = remove_item_from_orcamento(session_id, int(product_id), qty_to_remove=None)
        patch_state(session_id, {
            "awaiting_remove_qty": False,
            "pending_remove_product_id": None,
            "pending_remove_max_qty": None,
        })
        resumo = format_orcamento(session_id)
        return f"{msg}\n\n{resumo}"

    from app.parsing import extract_units_quantity, extract_plain_number
    qty = extract_units_quantity(message) or extract_plain_number(message)

    if qty is None or qty <= 0:
        return (
            f"Nao entendi a quantidade. Voce tem **{max_qty:.0f} unidade(s)** no orcamento.\n\n"
            f"Me diga quantas quer remover (ex.: 2, 5, etc.) ou diga **tudo** para remover todas."
        )

    _, msg = remove_item_from_orcamento(session_id, int(product_id), qty_to_remove=float(qty))
    patch_state(session_id, {
        "awaiting_remove_qty": False,
        "pending_remove_product_id": None,
        "pending_remove_max_qty": None,
    })

    resumo = format_orcamento(session_id)
    return f"{msg}\n\n{resumo}"
