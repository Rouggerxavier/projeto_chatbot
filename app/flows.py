import traceback
from typing import Tuple

from app.constants import HORARIO_LOJA
from app.text_utils import (
    sanitize_reply, is_greeting, is_hours_question,
    is_cart_show_request, is_cart_reset_request, has_product_intent,
)
from app.persistence import save_chat_db
from app.cart_service import format_orcamento, reset_orcamento, add_item_to_orcamento
from app.product_search import db_find_best_products, format_options, parse_choice_indices, db_get_product_by_id
from app.parsing import (
    extract_kg_quantity, extract_units_quantity, extract_plain_number,
    suggest_units_from_packaging, extract_product_hint
)
from app.preferences import (
    detect_delivery_bairro, handle_preferences, message_is_preferences_only, maybe_register_address
)
from app.checkout import handle_checkout, ready_to_checkout
from app.session_state import get_state, patch_state


def reply_after_preference(session_id: str) -> str:
    st = get_state(session_id)
    resumo = format_orcamento(session_id)

    parts = []
    if st.get("preferencia_entrega"):
        parts.append(f"Beleza — anotei **{st['preferencia_entrega']}**.")
    if st.get("forma_pagamento"):
        parts.append(f"Pagamento: **{st['forma_pagamento']}**.")
    if st.get("bairro"):
        parts.append(f"Bairro: **{st['bairro']}**.")
    if st.get("cep"):
        parts.append(f"CEP: **{st['cep']}**.")

    reply = ""
    if parts:
        reply += " ".join(parts) + "\n\n"
    reply += resumo

    # ✅ se já dá pra fechar, pede contato (não volta pra “entrega ou retirada”)
    if ready_to_checkout(session_id):
        if not st.get("cliente_nome"):
            return reply + "\n\nPara finalizar com um atendente, me diga seu **nome**."
        if not st.get("cliente_telefone"):
            return reply + "\n\nAgora me diga seu **telefone** para contato."

    # caso contrário, pergunta só o que falta
    if not st.get("preferencia_entrega"):
        reply += "\n\nVai ser **entrega** ou **retirada**?"
    elif st.get("preferencia_entrega") == "entrega" and not (st.get("bairro") or st.get("cep") or st.get("endereco")):
        reply += "\n\nMe diga o **bairro** ou mande o **CEP/endereço** para entrega."

    if not st.get("forma_pagamento"):
        reply += "\n\nVai pagar no **PIX**, **cartão** ou **dinheiro**?"

    return reply


def set_pending_for_qty(session_id: str, produto, requested_kg: float | None) -> str:
    patch_state(session_id, {
        "pending_product_id": produto.id,
        "awaiting_qty": True,
        "pending_suggested_units": None,
    })

    ask = "\n\nQuantas unidades você quer? (ex.: 1, 4 sacos ou 200kg)"

    if requested_kg is not None:
        conv = suggest_units_from_packaging(produto.nome, requested_kg)
        if conv:
            suggested_units, conv_text = conv
            patch_state(session_id, {"pending_suggested_units": suggested_units})
            ask = (
                "\n\nPelo que você pediu: "
                f"**{conv_text}**.\n"
                f"Quer que eu adicione **{int(suggested_units)}** no orçamento? "
                "(responda sim ou diga outra quantidade)"
            )

    preco = float(produto.preco) if produto.preco is not None else 0.0
    estoque = float(produto.estoque_atual) if produto.estoque_atual is not None else 0.0
    un = produto.unidade or "UN"

    return (
        f"Beleza — **{produto.nome}**.\n"
        f"Preço: R$ {preco:.2f}/{un} | Estoque: {estoque:.0f} {un}."
        + ask
    )


def handle_pending_qty(session_id: str, message: str):
    st = get_state(session_id)
    if not st.get("awaiting_qty") or not st.get("pending_product_id"):
        return None

    produto = db_get_product_by_id(st["pending_product_id"])
    if not produto:
        patch_state(session_id, {"awaiting_qty": False, "pending_product_id": None, "pending_suggested_units": None})
        return "Certo — não consegui localizar esse produto agora. Me diga novamente qual produto você quer."

    t = (message or "").strip().lower()
    if t in {"sim", "isso", "ok", "certo"} and st.get("pending_suggested_units") is not None:
        qty_un = float(st["pending_suggested_units"])
    else:
        kg_qty = extract_kg_quantity(message)
        unit_qty = extract_units_quantity(message)
        plain = extract_plain_number(message)

        qty_un = None
        if kg_qty is not None:
            conv = suggest_units_from_packaging(produto.nome, kg_qty)
            if conv:
                qty_un, _ = conv
            else:
                return "Entendi os kg, mas este item não indica o peso por saco/unidade. Me diga quantas unidades você quer (ex.: 4)."

        if unit_qty is not None:
            qty_un = unit_qty
        if qty_un is None and plain is not None:
            qty_un = plain

        if qty_un is None:
            suggested = st.get("pending_suggested_units")
            if suggested is not None:
                return f"Quer que eu adicione **{int(suggested)}** unidades no orçamento? (responda sim ou diga outra quantidade)"
            return "Quantas unidades você quer? (ex.: 1, 4 sacos ou 200kg)"

    estoque = float(produto.estoque_atual) if produto.estoque_atual is not None else 0.0
    if estoque <= 0:
        patch_state(session_id, {"awaiting_qty": False, "pending_product_id": None, "pending_suggested_units": None})
        return f"Encontrei **{produto.nome}**, mas está **sem estoque** no momento. Quer escolher outra opção?"

    if qty_un > estoque:
        qty_un = estoque

    ok, msg_add = add_item_to_orcamento(session_id, produto, float(qty_un))
    patch_state(session_id, {"awaiting_qty": False, "pending_product_id": None, "pending_suggested_units": None})

    resumo = format_orcamento(session_id)
    return f"✅ {msg_add}\n\n{resumo}"


