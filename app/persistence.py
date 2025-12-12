from sqlalchemy.orm import Session
from database import SessionLocal, ChatHistory

def save_chat_db(session_id: str, message: str, reply: str, needs_human: bool) -> None:
    db: Session = SessionLocal()
    try:
        registro = ChatHistory(
            user_id=session_id,
            message=message,
            reply=reply,
            needs_human=needs_human,
        )
        db.add(registro)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
