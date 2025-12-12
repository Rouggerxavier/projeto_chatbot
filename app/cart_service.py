from typing import Tuple
from sqlalchemy.orm import Session
from database import SessionLocal, Orcamento, ItemOrcamento, Produto

def get_orcamento_aberto(db: Session, session_id: str) -> Orcamento:
    orc = (
        db.query(Orcamento)
        .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
        .first()
    )
    if not orc:
        orc = Orcamento(user_id=session_id, status="aberto", total_aproximado=0)
        db.add(orc)
        db.flush()
    return orc

def recompute_orcamento_total(db: Session, orc: Orcamento) -> None:
    itens = db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).all()
    total = 0.0
    for it in itens:
        total += float(it.subtotal)
    orc.total_aproximado = total
    db.flush()

def add_item_to_orcamento(session_id: str, produto: Produto, quantidade: float) -> Tuple[bool, str]:
    db: Session = SessionLocal()
    try:
        orc = get_orcamento_aberto(db, session_id)
        preco = float(produto.preco) if produto.preco is not None else 0.0
        subtotal_add = round(quantidade * preco, 2)

        item = (
            db.query(ItemOrcamento)
            .filter(ItemOrcamento.id_orcamento == orc.id, ItemOrcamento.id_produto == produto.id)
            .first()
        )
        if not item:
            item = ItemOrcamento(
                id_orcamento=orc.id,
                id_produto=produto.id,
                quantidade=quantidade,
                valor_unitario=preco,
                subtotal=subtotal_add,
            )
            db.add(item)
        else:
            nova_qtd = float(item.quantidade) + float(quantidade)
            item.quantidade = nova_qtd
            item.valor_unitario = preco
            item.subtotal = round(nova_qtd * preco, 2)

        recompute_orcamento_total(db, orc)
        db.commit()
        return True, "Item adicionado ao orçamento."
    except Exception as e:
        db.rollback()
        return False, f"Erro ao adicionar no orçamento: {e}"
    finally:
        db.close()

def reset_orcamento(session_id: str) -> str:
    db: Session = SessionLocal()
    try:
        orc = (
            db.query(Orcamento)
            .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
            .first()
        )
        if not orc:
            return "Seu orçamento já está vazio."
        db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).delete()
        orc.total_aproximado = 0
        db.commit()
        return "Zerei seu orçamento atual."
    except Exception as e:
        db.rollback()
        return f"Tive um problema ao limpar o orçamento: {e}"
    finally:
        db.close()

def format_orcamento(session_id: str) -> str:
    db: Session = SessionLocal()
    try:
        orc = (
            db.query(Orcamento)
            .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
            .first()
        )
        if not orc:
            return "Seu orçamento está vazio."

        itens = db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).all()
        if not itens:
            return "Seu orçamento está vazio."

        linhas = ["Resumo do orçamento:"]
        total = 0.0
        for it in itens:
            prod = it.produto
            if not prod:
                continue
            qtd = float(it.quantidade)
            vu = float(it.valor_unitario)
            sub = float(it.subtotal)
            total += sub
            linhas.append(f"- {qtd:.0f} x {prod.nome} (R$ {vu:.2f} cada) = R$ {sub:.2f}")

        linhas.append(f"\nTotal aproximado: R$ {total:.2f}")
        return "\n".join(linhas)
    finally:
        db.close()
