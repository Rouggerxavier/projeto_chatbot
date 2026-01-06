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
from app.cart_service import format_orcamento, reset_orcamento
from app.product_search import (
    db_find_best_products,
    format_options,
    db_get_product_by_id,
)
from app.parsing import (
    extract_kg_quantity,
    suggest_units_from_packaging,
    extract_product_hint,
)
from app.preferences import handle_preferences, message_is_preferences_only, maybe_register_address
from app.checkout import handle_more_products_question
from app.checkout_handlers.main import handle_checkout
from app.session_state import get_state, patch_state
from app.checkout_handlers.extractors import extract_email

# Importa dos modulos flows/
from app.flows.quantity import handle_pending_qty
from app.flows.removal import (
    is_remove_intent,
    start_remove_flow,
    handle_remove_choice,
    handle_remove_qty,
)
from app.flows.product_selection import handle_suggestions_choice


def _safe_option_id(o: Any) -> Optional[int]:
    """
    Aceita dicts com chaves diferentes (product_id / id / produto_id)
    e tambem objetos ORM (p.id).
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
    Ex.: '20 metros de areia' (m/metros nao e unidade boa pra areia no catalogo)
    Ensina o usuario a pedir.
    """
    t = norm(message)
    h = norm(hint or "")

    if "areia" in h:
        if re.search(r"\b(metro|metros)\b", t) or re.search(r"\b\d+\s*m\b", t):
            if not re.search(r"\b(m3|m3)\b", t):
                return (
                    "Entendi. So uma dica: **areia normalmente e vendida em m3 (metro cubico)**.\n\n"
                    "Tente assim:\n"
                    "- **quero 1m3 de areia fina**\n"
                    "- **areia media 2m3**\n"
                    "- ou so **areia fina** (que eu te mostro as opcoes)\n\n"
                    "Qual voce prefere?"
                )

    return None


def reply_after_preference(session_id: str) -> str:
    st = get_state(session_id)
    resumo = format_orcamento(session_id)

    parts = []
    if st.get("preferencia_entrega"):
        parts.append(f"Beleza - anotei **{st['preferencia_entrega']}**.")
    if st.get("forma_pagamento"):
        parts.append(f"Pagamento: **{st['forma_pagamento']}**.")
    if st.get("endereco"):
        parts.append(f"Endereco: **{st['endereco']}**.")
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
        reply += "\n\nMe diga o **bairro** ou mande o **endereco completo (rua e numero)** para entrega."

    if not st.get("forma_pagamento"):
        reply += "\n\nVai pagar no **PIX**, **cartao** ou **dinheiro**?"

    reply += "\n\nSe estiver tudo certo, diga **finalizar** para eu encaminhar a um atendente."

    return reply


