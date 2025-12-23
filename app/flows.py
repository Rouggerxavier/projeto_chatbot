import re
import traceback
from typing import Optional, Tuple, Any, Dict, List

from app.constants import HORARIO_LOJA
from app.text_utils import (
    sanitize_reply,
    is_greeting,
    is_hours_question,
    is_cart_show_request,
    is_cart_reset_request,
    has_product_intent,
    norm,
)
from app.persistence import save_chat_db
from app.cart_service import (
    format_orcamento,
    reset_orcamento,
    add_item_to_orcamento,
    list_orcamento_items,
    remove_item_from_orcamento,
)
from app.product_search import (
    db_find_best_products,
    format_options,
    parse_choice_indices,
    db_get_product_by_id,
)
from app.parsing import (
    extract_kg_quantity,
    extract_units_quantity,
    extract_plain_number,
    suggest_units_from_packaging,
    extract_product_hint,
)
from app.preferences import handle_preferences, message_is_preferences_only, maybe_register_address
from app.checkout import handle_checkout, ready_to_checkout, handle_more_products_question
from app.session_state import get_state, patch_state


# -------------------------
# Helpers de robustez
# -------------------------

def _safe_option_id(o: Any) -> Optional[int]:
    """
    Aceita dicts com chaves diferentes (product_id / id / produto_id)
    e também objetos ORM (p.id).
    """
    if o is None:
        return None
    if isinstance(o, dict):
        pid = o.get("product_id")
        if pid is None:
            pid = o.get("id")
        if pid is None:
            pid = o.get("produto_id")
        try:
            return int(pid) if pid is not None else None
        except Exception:
            return None
    # ORM / objeto
    pid = getattr(o, "id", None)
    try:
        return int(pid) if pid is not None else None
    except Exception:
        return None


def _safe_option_name(o: Any) -> str:
    if isinstance(o, dict):
        return str(o.get("nome") or o.get("name") or "")
    return str(getattr(o, "nome", "") or "")


def _looks_like_bad_unit_request(message: str, hint: str) -> Optional[str]:
    """
    Ex.: '20 metros de areia' (m/metros não é unidade boa pra areia no catálogo)
    Ensina o usuário a pedir.
    """
    t = norm(message)
    h = norm(hint or "")

    # areia costuma ser m³ no catálogo, então "metros" e "m" confundem.
    if "areia" in h:
        # se ele falou m/metros mas não falou m3 / m³
        if re.search(r"\b(metro|metros)\b", t) or re.search(r"\b\d+\s*m\b", t):
            if not re.search(r"\b(m3|m³)\b", t):
                return (
                    "Entendi 🙂 Só uma dica: **areia normalmente é vendida em m³ (metro cúbico)**.\n\n"
                    "Tente assim:\n"
                    "• **quero 1m³ de areia fina**\n"
                    "• **areia média 2m³**\n"
                    "• ou só **areia fina** (que eu te mostro as opções)\n\n"
                    "Qual você prefere?"
                )

    return None


def _is_remove_intent(message: str) -> bool:
    t = norm(message)
    return any(k in t for k in ["remover", "tirar", "excluir", "deletar", "retirar"]) or "tirar do" in t


