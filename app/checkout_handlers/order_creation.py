from typing import Optional, Tuple, List
from sqlalchemy.orm import Session

from database import SessionLocal, Cliente, Pedido, Orcamento, ItemOrcamento, PedidoChat
from app.session_state import get_state, patch_state


def summary_from_orcamento_items(items: List[ItemOrcamento]) -> Tuple[str, float]:
    total = 0.0
    linhas = []
    for it in items:
        produto = it.produto
        if not produto:
            continue
        qtd = float(it.quantidade)
        vu = float(it.valor_unitario)
        sub = float(it.subtotal)
        total += sub
        linhas.append(f"{qtd:.0f} x {produto.nome} (R$ {vu:.2f} cada) = R$ {sub:.2f}")
    linhas.append(f"Total aproximado: R$ {total:.2f}")
    return "\n".join(linhas), total


def create_pedido_from_orcamento(session_id: str) -> Tuple[Optional[int], Optional[str]]:
    st = get_state(session_id)

    db: Session = SessionLocal()
    try:
        orc: Optional[Orcamento] = (
            db.query(Orcamento)
            .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
            .first()
        )
        if not orc:
            return None, "Não encontrei um orçamento aberto para finalizar."

        items = (
            db.query(ItemOrcamento)
            .filter(ItemOrcamento.id_orcamento == orc.id)
            .all()
        )
        if not items:
            return None, "Seu orçamento está vazio — adicione algum item antes de finalizar."

        resumo, total = summary_from_orcamento_items(items)

        telefone = st.get("cliente_telefone") or ""
        nome = st.get("cliente_nome") or "Cliente do chat"

        cliente = db.query(Cliente).filter(Cliente.telefone == telefone).first()
        if not cliente:
            cliente = Cliente(nome=nome, telefone=telefone)
            db.add(cliente)
            db.flush()

        forma_pagamento = st.get("forma_pagamento") or ""
        preferencia_entrega = st.get("preferencia_entrega") or ""
        endereco = st.get("endereco") or ""
        bairro = st.get("bairro") or None
        cep = st.get("cep") or None

        pedido = Pedido(
            id_cliente=cliente.id,
            status="novo",
        )
        db.add(pedido)
        db.flush()

        pedido_chat = PedidoChat(
            id_pedido=pedido.id,
            user_id=session_id,
            forma_pagamento=forma_pagamento,
            preferencia_entrega=preferencia_entrega,
            endereco=endereco,
            bairro=bairro,
            cep=cep,
            cliente_nome=nome,
            cliente_telefone=telefone,
            itens=[
                {
                    "id_produto": it.id_produto,
                    "quantidade": float(it.quantidade),
                    "valor_unitario": float(it.valor_unitario),
                    "subtotal": float(it.subtotal),
                }
                for it in items
            ],
            total_aproximado=float(total),
            resumo=resumo,
        )
        db.add(pedido_chat)

        # fecha orçamento
        orc.status = "fechado"

        db.commit()

        patch_state(session_id, {
            "last_order_id": pedido.id,
            "last_order_summary": resumo,
            "last_order_total": total,
            "checkout_mode": False,
        })

        return pedido.id, None

    except Exception as e:
        import traceback
        db.rollback()
        print(f"❌ Erro ao criar pedido: {str(e)}")
        traceback.print_exc()
        return None, "Tive um problema ao finalizar o pedido. Um atendente humano pode revisar."
    finally:
        db.close()
