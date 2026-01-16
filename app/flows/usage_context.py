"""
Fluxo de esclarecimento de uso (modo consultivo pré-venda).

Antes de mostrar catálogo, pergunta contexto de uso para produtos genéricos.

Exemplo:
    Usuário: "quero cimento"
    Bot: "Claro 👍 É pra qual uso? (ex.: laje, reboco, piso, área externa...)"
    Usuário: "pra laje externa"
    Bot: [explica + mostra catálogo filtrado]
"""
from typing import Optional, Tuple, List, Any, Dict
from app.session_state import get_state, patch_state
from app.text_utils import norm
from app.product_search import db_find_best_products, format_options
from app.rag_products import search_products_semantic
from app.parsing import extract_product_hint


# Produtos genéricos que sempre precisam de contexto de uso
GENERIC_PRODUCTS = {
    "cimento": {
        "question": "Claro 👍 É pra qual uso? (ex.: laje, reboco, piso, fundação...)",
        "contexts": {
            "laje": ["cp ii", "cp iii", "estrutural"],
            "fundacao": ["cp iii", "cp iv"],
            "reboco": ["cp ii"],
            "piso": ["cp ii"],
            "area externa": ["cp iii", "cp iv"],
        },
    },
    "tinta": {
        "question": "Entendi 👍 É pra pintar onde? (ex.: parede interna, externa, madeira, metal...)",
        "contexts": {
            "parede interna": ["latex", "acrilica"],
            "parede externa": ["acrilica", "textura"],
            "madeira": ["esmalte", "verniz"],
            "metal": ["esmalte", "zarcao"],
        },
    },
    "areia": {
        "question": "Certo 👍 É pra qual finalidade? (ex.: reboco, assentamento, concreto...)",
        "contexts": {
            "reboco": ["areia fina", "areia media"],
            "assentamento": ["areia media"],
            "concreto": ["areia media", "areia grossa"],
            "massa": ["areia fina"],
        },
    },
    "brita": {
        "question": "Beleza 👍 É pra qual aplicação? (ex.: concreto, drenagem, pavimentação...)",
        "contexts": {
            "concreto": ["brita 1", "brita 2"],
            "drenagem": ["brita 3", "brita 4"],
            "pavimentacao": ["brita 2", "brita 3"],
        },
    },
    "argamassa": {
        "question": "Ok 👍 É pra qual uso? (ex.: assentamento, reboco, cola...)",
        "contexts": {
            "assentamento": ["argamassa ac"],
            "reboco": ["argamassa"],
            "cola": ["argamassa colante"],
        },
    },
}


def is_generic_product(hint: str) -> bool:
    """
    Verifica se o produto é genérico (precisa contexto de uso).

    Args:
        hint: Palavra-chave extraída da mensagem

    Returns:
        True se for produto genérico
    """
    if not hint:
        return False

    h = norm(hint)

    # Produto genérico exato
    for generic_key in GENERIC_PRODUCTS.keys():
        if generic_key in h:
            # Evita falso positivo se já vier específico (ex: "cimento cp ii")
            # Mas ignora se a keyword específica é exatamente igual ao genérico
            for contexts in GENERIC_PRODUCTS[generic_key]["contexts"].values():
                for ctx_keyword in contexts:
                    # Se encontrou palavra específica E ela é diferente do produto genérico
                    if ctx_keyword in h and ctx_keyword != generic_key:
                        return False
            return True

    return False


def ask_usage_context(session_id: str, hint: str) -> str:
    """
    Pergunta contexto de uso para produto genérico.

    Args:
        session_id: ID da sessão
        hint: Produto solicitado

    Returns:
        Pergunta formatada
    """
    h = norm(hint)

    # Encontra o produto genérico
    question = None
    for generic_key, config in GENERIC_PRODUCTS.items():
        if generic_key in h:
            question = config["question"]
            break

    if not question:
        # Fallback genérico
        question = f"Claro 👍 É pra qual uso você precisa?"

    # Salva estado
    patch_state(session_id, {
        "awaiting_usage_context": True,
        "usage_context_product_hint": hint,
    })

    return question


def _extract_usage_context(message: str) -> Optional[str]:
    """
    Extrai contexto de uso da resposta do usuário.

    Args:
        message: Resposta do usuário

    Returns:
        Contexto identificado ou None
    """
    t = norm(message)

    # Remove palavras de ligação
    t = t.replace(" pra ", " ").replace(" para ", " ").replace(" em ", " ")

    # Busca contextos conhecidos
    all_contexts = set()
    for config in GENERIC_PRODUCTS.values():
        all_contexts.update(config["contexts"].keys())

    for ctx in all_contexts:
        if ctx in t:
            return ctx

    # Se não achou contexto exato, retorna a mensagem limpa (uso genérico)
    return t.strip()