def auto_suggest_products(message: str, session_id: str):
    # se já dá pra fechar, não sugere produto — pede contato
    st = get_state(session_id)
    if ready_to_checkout(session_id) and (not st.get("cliente_nome") or not st.get("cliente_telefone")):
        return None

    if not has_product_intent(message):
        return None

    hint = extract_product_hint(message)
    if not hint or len(hint) < 2:
        return None

    produtos = db_find_best_products(hint, k=5)
    if not produtos:
        return None

    requested_kg = extract_kg_quantity(message)
    patch_state(session_id, {
        "last_suggestions": [{"id": p.id, "nome": p.nome} for p in produtos],
        "last_hint": hint,
        "last_requested_kg": requested_kg,
    })

    extra = ""
    if requested_kg is not None and produtos:
        conv = suggest_units_from_packaging(produtos[0].nome, requested_kg)
        if conv:
            _, conv_text = conv
            extra = f"\n\nPelo que você pediu: **{conv_text}**."

    return (
        f"Encontrei estas opções no catálogo para **{hint}**:\n\n"
        f"{format_options(produtos)}\n\n"
        "Qual você quer? (responda 1, 2, 3… ou escreva o nome parecido)"
        + extra
    )


def handle_suggestions_choice(session_id: str, message: str):
    st = get_state(session_id)
    suggestions = st.get("last_suggestions") or []
    if not suggestions:
        return None

    indices = parse_choice_indices(message, max_len=len(suggestions))
    if not indices:
        return None

    ids = [suggestions[i]["id"] for i in indices]
    requested_kg = st.get("last_requested_kg")

    patch_state(session_id, {"last_suggestions": [], "last_hint": None, "last_requested_kg": None})

    first = db_get_product_by_id(ids[0])
    if not first:
        return "Não consegui localizar essa opção agora. Pode tentar de novo?"

    return set_pending_for_qty(session_id, first, requested_kg=requested_kg)


def handle_message(message: str, session_id: str) -> Tuple[str, bool]:
    needs_human = False
    try:
        if is_greeting(message):
            reply = "Bom dia! 🙂 Como posso ajudar? (ex.: cimento, areia, trena, etc.)"
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        if is_hours_question(message):
            reply = HORARIO_LOJA
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        if is_cart_show_request(message):
            reply = format_orcamento(session_id)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        if is_cart_reset_request(message):
            reply = reset_orcamento(session_id)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        # preferências/endereço
        maybe_register_address(message, session_id)
        handle_preferences(message, session_id)

        # ✅ CHECKOUT: se já dá pra fechar, ele entra e pede nome/telefone
        checkout_reply, checkout_needs = handle_checkout(message, session_id)
        if checkout_reply:
            needs_human = checkout_needs
            checkout_reply = sanitize_reply(checkout_reply)
            save_chat_db(session_id, message, checkout_reply, needs_human)
            return checkout_reply, needs_human

        # prefs-only -> mostra resumo + próximo passo correto
        if message_is_preferences_only(message):
            reply = reply_after_preference(session_id)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        pending = handle_pending_qty(session_id, message)
        if pending:
            pending = sanitize_reply(pending)
            save_chat_db(session_id, message, pending, needs_human)
            return pending, needs_human

        choice = handle_suggestions_choice(session_id, message)
        if choice:
            choice = sanitize_reply(choice)
            save_chat_db(session_id, message, choice, needs_human)
            return choice, needs_human

        suggested = auto_suggest_products(message, session_id)
        if suggested:
            suggested = sanitize_reply(suggested)
            save_chat_db(session_id, message, suggested, needs_human)
            return suggested, needs_human

        # fallback
        resumo = format_orcamento(session_id)
        reply = (
            f"{resumo}\n\n"
            "Para finalizar com um atendente, diga **finalizar** ou mande seu **nome** e **telefone**."
        )
        reply = sanitize_reply(reply)
        save_chat_db(session_id, message, reply, needs_human)
        return reply, needs_human

    except Exception:
        traceback.print_exc()
        needs_human = True
        reply = "Tive um problema ao processar sua mensagem agora. Você pode tentar novamente."
        reply = sanitize_reply(reply)
        save_chat_db(session_id, message, reply, needs_human)
        return reply, needs_human
