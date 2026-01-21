import re
import traceback
import logging
from typing import Optional, Tuple, Any, Dict, List

from app.constants import HORARIO_LOJA
from app.text_utils import (
    sanitize_reply,
    is_greeting,
    is_hours_question,
    is_cart_show_request,
    is_cart_reset_request,
    has_product_intent,
    is_consultive_question,
    norm,
)
from app.persistence import save_chat_db
from app.cart_service import format_orcamento, reset_orcamento, list_orcamento_items
from app.product_search import (
    db_find_best_products,
    format_options,
    db_get_product_by_id,
    db_find_best_products_with_constraints,
)
from app.parsing import (
    extract_kg_quantity,
    suggest_units_from_packaging,
    extract_product_hint,
)
from app.preferences import handle_preferences, message_is_preferences_only, maybe_register_address
from app.checkout import handle_more_products_question
from app.checkout_handlers.main import handle_checkout
from app.session_state import get_state, patch_state, reset_consultive_context
from app.checkout_handlers.extractors import extract_email
from app.consultive_mode import answer_consultive_question
from app.llm_service import (
    route_intent,
    plan_consultive_next_step,
    generate_technical_synthesis,
    extract_product_factors,
    maybe_render_customer_message,
)
from app.flows.technical_recommendations import can_generate_technical_answer
from app.search_utils import extract_catalog_constraints_from_consultive
from app.rag_knowledge import format_knowledge_answer
from app.session_state import (
    get_pending_prompt,
    push_pending_prompt,
    pop_pending_prompt,
    set_pending_prompt,
)

# Importa dos modulos flows/
from app.flows.quantity import handle_pending_qty
from app.flows.removal import (
    is_remove_intent,
    start_remove_flow,
    handle_remove_choice,
    handle_remove_qty,
)
from app.flows.product_selection import handle_suggestions_choice
from app.flows.usage_context import (
    is_generic_product,
    ask_usage_context,
    handle_usage_context_response,
    extract_known_usage_context,
    start_usage_context_flow,
)
from app import settings

logger = logging.getLogger(__name__)

_ROUTER_CLARIFY_MSG = (
    "Preciso confirmar: voce quer ver opcoes de produtos (orcamento) ou prefere uma recomendacao tecnica? "
    "Responda 1 para produtos ou 2 para recomendacao."
)


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


def _detect_interrupt(message: str) -> bool:
    t = norm(message)
    if "?" in message:
        return True
    starters = ["voce", "voc", "tem", "vende", "quanto", "qual", "como", "pode", "sera", "será"]
    return any(t.startswith(s) for s in starters)


def _matches_expected_kind(message: str, prompt: Dict[str, Any]) -> bool:
    kind = (prompt or {}).get("expected_kind") or ""
    meta = (prompt or {}).get("metadata") or {}
    t = norm(message)
    if not t:
        return False
    if kind == "yes_no":
        return t in {"sim", "s", "nao", "não", "n"}
    if kind == "number_choice":
        import re as _re
        if not _re.fullmatch(r"\d+", t):
            return False
        val = int(t)
        limit = meta.get("max_option") or meta.get("options_len")
        if limit:
            return 1 <= val <= int(limit)
        return True
    if kind == "quantity":
        from app.parsing import extract_units_quantity, extract_plain_number, extract_kg_quantity
        return any(v is not None for v in [extract_units_quantity(message), extract_plain_number(message), extract_kg_quantity(message)])
    if kind == "free_text":
        return True
    return False


def _resume_previous_prompt(session_id: str, faq_reply: str, pending: Dict[str, Any]) -> str:
    resume_text = pending.get("text") or "Podemos continuar?"
    set_pending_prompt(session_id, pending)
    return f"{faq_reply}\n\nVoltando ao que estavamos: {resume_text}"


def resolve_faq_or_product_query(message: str) -> Optional[str]:
    hint = extract_product_hint(message)
    if hint:
        options = db_find_best_products(hint, k=3) or []
        if options:
            names = ", ".join([o.get("nome", "") for o in options[:3] if o.get("nome")])
            return f"Temos opcoes relacionadas a {hint}: {names}.\nQuer que eu siga com um orcamento ou uma recomendacao tecnica?"
    faq = format_knowledge_answer(message, hint)
    if faq:
        return faq
    return "Posso ajudar com isso. Quer detalhes de produtos ou uma recomendacao tecnica?"


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

    # NOVO: verifica se produto generico (precisa contexto de uso)
    if is_generic_product(hint):
        known_ctx = extract_known_usage_context(message)
        if known_ctx:
            return start_usage_context_flow(session_id, hint, known_ctx)
        return ask_usage_context(session_id, hint)

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