def auto_suggest_products(message: str, session_id: str) -> Optional[str]:
    if not has_product_intent(message):
        return None

    hint = extract_product_hint(message)
    if not hint or len(hint) < 2:
        return (
            "Nao consegui identificar o produto.\n\n"
            "Tente ser mais direto, por exemplo:\n"
            "- **quero areia fina**\n"
            "- **quero cimento CP II 50kg**\n"
            "- **quero trena 5m**"
        )

    teach = _looks_like_bad_unit_request(message, hint)
    if teach:
        return teach

    options = db_find_best_products(hint, k=6) or []
    if not options:
        return (
            f"Nao encontrei nada no catalogo parecido com **{hint}**.\n\n"
            "Tente assim:\n"
            "- **areia fina** / **areia media**\n"
            "- **cimento CP II 50kg**\n"
            "- **trena 5m**"
        )

    requested_kg = extract_kg_quantity(message)

    last_suggestions: List[Dict[str, Any]] = []
    for o in options:
        pid = _safe_option_id(o)
        if pid is None:
            continue
        last_suggestions.append({"id": pid, "nome": _safe_option_name(o)})

    if not last_suggestions:
        return (
            "Achei opcoes, mas nao consegui identificar o ID delas (erro de dados).\n"
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
    first_prod = db_get_product_by_id(int(last_suggestions[0]["id"]))
    if requested_kg is not None and first_prod:
        conv = suggest_units_from_packaging(first_prod.nome, requested_kg)
        if conv:
            _, conv_text = conv
            extra = f"\n\nPelo que voce pediu: **{conv_text}**."

    return (
        f"Encontrei estas opcoes no catalogo para **{hint}**:\n\n"
        f"{format_options(options)}\n\n"
        "Qual voce quer? (responda 1, 2, 3... ou escreva o nome parecido)"
        + extra
    )


def handle_message(message: str, session_id: str) -> Tuple[str, bool]:
    needs_human = False
    try:
        if is_greeting(message):
            reply = "Bom dia! Como posso ajudar? (ex.: cimento, areia, trena, etc.)"
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

        # preferencias/endereco
        maybe_register_address(message, session_id)
        handle_preferences(message, session_id)

        # remocao - quantidade pendente
        pending_remove_qty = handle_remove_qty(session_id, message)
        if pending_remove_qty:
            pending_remove_qty = sanitize_reply(pending_remove_qty)
            save_chat_db(session_id, message, pending_remove_qty, needs_human)
            return pending_remove_qty, needs_human

        # remocao - escolha pendente
        pending_remove = handle_remove_choice(session_id, message)
        if pending_remove:
            pending_remove = sanitize_reply(pending_remove)
            save_chat_db(session_id, message, pending_remove, needs_human)
            return pending_remove, needs_human

        # intencao de remover itens
        if is_remove_intent(message):
            remove_reply = start_remove_flow(session_id)
            remove_reply = sanitize_reply(remove_reply)
            save_chat_db(session_id, message, remove_reply, needs_human)
            return remove_reply, needs_human

        # resposta para "Quer outro produto?"
        st = get_state(session_id)
        if st.get("asking_for_more"):
            more_reply, more_needs = handle_more_products_question(message, session_id)
            if more_reply:
                needs_human = more_needs
                more_reply = sanitize_reply(more_reply)
                save_chat_db(session_id, message, more_reply, needs_human)
                return more_reply, needs_human

        # Checkout mode ou intent de finalizar - usa handle_checkout completo
        st = get_state(session_id)
        t = norm(message)
        is_finalize = any(k in t for k in ["finalizar", "fechar", "pagar", "checkout", "processar"])

        if st.get("checkout_mode") or is_finalize:
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

        # escolha em sugestoes
        choice = handle_suggestions_choice(session_id, message)
        if choice:
            choice = sanitize_reply(choice)
            save_chat_db(session_id, message, choice, needs_human)
            return choice, needs_human

        # sugestao automatica
        suggested = auto_suggest_products(message, session_id)
        if suggested:
            suggested = sanitize_reply(suggested)
            save_chat_db(session_id, message, suggested, needs_human)
            return suggested, needs_human

        # explicacao do "orcamento vazio" pos fechamento
        st = get_state(session_id)
        if "orcamento" in norm(message) and "vazio" in norm(message) and st.get("last_order_summary"):
            reply = (
                "Seu orcamento aparece vazio porque o pedido anterior foi **finalizado** e o orcamento foi **fechado**.\n\n"
                f"Resumo do ultimo pedido:\n{st['last_order_summary']}\n\n"
                "Se quiser fazer um novo orcamento, e so me dizer os itens."
            )
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        # fallback com instrucoes
        resumo = format_orcamento(session_id)
        reply = (
            f"{resumo}\n\n"
            "Nao consegui entender exatamente o que voce quer.\n\n"
            "Tente ser mais direto, por exemplo:\n"
            "- **quero areia fina**\n"
            "- **quero cimento CP II 50kg**\n"
            "- **quero trena 5m**\n\n"
            "Se quiser finalizar um pedido ja montado, diga **finalizar**."
        )
        reply = sanitize_reply(reply)
        save_chat_db(session_id, message, reply, needs_human)
        return reply, needs_human

    except Exception:
        traceback.print_exc()
        needs_human = True
        reply = "Tive um problema ao processar sua mensagem agora. Voce pode tentar novamente."
        reply = sanitize_reply(reply)
        save_chat_db(session_id, message, reply, needs_human)
        return reply, needs_human
