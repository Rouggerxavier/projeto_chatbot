from typing import Optional, Tuple, List

from sqlalchemy.orm import Session

from database import SessionLocal, Orcamento, ItemOrcamento, Produto


def get_open_orcamento(session_id: str) -> Optional[Orcamento]:
    db: Session = SessionLocal()
    try:
        return (
            db.query(Orcamento)
            .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
            .first()
        )
    finally:
        db.close()


def _get_or_create_open_orcamento(db: Session, session_id: str) -> Orcamento:
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


def add_item_to_orcamento(session_id: str, produto: Produto, quantidade: float) -> Tuple[bool, str]:
    db: Session = SessionLocal()
    try:
        orc = _get_or_create_open_orcamento(db, session_id)

        valor_unit = float(produto.preco) if produto.preco is not None else 0.0
        subtotal = round(float(quantidade) * valor_unit, 2)

        item = (
            db.query(ItemOrcamento)
            .filter(ItemOrcamento.id_orcamento == orc.id, ItemOrcamento.id_produto == produto.id)
            .first()
        )
        if not item:
            item = ItemOrcamento(
                id_orcamento=orc.id,
                id_produto=produto.id,
                quantidade=float(quantidade),
                valor_unitario=valor_unit,
                subtotal=subtotal,
            )
            db.add(item)
        else:
            item.quantidade = float(item.quantidade) + float(quantidade)
            item.subtotal = round(float(item.quantidade) * valor_unit, 2)

        db.flush()

        itens = db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).all()
        total = round(sum(float(it.subtotal) for it in itens), 2)
        orc.total_aproximado = total

        db.commit()

        return True, f"Item adicionado ao orçamento.\nItem: {produto.nome} Quantidade: {float(quantidade):.0f} {produto.unidade or 'UN'} Subtotal aprox.: R$ {subtotal:.2f}"

    except Exception:
        db.rollback()
        return False, "Não consegui adicionar este item agora."
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

        linhas: List[str] = []
        linhas.append("Resumo do orçamento:\n")

        total = 0.0
        for it in itens:
            produto = it.produto
            if not produto:
                continue
            qtd = float(it.quantidade)
            vu = float(it.valor_unitario)
            sub = float(it.subtotal)
            total += sub
            linhas.append(f"{qtd:.0f} x {produto.nome} (R$ {vu:.2f} cada) = R$ {sub:.2f}")

        linhas.append(f"Total aproximado: R$ {total:.2f}")
        return "\n".join(linhas)

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
            return "Seu orçamento já estava vazio. Podemos começar um novo agora. 🙂"

        db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).delete()
        orc.total_aproximado = 0
        db.commit()
        return "Zerei o seu orçamento atual. Podemos começar tudo do zero. 🙂"
    except Exception:
        db.rollback()
        return "Tive um problema ao limpar seu orçamento."
    finally:
        db.close()
