from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from database import SessionLocal, ChatSessionState


DEFAULT_STATE: Dict[str, Any] = {
    "preferencia_entrega": None,     # "entrega" | "retirada"
    "bairro": None,
    "cep": None,
    "endereco": None,
    "forma_pagamento": None,         # "pix" | "cartão" | "dinheiro"
    "cliente_nome": None,
    "cliente_telefone": None,
    "checkout_active": False,

    "pending_product_id": None,
    "awaiting_qty": False,
    "pending_suggested_units": None,

    "last_suggestions": [],
    "last_hint": None,
    "last_requested_kg": None,

    "last_order_id": None,
}


def get_state(session_id: str) -> Dict[str, Any]:
    db: Session = SessionLocal()
    try:
        row = db.query(ChatSessionState).filter(ChatSessionState.user_id == session_id).first()
        if not row:
            row = ChatSessionState(user_id=session_id, data=dict(DEFAULT_STATE))
            db.add(row)
            db.commit()
            db.refresh(row)

        # garante chaves padrão
        changed = False
        for k, v in DEFAULT_STATE.items():
            if k not in row.data:
                row.data[k] = v
                changed = True
        if changed:
            db.commit()

        return dict(row.data)
    finally:
        db.close()


def patch_state(session_id: str, patch: Dict[str, Any]) -> None:
    db: Session = SessionLocal()
    try:
        row = db.query(ChatSessionState).filter(ChatSessionState.user_id == session_id).first()
        if not row:
            row = ChatSessionState(user_id=session_id, data=dict(DEFAULT_STATE))
            db.add(row)
            db.flush()

        for k, v in patch.items():
            row.data[k] = v

        db.commit()
    finally:
        db.close()


def set_state_value(session_id: str, key: str, value: Any) -> None:
    patch_state(session_id, {key: value})


def reset_state(session_id: str) -> None:
    patch_state(session_id, dict(DEFAULT_STATE))
