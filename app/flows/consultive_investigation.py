"""
Investigação progressiva para modo consultivo avançado.

Coleta contexto de aplicação gradualmente antes de recomendar produtos.

Exemplo de fluxo:
    User: "quero cimento"
    Bot: "É pra qual uso?"
    User: "pra laje"
    Bot: "É área interna ou externa?"  ← INVESTIGAÇÃO PROGRESSIVA
    User: "externa"
    Bot: "Coberta ou exposta à chuva/sol?"
    User: "exposta"
    Bot: "Uso residencial ou carga pesada?"
    User: "residencial"
    Bot: [recomendação técnica com explicação + produtos]
"""
from typing import Optional, Dict, List, Callable, Any
from app.session_state import get_state, patch_state
from app.text_utils import norm
from app.search_utils import extract_catalog_constraints_from_consultive
from app.product_search import db_find_best_products_with_constraints


# Fluxos de investigação por produto genérico
INVESTIGATION_FLOWS: Dict[str, List[Dict[str, Any]]] = {
    "cimento": [
        {
            "step": 1,
            "question": "Entendi, é pra {application}. É **área interna** ou **externa**?",
            "field": "consultive_environment",
            "options": ["interna", "externa", "interno", "externo"],
        },
        {
            "step": 2,
            "question": "Certo. É local **coberto** ou **exposto** à chuva/sol?",
            "field": "consultive_exposure",
            "options": ["coberto", "exposto", "coberta", "exposta"],
            "skip_if": lambda st: st.get("consultive_environment") in ["interna", "interno"],
        },
        {
            "step": 3,
            "question": "E é uso **residencial** ou **carga pesada** (ex: garagem, piso comercial)?",
            "field": "consultive_load_type",
            "options": ["residencial", "carga pesada", "comercial", "pesado", "garagem"],
        },
    ],
    "tinta": [
        {
            "step": 1,
            "question": "Entendi. É pra pintar **parede**, **madeira** ou **metal**?",
            "field": "consultive_surface",
            "options": ["parede", "madeira", "metal", "ferro"],
        },
        {
            "step": 2,
            "question": "É **área interna** ou **externa**?",
            "field": "consultive_environment",
            "options": ["interna", "externa", "interno", "externo"],
        },
    ],
    "areia": [
        {
            "step": 1,
            "question": "Entendi, é pra {application}. Precisa de acabamento **fino** ou pode ser **médio/grosso**?",
            "field": "consultive_grain",
            "options": ["fino", "fina", "medio", "média", "grosso", "grossa"],
        },
    ],
    "brita": [
        {
            "step": 1,
            "question": "Ok, é pra {application}. Qual tamanho você precisa? **Brita 1** (pequena), **2** (média) ou **3/4** (grande)?",
            "field": "consultive_size",
            "options": ["1", "2", "3", "4", "pequena", "média", "grande"],
        },
    ],
    "argamassa": [
        {
            "step": 1,
            "question": "Entendi, é pra {application}. É **assentamento**, **reboco** ou **cola**?",
            "field": "consultive_argamassa_type",
            "options": ["assentamento", "reboco", "cola", "colante"],
        },
    ],
}


def start_investigation(session_id: str, product_hint: str, application: str) -> str:
    """
    Inicia investigação progressiva após aplicação informada.

    Args:
        session_id: ID da sessão
        product_hint: Produto genérico (ex: "cimento")
        application: Aplicação informada (ex: "laje")

    Returns:
        Primeira pergunta da investigação
    """
    ph = norm(product_hint)

    # Encontra fluxo de investigação para o produto
    flow = None
    for product_key, investigation_flow in INVESTIGATION_FLOWS.items():
        if product_key in ph:
            flow = investigation_flow
            break

    if not flow:
        # Produto sem fluxo definido, pula investigação
        return None

    # Salva estado inicial
    patch_state(session_id, {
        "consultive_investigation": True,
        "consultive_application": application,
        "consultive_product_hint": product_hint,
        "consultive_investigation_step": 0,
    })

    # Primeira pergunta
    first_question = flow[0]
    question_text = first_question["question"].format(application=application)

    return question_text


