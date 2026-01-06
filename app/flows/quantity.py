from typing import Optional

from app.session_state import get_state, patch_state
from app.cart_service import add_item_to_orcamento, format_orcamento
from app.product_search import db_get_product_by_id
from app.parsing import (
    extract_kg_quantity,
    extract_units_quantity,
    extract_plain_number,
    suggest_units_from_packaging,
)


def set_pending_for_qty(session_id: str, produto, requested_kg: Optional[float]) -> str:
    patch_state(
        session_id,
        {
            "pending_product_id": produto.id,
            "awaiting_qty": True,
            "pending_suggested_units": None,
        },
    )

    ask = "\n\nQuantas unidades voce quer? (ex.: 1, 4 sacos ou 200kg)"

    if requested_kg is not None:
        conv = suggest_units_from_packaging(produto.nome, requested_kg)
        if conv:
            suggested_units, conv_text = conv
            patch_state(session_id, {"pending_suggested_units": suggested_units})
            ask = (
                "\n\nPelo que voce pediu: "
                f"**{conv_text}**.\n"
                f"Quer que eu adicione **{int(suggested_units)}** no orcamento? "
                "(responda sim ou diga outra quantidade)"
            )

    preco = float(produto.preco) if produto.preco is not None else 0.0
    estoque = float(produto.estoque_atual) if produto.estoque_atual is not None else 0.0
    un = produto.unidade or "UN"

    return (
        f"Beleza - **{produto.nome}**.\n"
        f"Preco: R$ {preco:.2f}/{un} | Estoque: {estoque:.0f} {un}."
        + ask
    )


def handle_pending_qty(session_id: str, message: str) -> Optional[str]:
    st = get_state(session_id)
    if not st.get("awaiting_qty") or not st.get("pending_product_id"):
        return None

    produto = db_get_product_by_id(int(st["pending_product_id"]))
    if not produto:
        patch_state(
            session_id,
            {
                "awaiting_qty": False,
                "pending_product_id": None,
                "pending_suggested_units": None,
            },
        )
        return "Certo - nao consegui localizar esse produto agora. Me diga novamente qual produto voce quer."

    t = (message or "").strip().lower()
    qty_un: Optional[float] = None

    if t in {"sim", "isso", "ok", "certo"} and st.get("pending_suggested_units") is not None:
        qty_un = float(st["pending_suggested_units"])
    else:
        kg_qty = extract_kg_quantity(message)
        unit_qty = extract_units_quantity(message)
        plain = extract_plain_number(message)

        if kg_qty is not None:
            conv = suggest_units_from_packaging(produto.nome, kg_qty)
            if conv:
                qty_un, _ = conv
            else:
                return (
                    "Entendi os kg, mas este item nao indica o peso por saco/unidade. "
                    "Me diga quantas unidades voce quer (ex.: 4)."
                )

        if unit_qty is not None:
            qty_un = unit_qty

        if qty_un is None and plain is not None:
            qty_un = plain

        if qty_un is None:
            suggested = st.get("pending_suggested_units")
            if suggested is not None:
                return (
                    f"Quer que eu adicione **{int(suggested)}** unidades no orcamento? "
                    "(responda sim ou diga outra quantidade)"
                )
            return "Entendi. Quantas unidades voce quer? (ex.: 1, 4 sacos ou 200kg)"

    # Verificacao geral apos todo o processamento
    if qty_un is None or qty_un <= 0:
        return "Entendi. Quantas unidades voce quer?"

    patch_state(
        session_id,
        {
            "awaiting_qty": False,
            "pending_product_id": None,
            "pending_suggested_units": None,
        },
    )

    ok, msg = add_item_to_orcamento(session_id, produto, qty_un)
    resumo = format_orcamento(session_id)

    if ok:
        patch_state(session_id, {"asking_for_more": True})
        return f"{msg}\n\n{resumo}\n\nQuer adicionar outro produto? (sim ou nao)"
    else:
        return f"{msg}\n\n{resumo}"
