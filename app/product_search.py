import re
from typing import List, Optional

from sqlalchemy.orm import Session

from database import SessionLocal, Produto
from app.text_utils import norm


def db_get_product_by_id(prod_id: int) -> Optional[Produto]:
    """Busca um produto ativo pelo ID."""
    db: Session = SessionLocal()
    try:
        return (
            db.query(Produto)
            .filter(Produto.id == int(prod_id), Produto.ativo == True)  # noqa: E712
            .first()
        )
    finally:
        db.close()


def _score_product(query_words: List[str], p: Produto) -> int:
    text = f"{p.nome or ''} {p.descricao or ''}"
    t = norm(text)

    score = 0
    for w in query_words:
        if w in t:
            score += 2
    # pequeno bônus se bater no começo do nome
    if p.nome:
        name = norm(p.nome)
        for w in query_words:
            if name.startswith(w):
                score += 1
    return score


def db_find_best_products(query: str, k: int = 6) -> List[Produto]:
    """
    Retorna os k produtos mais relevantes (ativos) para a string query.
    Heurística simples por palavras-chave (sem embeddings).
    """
    q = norm(query)
    words = [w for w in re.split(r"\s+", q) if len(w) >= 2]

    db: Session = SessionLocal()
    try:
        produtos = db.query(Produto).filter(Produto.ativo == True).all()  # noqa: E712
        if not produtos:
            return []

        scored = []
        for p in produtos:
            s = _score_product(words, p)
            if s > 0:
                scored.append((s, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [p for _, p in scored[:k]]

        # fallback: se nada pontuou, devolve alguns quaisquer
        if not top:
            top = produtos[:k]

        return top
    finally:
        db.close()


def format_options(produtos: List[Produto]) -> str:
    """
    Formata lista numerada: "1) Nome — R$ .../UN — estoque ..."
    """
    linhas = []
    for i, p in enumerate(produtos, start=1):
        preco = float(p.preco) if p.preco is not None else 0.0
        un = p.unidade or "UN"
        estoque = float(p.estoque_atual) if p.estoque_atual is not None else 0.0
        linhas.append(f"{i}) {p.nome} — R$ {preco:.2f}/{un} — estoque {estoque:.0f}")
    return "\n".join(linhas)


def parse_choice_indices(message: str, max_len: int) -> List[int]:
    """
    Aceita: "1", "1 e 3", "1,3", "2 3"
    Retorna índices 0-based válidos.
    """
    t = norm(message)

    nums = re.findall(r"\d+", t)
    if not nums:
        return []

    idxs = []
    for n in nums:
        val = int(n)
        if 1 <= val <= max_len:
            idxs.append(val - 1)

    # remove duplicados mantendo ordem
    out = []
    seen = set()
    for x in idxs:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out