def _build_state_summary(session_id: str, st: Dict[str, Any]) -> Dict[str, Any]:
    items = list_orcamento_items(session_id)
    cart_has_items = bool(items)

    last_known = (
        st.get("last_hint")
        or st.get("consultive_product_hint")
        or st.get("usage_context_product_hint")
    )

    consultive_fields = {
        "consultive_application": "application",
        "consultive_environment": "environment",
        "consultive_exposure": "exposure",
        "consultive_load_type": "load_type",
        "consultive_surface": "surface",
        "consultive_grain": "grain",
        "consultive_size": "size",
        "consultive_argamassa_type": "argamassa_type",
    }
    has_any_consultive = any(st.get(k) for k in consultive_fields)
    missing = []
    if has_any_consultive:
        missing = [v for k, v in consultive_fields.items() if not st.get(k)]

    return {
        "in_checkout": bool(st.get("checkout_mode")),
        "awaiting_choice": bool(st.get("last_suggestions")),
        "awaiting_quantity": bool(st.get("awaiting_qty")),
        "consultive_pending": bool(st.get("awaiting_usage_context") or st.get("consultive_investigation")),
        "cart_has_items": cart_has_items,
        "last_known_product": last_known,
        "last_known_category": last_known,
        "consultive_context_missing": missing,
        "asked_context_fields": st.get("asked_context_fields") or [],
    }


def _should_bypass_router(st: Dict[str, Any], message: str) -> bool:
    t = norm(message)
    is_finalize = any(k in t for k in ["finalizar", "fechar", "pagar", "checkout", "processar"])

    return any(
        [
            bool(st.get("last_suggestions")),
            bool(st.get("awaiting_qty")),
            bool(st.get("pending_product_id")),
            bool(st.get("awaiting_remove_choice")),
            bool(st.get("awaiting_remove_qty")),
            bool(st.get("checkout_mode")),
            bool(st.get("asking_for_more")),
            bool(st.get("awaiting_usage_context")),
            bool(st.get("consultive_investigation")),
            bool(is_finalize),
        ]
    )


def _constraints_to_query(constraints: Dict[str, Any]) -> str:
    parts: List[str] = []
    if not isinstance(constraints, dict):
        return ""
    for _, v in constraints.items():
        if isinstance(v, (str, int, float)):
            parts.append(str(v))
        elif isinstance(v, list):
            parts.extend([str(x) for x in v if isinstance(x, (str, int, float))])
    return " ".join(parts).strip()


def _gate_generic_usage(session_id: str, hint: str, message: str) -> Optional[Tuple[str, bool]]:
    """
    Se for produto genérico, aciona pergunta de uso ou inicia fluxo direto se já houver contexto.
    Retorna (reply, needs_human) ou None para seguir fluxo normal.
    """
    if not hint or not is_generic_product(hint):
        return None

    known_ctx = extract_known_usage_context(message)
    if known_ctx:
        reply = start_usage_context_flow(session_id, hint, known_ctx)
    else:
        reply = ask_usage_context(session_id, hint)

    if reply:
        return sanitize_reply(reply), False
    return None


def _set_last_suggestions(session_id: str, options: List[Dict[str, Any]], hint: str, context: Optional[Dict[str, Any]] = None) -> None:
    last_suggestions: List[Dict[str, Any]] = []
    for o in options:
        pid = _safe_option_id(o)
        if pid is None:
            continue
        entry = {"id": pid, "nome": _safe_option_name(o)}
        if context:
            entry["context"] = context
        last_suggestions.append(entry)
    patch_state(
        session_id,
        {
            "last_suggestions": last_suggestions,
            "last_hint": hint,
            "last_requested_kg": None,
        },
    )


