from typing import Any, Dict
from sqlalchemy.orm import Session

from database import SessionLocal, ChatSessionState


DEFAULT_STATE: Dict[str, Any] = {
    # checkout
    "preferencia_entrega": None,   # "entrega" ou "retirada"
    "forma_pagamento": None,       # "pix" / "cartão" / "dinheiro"
    "bairro": None,
    "cep": None,
    "endereco": None,

    # remoção de itens
    "awaiting_remove_choice": False,
    "remove_options": None,
    "awaiting_remove_qty": False,
    "pending_remove_product_id": None,
    "pending_remove_max_qty": None,

    # cliente
    "cliente_nome": None,
    "cliente_telefone": None,

    # controle do fluxo
    "checkout_mode": False,

    # último pedido finalizado
    "last_order_id": None,
    "last_order_summary": None,
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
