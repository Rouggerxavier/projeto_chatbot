import re
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from database import SessionLocal, Orcamento, ItemOrcamento, Cliente, Pedido, ItemPedido
from app.session_state import get_state, patch_state
from app.cart_service import format_orcamento
from app.text_utils import norm

CHECKOUT_REGEX = re.compile(r"\b(finalizar|fechar|concluir|confirmar)\b", flags=re.IGNORECASE)

def is_checkout_intent(message: str) -> bool:
    return bool(CHECKOUT_REGEX.search(message or ""))

def parse_phone(message: str) -> Optional[str]:
    m = re.search(r"(\d[\d\s\-().]{7,})", message or "")
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    return digits if len(digits) >= 8 else None

def parse_name(message: str) -> Optional[str]:
    pats = [
        r"meu nome é\s+([A-Za-zÀ-ÿ\s]{2,})",
        r"meu nome eh\s+([A-Za-zÀ-ÿ\s]{2,})",
        r"me chamo\s+([A-Za-zÀ-ÿ\s]{2,})",
        r"sou\s+([A-Za-zÀ-ÿ\s]{2,})",
    ]
    for pat in pats:
        m = re.search(pat, message or "", flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().strip(" .,!;:")
    return None

def get_open_budget(db: Session, session_id: str) -> Optional[Orcamento]:
    return db.query(Orcamento).filter(Orcamento.user_id == session_id, Orcamento.status == "aberto").first()

def budget_is_empty(db: Session, orc: Orcamento) -> bool:
    return db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).count() == 0

def ready_to_checkout(session_id: str) -> bool:
    st = get_state(session_id)

    if not st.get("preferencia_entrega"):
        return False
    if not st.get("forma_pagamento"):
        return False
    if st.get("preferencia_entrega") == "entrega" and not (st.get("cep") or st.get("endereco") or st.get("bairro")):
        return False

    db: Session = SessionLocal()
    try:
        orc = get_open_budget(db, session_id)
        if not orc or budget_is_empty(db, orc):
            return False
        return True
    finally:
        db.close()

def create_order_from_budget(session_id: str) -> Tuple[bool, str, Optional[int]]:
    st = get_state(session_id)
    nome = st.get("cliente_nome")
    tel = st.get("cliente_telefone")
    if not nome or not tel:
        return False, "Faltam dados de contato (nome/telefone).", None

    db: Session = SessionLocal()
    try:
        orc = get_open_budget(db, session_id)
        if not orc:
            return False, "Não encontrei um orçamento aberto para fechar.", None
        if budget_is_empty(db, orc):
            return False, "Seu orçamento está vazio. Adicione pelo menos 1 item antes de finalizar.", None

        cliente = db.query(Cliente).filter(Cliente.telefone == tel).first()
        if not cliente:
            cliente = Cliente(nome=nome, telefone=tel, bairro=st.get("bairro"), endereco=st.get("endereco"))
            db.add(cliente)
            db.flush()
        else:
            cliente.nome = nome
            if st.get("bairro"):
                cliente.bairro = st.get("bairro")
            if st.get("endereco"):
                cliente.endereco = st.get("endereco")

        observacoes = (
            f"Origem: chatbot. "
            f"Entrega/retirada: {st.get('preferencia_entrega')}. "
            f"Pagamento: {st.get('forma_pagamento')}. "
            f"Endereço: {st.get('endereco') or ''}. "
            f"CEP: {st.get('cep') or ''}. "
            f"Bairro: {st.get('bairro') or ''}."
        )

        pedido = Pedido(id_cliente=cliente.id, status="aberto", observacoes=observacoes)
        db.add(pedido)
        db.flush()

        itens_orc = db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).all()
        for it in itens_orc:
            prod = it.produto
            if not prod:
                continue
            db.add(
                ItemPedido(
                    id_pedido=pedido.id,
                    id_produto=prod.id,
                    quantidade=float(it.quantidade),
                    valor_unitario=float(it.valor_unitario),
                    valor_total=float(it.subtotal),
                )
            )

        orc.status = "fechado"
        db.flush()
        db.commit()

        patch_state(session_id, {"last_order_id": pedido.id})
        return True, f"Pedido #{pedido.id} registrado e encaminhado para um atendente finalizar.", pedido.id

    except Exception as e:
        db.rollback()
        return False, f"Erro ao fechar o pedido: {e}", None
    finally:
        db.close()

def handle_checkout(message: str, session_id: str) -> Tuple[Optional[str], bool]:
    st = get_state(session_id)

    # ✅ ativa checkout se o usuário pedir ou se já está tudo pronto
    if is_checkout_intent(message) or ready_to_checkout(session_id):
        patch_state(session_id, {"checkout_active": True})
        st = get_state(session_id)

    if not st.get("checkout_active"):
        return None, False

    # captura nome/telefone
    n = parse_name(message)
    if n:
        patch_state(session_id, {"cliente_nome": n})
        st = get_state(session_id)

    tel = parse_phone(message)
    if tel:
        patch_state(session_id, {"cliente_telefone": tel})
        st = get_state(session_id)

    # faltas do “pronto pra fechar”
    if not st.get("preferencia_entrega"):
        return "Para finalizar: vai ser **entrega** ou **retirada**?", True

    if not st.get("forma_pagamento"):
        return "Qual a forma de pagamento? (**PIX**, **cartão** ou **dinheiro**)", True

    if st.get("preferencia_entrega") == "entrega" and not (st.get("cep") or st.get("endereco") or st.get("bairro")):
        return "Para entrega, me diga o **bairro** ou mande o **CEP/endereço**.", True

    # contato
    if not st.get("cliente_nome"):
        return "Para eu encaminhar ao atendente, me diga seu **nome** (ex.: “me chamo João”).", True

    if not st.get("cliente_telefone"):
        return "Agora me informe seu **telefone** para contato (ex.: 83999999999).", True

    ok, msg, _ = create_order_from_budget(session_id)
    patch_state(session_id, {"checkout_active": False})

    if not ok:
        return msg, True

    return f"✅ {msg}\n\nUm atendente humano vai revisar e finalizar seu pedido agora. 🙋‍♂️\n\n{format_orcamento(session_id)}", True