def _catalog_reply_for_query(session_id: str, query: str, clarifying_question: Optional[str], category_hint: Optional[str] = None) -> Optional[str]:
    if not query:
        return clarifying_question or "Qual produto voce procura?"

    options = db_find_best_products(query, k=6) or []
    if not options:
        return clarifying_question or "Nao encontrei esse produto. Qual voce procura?"

    context_payload = {"query": query}
    if category_hint:
        context_payload["hint"] = category_hint
    _set_last_suggestions(session_id, options, query, context=context_payload)
    facts_items = []
    for o in options:
        facts_items.append(
            {
                "id": str(_safe_option_id(o) or ""),
                "name": _safe_option_name(o),
                "price": f"{float(o.get('preco', 0.0) or 0.0):.2f}",
                "unit": o.get("unidade", "UN"),
            }
        )
    facts = {
        "type": "catalog",
        "query": query,
        "items": facts_items,
        "next_question": "Qual voce quer? (responda 1, 2, 3... ou escreva o nome parecido)",
    }
    rendered = maybe_render_customer_message("CURTO_WHATSAPP", facts)
    if rendered:
        return rendered
    return (
        f"Encontrei estas opcoes no catalogo para **{query}**:\n\n"
        f"{format_options(options)}\n\n"
        "Qual voce quer? (responda 1, 2, 3... ou escreva o nome parecido)"
    )


def _has_consultive_context(st: Dict[str, Any], constraints: Dict[str, Any]) -> bool:
    if constraints:
        return True
    return any(
        [
            st.get("consultive_application"),
            st.get("consultive_environment"),
            st.get("consultive_exposure"),
            st.get("consultive_load_type"),
            st.get("consultive_surface"),
            st.get("consultive_grain"),
            st.get("consultive_size"),
        ]
    )


