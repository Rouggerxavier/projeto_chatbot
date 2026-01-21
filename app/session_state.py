from typing import Any, Dict
from sqlalchemy.orm import Session

from database import SessionLocal, ChatSessionState


# Estado padrão com email
DEFAULT_STATE: Dict[str, Any] = {
    # cliente
    "cliente_nome": None,
    "cliente_telefone": None,
    "cliente_email": None,  # ✅ EMAIL OBRIGATÓRIO

    # checkout
    "preferencia_entrega": None,   # "entrega" ou "retirada"
    "forma_pagamento": None,       # "pix" / "cartão" / "dinheiro"
    "bairro": None,
    "cep": None,
    "endereco": None,

    # controle do fluxo
    "checkout_mode": False,

    # último pedido finalizado
    "last_order_id": None,
    "last_order_summary": None,
    "last_order_total": None,

    # contexto de uso (modo consultivo pré-venda)
    "awaiting_usage_context": False,
    "usage_context_product_hint": None,

    # investigação consultiva progressiva (modo avançado)
    "consultive_investigation": False,          # Flag: em investigação progressiva
    "consultive_application": None,             # Aplicação informada (ex: "laje")
    "consultive_environment": None,             # Ambiente (interna/externa)
    "consultive_exposure": None,                # Exposição (coberto/exposto)
    "consultive_load_type": None,               # Tipo de carga (residencial/pesado)
    "consultive_investigation_step": 0,         # Passo atual (0-3)
    "consultive_recommendation_shown": False,   # Flag: já mostrou recomendações
    "consultive_product_hint": None,            # Produto sendo investigado
    # anti-repeticao em modo consultivo
    "asked_context_fields": [],
    "last_consultive_question_key": None,
    "consultive_last_summary": None,
    "consultive_catalog_constraints": {},

    # prompts pendentes e interrupcoes
    "pending_prompt": None,
    "state_stack": [],
}


def _merge_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(DEFAULT_STATE)
    merged.update(state or {})
    return merged


def get_state(user_id: str) -> Dict[str, Any]:
    db: Session = SessionLocal()
    try:
        row = db.query(ChatSessionState).filter(ChatSessionState.user_id == user_id).first()
        if not row:
            row = ChatSessionState(user_id=user_id, state=dict(DEFAULT_STATE))
            db.add(row)
            db.commit()
            db.refresh(row)
        return _merge_defaults(row.state or {})
    finally:
        db.close()


def patch_state(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    db: Session = SessionLocal()
    try:
        row = db.query(ChatSessionState).filter(ChatSessionState.user_id == user_id).first()
        if not row:
            row = ChatSessionState(user_id=user_id, state=dict(DEFAULT_STATE))
            db.add(row)
            db.flush()

        st = row.state or {}
        st = _merge_defaults(st)

        for k, v in (updates or {}).items():
            st[k] = v

        row.state = st
        db.commit()
        db.refresh(row)
        return _merge_defaults(row.state or {})
    finally:
        db.close()


def reset_state(user_id: str) -> None:
    db: Session = SessionLocal()
    try:
        row = db.query(ChatSessionState).filter(ChatSessionState.user_id == user_id).first()
        if row:
            row.state = dict(DEFAULT_STATE)
            db.commit()
    finally:
        db.close()


def reset_consultive_context(user_id: str) -> None:
    """
    Reseta APENAS o contexto consultivo, preservando dados do cliente e carrinho.

    CRÍTICO: Deve ser chamado sempre que:
    - Novo pedido genérico é detectado ("quero cimento")
    - Usuário muda de assunto
    - Nova conversa inicia

    Isso IMPEDE que contexto técnico anterior seja reutilizado indevidamente.
    """
    consultive_fields = {
        "awaiting_usage_context": False,
        "usage_context_product_hint": None,
        "consultive_investigation": False,
        "consultive_application": None,
        "consultive_environment": None,
        "consultive_exposure": None,
        "consultive_load_type": None,
        "consultive_investigation_step": 0,
        "consultive_recommendation_shown": False,
        "consultive_product_hint": None,
        "consultive_surface": None,
        "consultive_grain": None,
        "consultive_size": None,
        "consultive_argamassa_type": None,
        "asked_context_fields": [],
        "last_consultive_question_key": None,
        "consultive_last_summary": None,
        "consultive_catalog_constraints": {},
    }
    patch_state(user_id, consultive_fields)


def get_pending_prompt(user_id: str) -> Any:
    st = get_state(user_id)
    return st.get("pending_prompt")


def set_pending_prompt(user_id: str, prompt: Any) -> None:
    patch_state(user_id, {"pending_prompt": prompt})


def push_pending_prompt(user_id: str, prompt: Any) -> None:
    st = get_state(user_id)
    stack = list(st.get("state_stack") or [])
    stack.append(prompt)
    patch_state(user_id, {"state_stack": stack})


def pop_pending_prompt(user_id: str) -> Any:
    st = get_state(user_id)
    stack = list(st.get("state_stack") or [])
    if not stack:
        patch_state(user_id, {"state_stack": []})
        return None
    prompt = stack.pop()
    patch_state(user_id, {"state_stack": stack})
    return prompt