def continue_investigation(session_id: str, message: str) -> Optional[str]:
    """
    Processa resposta de investigação e avança para próximo passo.

    Args:
        session_id: ID da sessão
        message: Resposta do usuário

    Returns:
        Próxima pergunta ou None se investigação completa
    """
    st = get_state(session_id)

    if not st.get("consultive_investigation"):
        return None

    product_hint = st.get("consultive_product_hint")
    application = st.get("consultive_application")
    current_step = st.get("consultive_investigation_step", 0)

    if not product_hint:
        # Estado inconsistente, limpa
        patch_state(session_id, {"consultive_investigation": False})
        return None

    ph = norm(product_hint)

    # Carrega fluxo de investigação
    flow = None
    for product_key, investigation_flow in INVESTIGATION_FLOWS.items():
        if product_key in ph:
            flow = investigation_flow
            break

    if not flow:
        # Sem fluxo, encerra investigação
        patch_state(session_id, {"consultive_investigation": False})
        return None

    # Processa resposta do passo atual
    if current_step < len(flow):
        current_question = flow[current_step]
        field = current_question["field"]
        options = current_question["options"]

        # Extrai resposta da mensagem
        answer = _extract_answer(message, options)

        if answer:
            # Salva resposta
            patch_state(session_id, {field: answer})

    # Avança para próximo passo
    next_step = current_step + 1

    # Verifica se há próximo passo
    while next_step < len(flow):
        next_question = flow[next_step]

        # Verifica condição de skip
        skip_if = next_question.get("skip_if")
        if skip_if and callable(skip_if):
            if skip_if(st):
                # Pula esta pergunta
                next_step += 1
                continue

        # Atualiza passo
        patch_state(session_id, {"consultive_investigation_step": next_step})

        # Retorna próxima pergunta
        question_text = next_question["question"].format(application=application or "")
        return question_text

    # Investigação completa, gera recomendação técnica
    from app.flows.technical_recommendations import get_technical_recommendation, format_recommendation_text

    patch_state(session_id, {
        "consultive_investigation_step": next_step,
        "consultive_recommendation_shown": True,
    })

    # Monta contexto para recomendacao tecnica
    st_fresh = get_state(session_id)  # Recarrega estado com as respostas coletadas
    context = {
        "product": product_hint,
        "application": application,
        "environment": st_fresh.get("consultive_environment"),
        "exposure": st_fresh.get("consultive_exposure"),
        "load_type": st_fresh.get("consultive_load_type"),
        "surface": st_fresh.get("consultive_surface"),
        "grain": st_fresh.get("consultive_grain"),
        "size": st_fresh.get("consultive_size"),
    }

    # Busca produtos com coerencia consultiva
    enriched_query = f"{product_hint} {application}"
    rec = get_technical_recommendation(context)
    constraints = extract_catalog_constraints_from_consultive(
        rec.get("reasoning", ""),
        product_hint,
        context,
    )
    category_hint = constraints.get("category_hint") or product_hint
    must_terms = constraints.get("must_terms") or []
    should_terms = constraints.get("should_terms") or []

    patch_state(session_id, {
        "consultive_last_summary": rec.get("reasoning", ""),
        "consultive_catalog_constraints": constraints,
    })

    products = db_find_best_products_with_constraints(
        enriched_query,
        k=6,
        category_hint=category_hint,
        must_terms=must_terms,
        strict=True,
    )

    unavailable_specs = []
    if not products and must_terms:
        unavailable_specs = list(must_terms)

    if not products:
        products = db_find_best_products_with_constraints(
            enriched_query or product_hint,
            k=6,
            category_hint=category_hint,
            should_terms=should_terms,
            strict=False,
        )

    if not products:
        products = db_find_best_products_with_constraints(
            product_hint,
            k=6,
            category_hint=category_hint,
            strict=False,
        )

    if not products:
        # Nao encontrou produtos
        patch_state(session_id, {
            "consultive_investigation": False,
            "consultive_recommendation_shown": False,
        })
        return (
            f"Hmm, nao encontrei {product_hint} especifico para {application} no catalogo agora.\n\n"
            "Quer tentar outro produto ou posso te ajudar de outra forma?"
        )

    reply = format_recommendation_text(rec, products, context=context)
    if unavailable_specs:
        spec_text = ", ".join(unavailable_specs).upper()
        warning = (
            f"Nao encontrei {spec_text} no catalogo agora, "
            "mas posso sugerir opcoes disponiveis:\n\n"
        )
        reply = warning + reply

    return reply


def is_investigation_complete(session_id: str) -> bool:
    """
    Verifica se investigação foi completada.

    Args:
        session_id: ID da sessão

    Returns:
        True se investigação completa
    """
    st = get_state(session_id)

    if not st.get("consultive_investigation"):
        return False

    product_hint = st.get("consultive_product_hint")
    current_step = st.get("consultive_investigation_step", 0)

    if not product_hint:
        return False

    ph = norm(product_hint)

    # Carrega fluxo
    flow = None
    for product_key, investigation_flow in INVESTIGATION_FLOWS.items():
        if product_key in ph:
            flow = investigation_flow
            break

    if not flow:
        return False

    # Completo se passou de todos os passos
    return current_step >= len(flow)


def _extract_answer(message: str, options: List[str]) -> Optional[str]:
    """
    Extrai resposta da mensagem do usuário.

    Args:
        message: Mensagem do usuário
        options: Opções válidas

    Returns:
        Resposta identificada ou None
    """
    t = norm(message)

    # Remove palavras de ligação
    t = t.replace(" pra ", " ").replace(" para ", " ").replace(" em ", " ")
    t = t.replace(" e ", " ").replace(" ou ", " ")

    # Busca opções
    for option in options:
        if option in t:
            return option

    # Não identificou, retorna mensagem limpa
    return t.strip()