def _build_remove_options_text(options: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, opt in enumerate(options, start=1):
        lines.append(
            f"{idx}) {opt['nome']} — {opt['quantidade']:.0f} {opt['unidade']} (R$ {opt['subtotal']:.2f})"
        )
    return "\n".join(lines)


def start_remove_flow(session_id: str) -> str:
    items = list_orcamento_items(session_id)
    if not items:
        return "Seu orçamento está vazio. Não há itens para remover."

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

    options_text = _build_remove_options_text(items)
    return (
        "Quer remover algum item do orçamento? Se quiser, responda o número correspondente. "
        "Se não quiser remover nada, diga **não**.\n\n" + options_text
    )


def handle_remove_choice(session_id: str, message: str) -> Optional[str]:
    st = get_state(session_id)
    if not st.get("awaiting_remove_choice"):
        return None

    opts: List[Dict[str, Any]] = st.get("remove_options") or []
    t = norm(message)

    if t in {"nao", "não", "nenhum", "n"}:
        patch_state(session_id, {"awaiting_remove_choice": False, "remove_options": None})
        return "Certo, mantive todos os itens do orçamento."

    if not opts:
        patch_state(session_id, {"awaiting_remove_choice": False, "remove_options": None})
        return "Não encontrei itens para remover agora."

    choice = parse_choice_indices(message, max_n=len(opts))
    if not choice:
        options_text = _build_remove_options_text(opts)
        return (
            "Me diga o número do item que quer remover ou responda **não** para manter tudo.\n\n"
            + options_text
        )

    idx0 = choice[0] - 1
    if idx0 < 0 or idx0 >= len(opts):
        options_text = _build_remove_options_text(opts)
        return (
            "Opção inválida. Escolha um número da lista ou responda **não** para manter tudo.\n\n"
            + options_text
        )

    # Produto escolhido - agora perguntar quantidade
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
        f"Você tem **{max_qty:.0f} unidade(s)** de **{produto_nome}** no orçamento.\n\n"
        f"Quantas unidades você quer remover? (ou diga **tudo** para remover todas)"
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
        return "Não consegui identificar o item para remover. Tente novamente."
    
    t = norm(message)
    
    # Se disser "tudo", remove tudo
    if t in {"tudo", "todos", "todas", "completo"}:
        ok, msg = remove_item_from_orcamento(session_id, int(product_id), qty_to_remove=None)
        patch_state(session_id, {
            "awaiting_remove_qty": False,
            "pending_remove_product_id": None,
            "pending_remove_max_qty": None,
        })
        resumo = format_orcamento(session_id)
        if ok:
            return f"✅ {msg}\n\n{resumo}"
        return f"⚠️ {msg}\n\n{resumo}"
    
    # Tenta extrair quantidade
    from app.quantity_parser import extract_units_quantity, extract_plain_number
    qty = extract_units_quantity(message) or extract_plain_number(message)
    
    if qty is None or qty <= 0:
        return (
            f"Não entendi a quantidade. Você tem **{max_qty:.0f} unidade(s)** no orçamento.\n\n"
            f"Me diga quantas quer remover (ex.: 2, 5, etc.) ou diga **tudo** para remover todas."
        )
    
    # Remove a quantidade
    ok, msg = remove_item_from_orcamento(session_id, int(product_id), qty_to_remove=float(qty))
    patch_state(session_id, {
        "awaiting_remove_qty": False,
        "pending_remove_product_id": None,
        "pending_remove_max_qty": None,
    })
    
    resumo = format_orcamento(session_id)
    if ok:
        return f"✅ {msg}\n\n{resumo}"
    return f"⚠️ {msg}\n\n{resumo}"


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

    if not st.get("preferencia_entrega"):
        reply += "\n\nVai ser **entrega** ou **retirada**?"
    elif st.get("preferencia_entrega") == "entrega" and not (st.get("bairro") or st.get("cep") or st.get("endereco")):
        reply += "\n\nMe diga o **bairro** ou mande o **endereço completo (rua e número)** para entrega."

    if not st.get("forma_pagamento"):
        reply += "\n\nVai pagar no **PIX**, **cartão** ou **dinheiro**?"

    if ready_to_checkout(session_id):
        reply += "\n\nSe estiver tudo certo, diga **finalizar** para eu encaminhar a um atendente."

    return reply


def set_pending_for_qty(session_id: str, produto, requested_kg: Optional[float]) -> str:
    patch_state(
        session_id,
        {
            "pending_product_id": produto.id,
            "awaiting_qty": True,
            "pending_suggested_units": None,
        },
    )

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
        return "Certo — não consegui localizar esse produto agora. Me diga novamente qual produto você quer."

    t = (message or "").strip().lower()
    if t in {"sim", "isso", "ok", "certo"} and st.get("pending_suggested_units") is not None:
        qty_un = float(st["pending_suggested_units"])
    else:
        kg_qty = extract_kg_quantity(message)
        unit_qty = extract_units_quantity(message)
        plain = extract_plain_number(message)

        qty_un: Optional[float] = None

        if kg_qty is not None:
            conv = suggest_units_from_packaging(produto.nome, kg_qty)
            if conv:
                qty_un, _ = conv
            else:
                return (
                    "Entendi os kg, mas este item não indica o peso por saco/unidade. "
                    "Me diga quantas unidades você quer (ex.: 4)."
                )

        if unit_qty is not None:
            qty_un = unit_qty

        if qty_un is None and plain is not None:
            qty_un = plain

        if qty_un is None:
            suggested = st.get("pending_suggested_units")
            if suggested is not None:
                return (
                    f"Quer que eu adicione **{int(suggested)}** unidades no orçamento? "
                    "(responda sim ou diga outra quantidade)"
                )
            return "Quantas unidades você quer? (ex.: 1, 4 sacos ou 200kg)"

    estoque = float(produto.estoque_atual) if produto.estoque_atual is not None else 0.0
    if estoque <= 0:
        patch_state(
            session_id,
            {
                "awaiting_qty": False,
                "pending_product_id": None,
                "pending_suggested_units": None,
            },
        )
        return f"Encontrei **{produto.nome}**, mas está **sem estoque** no momento. Quer escolher outra opção?"

    if qty_un > estoque:
        qty_un = estoque

    ok, msg_add = add_item_to_orcamento(session_id, produto, float(qty_un))

    patch_state(
        session_id,
        {
            "awaiting_qty": False,
            "pending_product_id": None,
            "pending_suggested_units": None,
        },
    )

    resumo = format_orcamento(session_id)
    if not ok:
        return f"{msg_add}\n\n{resumo}"
    
    patch_state(session_id, {"asking_for_more": True})
    return f"✅ {msg_add}\n\n{resumo}\n\n**Quer adicionar outro produto?** (sim/não)"


def auto_suggest_products(message: str, session_id: str) -> Optional[str]:
    # só tenta sugerir se parecer pedido de produto
    if not has_product_intent(message):
        return None

    hint = extract_product_hint(message)
    if not hint or len(hint) < 2:
        return (
            "Não consegui identificar o produto 😅\n\n"
            "Tente ser mais direto, por exemplo:\n"
            "• **quero areia fina**\n"
            "• **quero cimento CP II 50kg**\n"
            "• **quero trena 5m**"
        )

    # dica de unidade (ex.: "20 metros de areia")
    teach = _looks_like_bad_unit_request(message, hint)
    if teach:
        return teach

    options = db_find_best_products(hint, k=6) or []
    if not options:
        return (
            f"Não encontrei nada no catálogo parecido com **{hint}**.\n\n"
            "Tente assim:\n"
            "• **areia fina** / **areia média**\n"
            "• **cimento CP II 50kg**\n"
            "• **trena 5m**"
        )

    requested_kg = extract_kg_quantity(message)

    # guarda sugestões SEM quebrar com formatos diferentes
    last_suggestions: List[Dict[str, Any]] = []
    for o in options:
        pid = _safe_option_id(o)
        if pid is None:
            continue
        last_suggestions.append({"id": pid, "nome": _safe_option_name(o)})

    if not last_suggestions:
        return (
            "Achei opções, mas não consegui identificar o ID delas (erro de dados).\n"
            "Pode tentar novamente com o nome do produto? Ex.: **areia fina**"
        )

    patch_state(
        session_id,
        {
            "last_suggestions": last_suggestions,
            "last_hint": hint,
            "last_requested_kg": requested_kg,
        },
    )

    extra = ""
    # se pediu kg e a 1ª opção tem embalagem, sugere conversão
    first_prod = db_get_product_by_id(int(last_suggestions[0]["id"]))
    if requested_kg is not None and first_prod:
        conv = suggest_units_from_packaging(first_prod.nome, requested_kg)
        if conv:
            _, conv_text = conv
            extra = f"\n\nPelo que você pediu: **{conv_text}**."

    return (
        f"Encontrei estas opções no catálogo para **{hint}**:\n\n"
        f"{format_options(options)}\n\n"
        "Qual você quer? (responda 1, 2, 3… ou escreva o nome parecido)"
        + extra
    )


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

        # preferências/endereço
        maybe_register_address(message, session_id)
        handle_preferences(message, session_id)

        # remoção - quantidade pendente
        pending_remove_qty = handle_remove_qty(session_id, message)
        if pending_remove_qty:
            pending_remove_qty = sanitize_reply(pending_remove_qty)
            save_chat_db(session_id, message, pending_remove_qty, needs_human)
            return pending_remove_qty, needs_human

        # remoção - escolha pendente
        pending_remove = handle_remove_choice(session_id, message)
        if pending_remove:
            pending_remove = sanitize_reply(pending_remove)
            save_chat_db(session_id, message, pending_remove, needs_human)
            return pending_remove, needs_human

        # intenção de remover itens
        if _is_remove_intent(message):
            remove_reply = start_remove_flow(session_id)
            remove_reply = sanitize_reply(remove_reply)
            save_chat_db(session_id, message, remove_reply, needs_human)
            return remove_reply, needs_human

        # resposta para "Quer outro produto?"
        more_reply, more_needs = handle_more_products_question(message, session_id)
        if more_reply:
            needs_human = more_needs
            more_reply = sanitize_reply(more_reply)
            save_chat_db(session_id, message, more_reply, needs_human)
            return more_reply, needs_human

        # checkout (apenas quando usuário disser finalizar/fechar)
        checkout_reply, checkout_needs = handle_checkout(message, session_id)
        if checkout_reply:
            needs_human = checkout_needs
            checkout_reply = sanitize_reply(checkout_reply)
            save_chat_db(session_id, message, checkout_reply, needs_human)
            return checkout_reply, needs_human

        # pending qty primeiro
        pending = handle_pending_qty(session_id, message)
        if pending:
            pending = sanitize_reply(pending)
            save_chat_db(session_id, message, pending, needs_human)
            return pending, needs_human

        # prefs-only (entrega/pix/cep/bairro)
        if message_is_preferences_only(message, session_id):
            reply = reply_after_preference(session_id)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        # escolha em sugestões
        choice = handle_suggestions_choice(session_id, message)
        if choice:
            choice = sanitize_reply(choice)
            save_chat_db(session_id, message, choice, needs_human)
            return choice, needs_human

        # sugestão automática (com ensino quando não entender)
        suggested = auto_suggest_products(message, session_id)
        if suggested:
            suggested = sanitize_reply(suggested)
            save_chat_db(session_id, message, suggested, needs_human)
            return suggested, needs_human

        # explicação do "orçamento vazio" pós fechamento
        st = get_state(session_id)
        if "orcamento" in norm(message) and "vazio" in norm(message) and st.get("last_order_summary"):
            reply = (
                "Seu orçamento aparece vazio porque o pedido anterior foi **finalizado** e o orçamento foi **fechado**.\n\n"
                f"Resumo do último pedido:\n{st['last_order_summary']}\n\n"
                "Se quiser fazer um novo orçamento, é só me dizer os itens."
            )
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        # fallback com instruções (melhor que só repetir exemplo)
        resumo = format_orcamento(session_id)
        reply = (
            f"{resumo}\n\n"
            "Não consegui entender exatamente o que você quer 😅\n\n"
            "Tente ser mais direto, por exemplo:\n"
            "• **quero areia fina**\n"
            "• **quero cimento CP II 50kg**\n"
            "• **quero trena 5m**\n\n"
            "Se quiser finalizar um pedido já montado, diga **finalizar**."
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
