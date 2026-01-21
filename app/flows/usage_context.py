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
from app.session_state import get_state, patch_state, reset_consultive_context
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


def _canonicalize_generic_hint(hint: str) -> str:
    """
    Reduz hint para o produto genérico principal quando possível.
    """
    if not hint:
        return hint

    h = norm(hint)
    for generic_key in GENERIC_PRODUCTS.keys():
        if generic_key in h:
            return generic_key

    return hint


def ask_usage_context(session_id: str, hint: str) -> str:
    """
    Pergunta contexto de uso para produto genérico.

    Args:
        session_id: ID da sessão
        hint: Produto solicitado

    Returns:
        Pergunta formatada
    """
    # CRÍTICO: Limpa contexto consultivo anterior para evitar vazamento de dados
    # Isso impede que contexto de conversas anteriores contamine a nova consulta
    reset_consultive_context(session_id)

    h = norm(hint)
    canonical_hint = _canonicalize_generic_hint(hint)

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
        "usage_context_product_hint": canonical_hint,
    })

    return question


def extract_known_usage_context(message: str) -> Optional[str]:
    """
    Extrai apenas contextos de uso reconhecidos.
    """
    t = norm(message)
    t = t.replace(" pra ", " ").replace(" para ", " ").replace(" em ", " ")

    all_contexts = set()
    for config in GENERIC_PRODUCTS.values():
        all_contexts.update(config["contexts"].keys())

    for ctx in all_contexts:
        if ctx in t:
            return ctx

    return None


def _extract_usage_context(message: str) -> Optional[str]:
    """
    Extrai contexto de uso da resposta do usuario.

    Args:
        message: Resposta do usuario

    Returns:
        Contexto identificado ou None
    """
    t = norm(message)

    # Remove palavras de ligacao
    t = t.replace(" pra ", " ").replace(" para ", " ").replace(" em ", " ")

    ctx = extract_known_usage_context(message)
    if ctx:
        return ctx

    # Se nao achou contexto exato, retorna a mensagem limpa (uso generico)
    return t.strip()


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
        # Nao entendeu, pede novamente
        return "Nao entendi bem. Pode me dizer pra que voce vai usar? (ex.: laje, reboco, parede externa...)"

    reply = start_usage_context_flow(session_id, product_hint, usage_context)
    if reply:
        return reply
    return "Pode me dizer pra que voce vai usar? (ex.: laje, reboco, parede externa...)"


def _safe_option_id(o: Any) -> Optional[int]:
    if o is None:
        return None
    if isinstance(o, dict):
        pid = o.get("id") or o.get("product_id") or o.get("produto_id")
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


def start_usage_context_flow(session_id: str, product_hint: str, usage_context: str) -> Optional[str]:
    """
    Inicia fluxo consultivo quando produto e contexto ja sao conhecidos.
    """
    from app.flows.consultive_investigation import start_investigation
    from app.flows.technical_recommendations import get_technical_recommendation, format_recommendation_text

    # CRÍTICO: Limpa contexto consultivo anterior para evitar vazamento de dados
    reset_consultive_context(session_id)

    canonical_hint = _canonicalize_generic_hint(product_hint)

    patch_state(session_id, {
        "awaiting_usage_context": False,
        "usage_context_product_hint": None,
        "consultive_investigation": True,
        "consultive_application": usage_context,
        "consultive_product_hint": canonical_hint,
        "consultive_investigation_step": 0,
    })

    investigation_reply = start_investigation(session_id, canonical_hint, usage_context)

    if investigation_reply:
        return investigation_reply

    patch_state(session_id, {"consultive_recommendation_shown": True})

    products = db_find_best_products(f"{canonical_hint} {usage_context}", k=6) or []
    if not products:
        products = db_find_best_products(canonical_hint, k=6) or []

    if not products:
        reply = (
            f"Hmm, nao encontrei {canonical_hint} especifico para {usage_context} no catalogo agora.\n\n"
            "Quer tentar outro produto ou posso te ajudar de outra forma?"
        )
        patch_state(session_id, {
            "consultive_investigation": False,
            "consultive_recommendation_shown": False,
        })
        return reply

    # Persistir sugestoes numeradas para permitir selecao por numero
    suggestions = []
    for p in products:
        pid = _safe_option_id(p)
        if pid:
            suggestions.append(
                {
                    "id": pid,
                    "nome": _safe_option_name(p),
                    "context": {"usage_context": usage_context, "product_hint": canonical_hint},
                }
            )
    if suggestions:
        patch_state(
            session_id,
            {
                "last_suggestions": suggestions,
                "last_hint": canonical_hint,
                "last_requested_kg": None,
                "consultive_investigation": False,
            },
        )

    st = get_state(session_id)
    context = {
        "product": canonical_hint,
        "application": usage_context,
        "environment": st.get("consultive_environment"),
        "exposure": st.get("consultive_exposure"),
        "load_type": st.get("consultive_load_type"),
        "surface": st.get("consultive_surface"),
        "grain": st.get("consultive_grain"),
        "size": st.get("consultive_size"),
    }

    rec = get_technical_recommendation(context)
    reply = format_recommendation_text(rec, products, context=context)

    return reply