def _build_known_context(st: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
    ctx = {
        "application": st.get("consultive_application"),
        "environment": st.get("consultive_environment"),
        "exposure": st.get("consultive_exposure"),
        "load_type": st.get("consultive_load_type"),
        "surface": st.get("consultive_surface"),
        "grain": st.get("consultive_grain"),
        "size": st.get("consultive_size"),
        "argamassa_type": st.get("consultive_argamassa_type"),
    }
    if isinstance(constraints, dict):
        for k, v in constraints.items():
            if k in ctx and v:
                ctx[k] = v
    return {k: v for k, v in ctx.items() if v}


def _infer_missing_fields(product_hint: str, context: Dict[str, Any]) -> List[str]:
    p = norm(product_hint or "")
    missing: List[str] = []

    if "tinta" in p:
        if not context.get("surface"):
            missing.append("surface")
        if not context.get("environment"):
            missing.append("environment")
        return missing

    if not context.get("application"):
        missing.append("application")
        return missing

    if "cimento" in p:
        app = norm(context.get("application"))
        if app not in ["fundacao", "reboco", "piso"] and not context.get("environment"):
            missing.append("environment")
        return missing

    return missing


def _question_for_field(product_hint: str, field: str) -> str:
    p = norm(product_hint or "")
    if field == "application":
        return "Qual uso voce precisa? (ex.: laje, reboco, piso, fundacao)"
    if field == "environment":
        return "Vai usar em area interna ou externa?"
    if field == "exposure":
        return "O local fica coberto ou exposto?"
    if field == "load_type":
        return "E uso residencial ou carga pesada?"
    if field == "surface":
        return "Qual superficie vai receber a tinta? (parede, madeira, metal)"
    if field == "grain":
        return "Qual granulometria voce precisa? (fina, media, grossa)"
    if field == "size":
        return "Qual tamanho voce precisa?"
    if field == "argamassa_type":
        return "Qual tipo de argamassa? (assentamento, reboco, cola)"
    if "tijolo" in p:
        return "Voce precisa de tijolo estrutural ou de vedacao?"
    return "Pode explicar melhor o uso?"


def _apply_asked_context_fields(session_id: str, st: Dict[str, Any], field: Optional[str]) -> None:
    asked = list(st.get("asked_context_fields") or [])
    if field and field not in asked:
        asked.append(field)
    patch_state(session_id, {"asked_context_fields": asked, "last_consultive_question_key": field})


def _search_consultive_catalog(
    product_hint: str,
    summary_text: str,
    known_context: Dict[str, Any],
    query_base: str,
) -> Dict[str, Any]:
    try:
        constraints = extract_catalog_constraints_from_consultive(summary_text, product_hint, known_context)
    except Exception:
        constraints = None

    if not constraints:
        items = db_find_best_products_with_constraints(
            query_base,
            k=6,
            category_hint=product_hint or None,
            strict=False,
        )
        if not items and query_base:
            items = db_find_best_products(query_base, k=6) or []
        return {
            "items": items,
            "exact_match_found": False,
            "unavailable_specs": [],
            "warning_text": None,
            "constraints": {},
        }

    category_hint = constraints.get("category_hint") or product_hint or None
    must_terms = constraints.get("must_terms") or []
    should_terms = constraints.get("should_terms") or []

    phase1 = db_find_best_products_with_constraints(
        query_base,
        k=6,
        category_hint=category_hint,
        must_terms=must_terms,
        strict=True,
    )
    if phase1:
        return {
            "items": phase1,
            "exact_match_found": True,
            "unavailable_specs": [],
            "warning_text": None,
            "constraints": constraints,
        }

    unavailable_specs = list(must_terms)
    phase2 = db_find_best_products_with_constraints(
        query_base or (category_hint or ""),
        k=6,
        category_hint=category_hint,
        should_terms=should_terms,
        strict=False,
    )

    warning_text = None
    if unavailable_specs:
        spec_text = ", ".join(unavailable_specs).upper()
        warning_text = (
            f"Nao encontrei {spec_text} no catalogo agora, "
            "mas posso sugerir opcoes disponiveis:"
        )

    return {
        "items": phase2,
        "exact_match_found": False,
        "unavailable_specs": unavailable_specs,
        "warning_text": warning_text,
        "constraints": constraints,
    }


def _handle_consultive_planner(
    session_id: str,
    message: str,
    st: Dict[str, Any],
    product_hint: str,
    constraints: Dict[str, Any],
    fallback_to_usage: bool,
    fallback_to_consultive: bool,
) -> Optional[Tuple[str, bool]]:
    state_summary = _build_state_summary(session_id, st)
    known_context = _build_known_context(st, constraints)
    plan = plan_consultive_next_step(message, state_summary, product_hint, known_context)
    if plan:
        plan_conf = float(plan.get("confidence", 0.0) or 0.0)
        if plan_conf < settings.LLM_HARD_BLOCK_THRESHOLD or plan_conf < settings.PLANNER_CONFIDENCE_THRESHOLD:
            missing_fields = plan.get("missing_fields") or []
            field = missing_fields[0] if missing_fields else None
            question = plan.get("next_question") or _question_for_field(product_hint, field or "application")
            _apply_asked_context_fields(session_id, st, field or "application")
            logger.info(
                "llm_low_confidence_fallback component=planner confidence=%.2f threshold=%.2f session=%s type=%s",
                plan_conf,
                settings.PLANNER_CONFIDENCE_THRESHOLD,
                session_id,
                "clarify",
            )
            return question, False
    if not plan:
        if fallback_to_usage and product_hint:
            reply = ask_usage_context(session_id, product_hint)
            return reply, False
        if fallback_to_consultive:
            reply, needs = answer_consultive_question(message, product_hint)
            return reply, needs
        return None

    next_action = plan.get("next_action")
    missing_fields = plan.get("missing_fields") or []
    next_question = plan.get("next_question")
    asked_fields = set(st.get("asked_context_fields") or [])

    if next_action == "ASK_CONTEXT":
        field = None
        for mf in missing_fields:
            if mf not in asked_fields:
                field = mf
                break
        if not field and missing_fields:
            field = missing_fields[0]
        question = next_question or _question_for_field(product_hint, field or "")
        _apply_asked_context_fields(session_id, st, field)
        return question, False

    if next_action == "ASK_CLARIFYING_QUESTION":
        question = next_question or "Voce quer dica tecnica ou ver opcoes do catalogo?"
        _apply_asked_context_fields(session_id, st, "clarify")
        return question, False

    if next_action == "READY_TO_ANSWER":
        context_for_gate = dict(known_context)
        context_for_gate["product"] = product_hint
        if can_generate_technical_answer(product_hint, context_for_gate):
            factors = extract_product_factors(product_hint)
            synthesis = generate_technical_synthesis(product_hint, context_for_gate, factors)
            if synthesis:
                catalog_result = _search_consultive_catalog(
                    product_hint=product_hint,
                    summary_text=synthesis,
                    known_context=known_context,
                    query_base=product_hint,
                )
                patch_state(
                    session_id,
                    {
                        "consultive_last_summary": synthesis,
                        "consultive_catalog_constraints": catalog_result.get("constraints") or {},
                    },
                )
                facts = {
                    "type": "consultive_answer",
                    "summary": synthesis,
                    "recommended_next_steps": ["Quer que eu te ajude a escolher e comprar?"],
                    "suggested_items": [],
                    "recommended_specs": catalog_result.get("constraints", {}).get("must_terms", []),
                    "exact_match_found": bool(catalog_result.get("exact_match_found")),
                    "unavailable_specs": catalog_result.get("unavailable_specs", []),
                }
                rendered = maybe_render_customer_message("TECNICO", facts)
                if rendered:
                    return rendered, False
            reply = synthesis or "Posso ajudar com uma recomendacao tecnica se voce me passar mais contexto."
            reply += "\n\nQuer que eu te ajude a escolher e comprar?"
            return reply, False

        missing = _infer_missing_fields(product_hint, context_for_gate)
        field = missing[0] if missing else None
        question = _question_for_field(product_hint, field or "application")
        _apply_asked_context_fields(session_id, st, field or "application")
        return question, False

    return None


def handle_message(message: str, session_id: str) -> Tuple[str, bool]:
    needs_human = False
    try:
        # Pending prompt handling with interruption support
        st_initial = get_state(session_id)
        pending_prompt = get_pending_prompt(session_id)
        if pending_prompt:
            if _matches_expected_kind(message, pending_prompt):
                set_pending_prompt(session_id, None)
                st_initial = get_state(session_id)
            else:
                if _detect_interrupt(message):
                    push_pending_prompt(session_id, pending_prompt)
                    set_pending_prompt(session_id, None)
                    faq_reply = resolve_faq_or_product_query(message) or "Posso ajudar com isso."
                    resumed = pop_pending_prompt(session_id) or pending_prompt
                    reply = _resume_previous_prompt(session_id, faq_reply, resumed)
                    reply = sanitize_reply(reply)
                    save_chat_db(session_id, message, reply, needs_human)
                    return reply, needs_human
                else:
                    reply = pending_prompt.get("text") or "Pode responder?"
                    reply = sanitize_reply(reply)
                    save_chat_db(session_id, message, reply, needs_human)
                    return reply, needs_human

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

        # GATE: produtos genericos sempre passam por contexto de uso antes de quantidades
        if has_product_intent(message):
            hint = extract_product_hint(message)
            if hint and is_generic_product(hint):
                st_generic = get_state(session_id)
                if not st_generic.get("awaiting_usage_context") and not st_generic.get("consultive_investigation"):
                    # limpa pendencias de escolha/quantidade antigas
                    patch_state(
                        session_id,
                        {
                            "pending_product_id": None,
                            "awaiting_qty": False,
                            "last_suggestions": [],
                            "last_hint": None,
                            "last_requested_kg": None,
                        },
                    )
                    known_ctx = extract_known_usage_context(message)
                    reply = (
                        start_usage_context_flow(session_id, hint, known_ctx)
                        if known_ctx
                        else ask_usage_context(session_id, hint)
                    )
                    reply = sanitize_reply(reply)
                    save_chat_db(session_id, message, reply, needs_human)
                    return reply, needs_human

        # pending qty primeiro
        pending = handle_pending_qty(session_id, message)
        if pending:
            pending = sanitize_reply(pending)
            save_chat_db(session_id, message, pending, needs_human)
            return pending, needs_human

        # LLM Router (opt-in) - nao interrompe fluxos pendentes
        st_router = get_state(session_id)
        if not _should_bypass_router(st_router, message):
            state_summary = _build_state_summary(session_id, st_router)
            route = route_intent(message, state_summary)
            if route:
                route_conf = float(route.get("confidence", 0.0) or 0.0)
                if route_conf < settings.LLM_HARD_BLOCK_THRESHOLD or route_conf < settings.ROUTER_CONFIDENCE_THRESHOLD:
                    router_reply = route.get("clarifying_question") or _ROUTER_CLARIFY_MSG
                    logger.info(
                        "llm_low_confidence_fallback component=router confidence=%.2f threshold=%.2f session=%s type=%s",
                        route_conf,
                        settings.ROUTER_CONFIDENCE_THRESHOLD,
                        session_id,
                        "clarify",
                    )
                    router_reply = sanitize_reply(router_reply)
                    save_chat_db(session_id, message, router_reply, needs_human)
                    return router_reply, needs_human

                intent = route.get("intent")
                action = route.get("action")
                product_query = route.get("product_query") or ""
                category_hint = route.get("category_hint") or ""
                constraints = route.get("constraints") or {}
                clarifying_question = route.get("clarifying_question")

                search_query = " ".join(
                    [
                        product_query,
                        category_hint if category_hint not in product_query else "",
                        _constraints_to_query(constraints),
                    ]
                ).strip()

                if action == "SHOW_CATALOG":
                    gated = _gate_generic_usage(session_id, category_hint or product_query or extract_product_hint(message), message)
                    if gated:
                        router_reply, needs_human = gated
                    else:
                        router_reply = _catalog_reply_for_query(session_id, search_query, clarifying_question, category_hint)
                    if router_reply:
                        router_reply = sanitize_reply(router_reply)
                        save_chat_db(session_id, message, router_reply, needs_human)
                        return router_reply, needs_human

                elif action == "SEARCH_PRODUCTS":
                    gated = _gate_generic_usage(session_id, category_hint or product_query or extract_product_hint(message), message)
                    if gated:
                        router_reply, needs_human = gated
                    else:
                        router_reply = _catalog_reply_for_query(session_id, search_query, clarifying_question, category_hint)
                    if router_reply:
                        router_reply = sanitize_reply(router_reply)
                        save_chat_db(session_id, message, router_reply, needs_human)
                        return router_reply, needs_human

                elif action == "ASK_USAGE_CONTEXT":
                    hint = category_hint or product_query or extract_product_hint(message)
                    if hint:
                        planned = _handle_consultive_planner(
                            session_id=session_id,
                            message=message,
                            st=st_router,
                            product_hint=hint,
                            constraints=constraints,
                            fallback_to_usage=True,
                            fallback_to_consultive=False,
                        )
                        if planned:
                            router_reply, needs_human = planned
                            router_reply = sanitize_reply(router_reply)
                            save_chat_db(session_id, message, router_reply, needs_human)
                            return router_reply, needs_human
                    if clarifying_question:
                        router_reply = sanitize_reply(clarifying_question)
                        save_chat_db(session_id, message, router_reply, needs_human)
                        return router_reply, needs_human

                elif action == "ANSWER_WITH_RAG":
                    hint = category_hint or product_query or st_router.get("consultive_product_hint") or st_router.get("last_hint")
                    if intent == "TECHNICAL_QUESTION":
                        knowledge_reply = format_knowledge_answer(message, hint)
                        if knowledge_reply:
                            router_reply = knowledge_reply
                            router_reply = sanitize_reply(router_reply)
                            save_chat_db(session_id, message, router_reply, needs_human)
                            return router_reply, needs_human
                    planned = _handle_consultive_planner(
                        session_id=session_id,
                        message=message,
                        st=st_router,
                        product_hint=hint or "",
                        constraints=constraints,
                        fallback_to_usage=not _has_consultive_context(st_router, constraints),
                        fallback_to_consultive=True,
                    )
                    if planned:
                        router_reply, needs_human = planned
                        router_reply = sanitize_reply(router_reply)
                        save_chat_db(session_id, message, router_reply, needs_human)
                        return router_reply, needs_human

                elif action == "HANDOFF_CHECKOUT":
                    checkout_reply, checkout_needs = handle_checkout(message, session_id)
                    if checkout_reply:
                        needs_human = checkout_needs
                        checkout_reply = sanitize_reply(checkout_reply)
                        save_chat_db(session_id, message, checkout_reply, needs_human)
                        return checkout_reply, needs_human

                elif action == "ASK_CLARIFYING_QUESTION":
                    router_reply = clarifying_question or "Pode explicar melhor o que voce precisa?"
                    router_reply = sanitize_reply(router_reply)
                    save_chat_db(session_id, message, router_reply, needs_human)
                    return router_reply, needs_human
        hint_check = extract_product_hint(message)

        # NOVO: investigacao consultiva progressiva (modo avancado)
        from app.flows.consultive_investigation import continue_investigation
        st_fresh = get_state(session_id)
        if st_fresh.get("consultive_investigation") and not (
            hint_check and is_generic_product(hint_check) and has_product_intent(message)
        ):
            investigation_reply = continue_investigation(session_id, message)
        else:
            investigation_reply = None
        if investigation_reply:
            investigation_reply = sanitize_reply(investigation_reply)
            save_chat_db(session_id, message, investigation_reply, needs_human)
            return investigation_reply, needs_human

        # NOVO: resposta de contexto de uso (modo consultivo pre-venda)
        st_fresh = get_state(session_id)
        if st_fresh.get("awaiting_usage_context") and not (
            hint_check and is_generic_product(hint_check) and has_product_intent(message)
        ):
            usage_ctx_reply = handle_usage_context_response(session_id, message)
        else:
            usage_ctx_reply = None
        if usage_ctx_reply:
            usage_ctx_reply = sanitize_reply(usage_ctx_reply)
            save_chat_db(session_id, message, usage_ctx_reply, needs_human)
            return usage_ctx_reply, needs_human

        # prefs-only (entrega/pix/cep/bairro)
        if message_is_preferences_only(message, session_id):
            reply = reply_after_preference(session_id)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, needs_human)
            return reply, needs_human

        # NOVO: validacao passiva de interesse (apos recomendacao consultiva)
        st = get_state(session_id)
        if st.get("consultive_recommendation_shown") and not st.get("last_suggestions"):
            t = norm(message)

            # Sinal positivo - entra em modo de venda
            if any(w in t for w in ["sim", "faz", "sentido", "quero", "vou levar", "me interessa", "boa", "ok"]):
                hint = st.get("consultive_product_hint")
                if hint:
                    summary = st.get("consultive_last_summary") or ""
                    known_context = _build_known_context(
                        st,
                        st.get("consultive_catalog_constraints") or {},
                    )
                    catalog_result = _search_consultive_catalog(
                        product_hint=hint,
                        summary_text=summary,
                        known_context=known_context,
                        query_base=hint,
                    )
                    products = catalog_result.get("items") or []
                    if products:
                        last_suggestions = []
                        for p in products:
                            pid = _safe_option_id(p)
                            if pid:
                                last_suggestions.append({"id": pid, "nome": _safe_option_name(p)})

                        patch_state(
                            session_id,
                            {
                                "consultive_investigation": False,
                                "consultive_recommendation_shown": False,
                                "last_suggestions": last_suggestions,
                                "last_hint": hint,
                            },
                        )

                        warning = catalog_result.get("warning_text")
                        header = "Otimo! Aqui estao as opcoes:\n\n"
                        reply = ""
                        if warning:
                            reply += warning + "\n\n"
                        reply += f"{header}{format_options(products)}\n\n"
                        reply += "Qual voce prefere? (responda 1, 2, 3... ou o nome)"
                        reply = sanitize_reply(reply)
                        save_chat_db(session_id, message, reply, needs_human)
                        return reply, needs_human

            # Sinal negativo - pede clarificacao
            elif any(w in t for w in ["nao", "outro", "diferente"]):
                patch_state(
                    session_id,
                    {
                        "consultive_investigation": False,
                        "consultive_recommendation_shown": False,
                    },
                )
                reply = "Sem problemas! Me diga mais sobre o que voce precisa, que eu posso ajudar."
                reply = sanitize_reply(reply)
                save_chat_db(session_id, message, reply, needs_human)
                return reply, needs_human
        # escolha em sugestoes
        choice = handle_suggestions_choice(session_id, message)
        if choice:
            choice = sanitize_reply(choice)
            save_chat_db(session_id, message, choice, needs_human)
            return choice, needs_human

        # MODO CONSULTIVO - perguntas abertas antes de tentar vender
        if is_consultive_question(message):
            # Verifica se hÃ¡ produto em contexto (Ãºltima busca/sugestÃ£o)
            st = get_state(session_id)
            context_product = None
            suggestions = st.get("suggestions", [])
            if suggestions:
                # Pega o primeiro produto da Ãºltima sugestÃ£o como contexto
                context_product = suggestions[0].get("nome") if suggestions else None

            consultive_reply, consultive_needs = answer_consultive_question(message, context_product)
            needs_human = consultive_needs
            consultive_reply = sanitize_reply(consultive_reply)
            save_chat_db(session_id, message, consultive_reply, needs_human)
            return consultive_reply, needs_human

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