def _build_consultive_reply(product_hint: str, usage_context: str, products: List[Any]) -> str:
    """
    Constrói resposta consultiva baseada no contexto de uso.

    Args:
        product_hint: Produto solicitado
        usage_context: Contexto de uso informado
        products: Lista de produtos encontrados

    Returns:
        Resposta formatada
    """
    ph = norm(product_hint)
    uc = norm(usage_context)

    # Mapeamento de recomendações
    recommendations = {
        ("cimento", "laje"): "Para laje, recomendo **cimento CP II ou CP III**, que têm boa resistência estrutural.",
        ("cimento", "fundacao"): "Para fundação, o ideal é **cimento CP III ou CP IV**, mais resistentes a sulfatos.",
        ("cimento", "reboco"): "Para reboco, **cimento CP II** é a melhor escolha, tem boa trabalhabilidade.",
        ("cimento", "piso"): "Para contrapiso, **cimento CP II** funciona bem.",
        ("cimento", "area externa"): "Para área externa, use **cimento CP III ou CP IV**, resistem melhor à umidade.",

        ("tinta", "parede interna"): "Para parede interna, **tinta látex ou acrílica** são ideais.",
        ("tinta", "parede externa"): "Para externa, prefira **tinta acrílica ou textura**, resistem ao tempo.",
        ("tinta", "madeira"): "Para madeira, **esmalte ou verniz** protegem melhor.",
        ("tinta", "metal"): "Para metal, use **esmalte sintético** ou **zarcão** (base).",

        ("areia", "reboco"): "Para reboco, **areia fina ou média** dão melhor acabamento.",
        ("areia", "assentamento"): "Para assentar tijolo/bloco, **areia média** é a indicada.",
        ("areia", "concreto"): "Para concreto, **areia média ou grossa** funcionam bem.",

        ("brita", "concreto"): "Para concreto, **brita 1 ou 2** são as mais usadas.",
        ("brita", "drenagem"): "Para drenagem, **brita 3 ou 4** facilitam o escoamento.",
    }

    # Busca recomendação
    recommendation = None
    for (prod_key, context_key), rec_text in recommendations.items():
        if prod_key in ph and context_key in uc:
            recommendation = rec_text
            break

    # Fallback genérico
    if not recommendation:
        recommendation = f"Para {usage_context}, aqui estão as melhores opções:"

    reply = f"{recommendation}\n\n"
    reply += f"{format_options(products)}\n\n"
    reply += "Qual você prefere? (responda 1, 2, 3... ou o nome)"

    return reply


def handle_usage_context_response(session_id: str, message: str) -> Optional[str]:
    """
    Processa resposta de contexto de uso.

    Args:
        session_id: ID da sessão
        message: Resposta do usuário

    Returns:
        Resposta formatada ou None se não estiver esperando contexto
    """
    st = get_state(session_id)

    if not st.get("awaiting_usage_context"):
        return None

    product_hint = st.get("usage_context_product_hint")
    if not product_hint:
        # Estado inconsistente, limpa
        patch_state(session_id, {
            "awaiting_usage_context": False,
            "usage_context_product_hint": None,
        })
        return None

    # Extrai contexto de uso da resposta
    usage_context = _extract_usage_context(message)

    if not usage_context:
        # Não entendeu, pede novamente
        return "Não entendi bem. Pode me dizer pra que você vai usar? (ex.: laje, reboco, parede externa...)"

    # NOVO: Inicia investigação progressiva em vez de mostrar produtos direto
    from app.flows.consultive_investigation import start_investigation

    # Atualiza estado
    patch_state(session_id, {
        "awaiting_usage_context": False,
        "usage_context_product_hint": None,
        "consultive_investigation": True,
        "consultive_application": usage_context,
        "consultive_product_hint": product_hint,
        "consultive_investigation_step": 0,
    })

    # Inicia investigação
    investigation_reply = start_investigation(session_id, product_hint, usage_context)

    if investigation_reply:
        # Há investigação a fazer
        return investigation_reply

    # Sem investigação (produto não tem fluxo), mostra produtos direto
    # Fallback para comportamento antigo
    from app.flows.consultive_investigation import is_investigation_complete
    from app.flows.technical_recommendations import get_technical_recommendation, format_recommendation_text

    # Marca investigação como completa
    patch_state(session_id, {"consultive_recommendation_shown": True})

    # Busca produtos
    products = db_find_best_products(f"{product_hint} {usage_context}", k=6) or []
    if not products:
        products = db_find_best_products(product_hint, k=6) or []

    if not products:
        reply = (
            f"Hmm, não encontrei {product_hint} específico para {usage_context} no catálogo agora.\n\n"
            "Quer tentar outro produto ou posso te ajudar de outra forma?"
        )
        patch_state(session_id, {
            "consultive_investigation": False,
            "consultive_recommendation_shown": False,
        })
        return reply

    # Busca recomendação técnica
    st = get_state(session_id)
    context = {
        "product": product_hint,
        "application": usage_context,
        "environment": st.get("consultive_environment"),
        "exposure": st.get("consultive_exposure"),
        "load_type": st.get("consultive_load_type"),
        "surface": st.get("consultive_surface"),
        "grain": st.get("consultive_grain"),
        "size": st.get("consultive_size"),
    }

    rec = get_technical_recommendation(context)
    reply = format_recommendation_text(rec, products, context=context)  # NOVO: passa contexto para síntese LLM

    return reply
