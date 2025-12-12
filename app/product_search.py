import re
from difflib import SequenceMatcher
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from database import SessionLocal, Produto
from app.text_utils import norm
from app.constants import STOPWORDS

def db_find_best_products(query: str, k: int = 5) -> List[Produto]:
    db: Session = SessionLocal()
    try:
        produtos = db.query(Produto).filter(Produto.ativo == True).all()
        if not produtos:
            return []

        qn = norm(query)
        q_words = [w for w in qn.split() if w and w not in STOPWORDS]

        scored: List[Tuple[float, Produto]] = []
        for p in produtos:
            textp = norm(f"{p.nome} {p.descricao or ''}")

            token_score = 0.0
            for w in q_words:
                if re.search(rf"\b{re.escape(w)}\b", textp):
                    token_score += 1.0

            seq_score = SequenceMatcher(None, qn, norm(p.nome)).ratio()
            score = token_score * 2.0 + seq_score

            if score > 0.4:
                scored.append((score, p))

        best_by_name: Dict[str, Tuple[float, Produto]] = {}
        for score, p in scored:
            key = (norm(p.nome) or "").strip()
            if key and (key not in best_by_name or score > best_by_name[key][0]):
                best_by_name[key] = (score, p)

        ranked = sorted(best_by_name.values(), key=lambda x: x[0], reverse=True)
        return [p for _, p in ranked[:k]]
    finally:
        db.close()

def format_options(produtos: List[Produto]) -> str:
    lines = []
    for i, p in enumerate(produtos, start=1):
        preco = float(p.preco) if p.preco is not None else 0.0
        estoque = float(p.estoque_atual) if p.estoque_atual is not None else 0.0
        un = p.unidade or "UN"
        lines.append(f"{i}) {p.nome} — R$ {preco:.2f}/{un} — estoque {estoque:.0f}")
    return "\n".join(lines)

def parse_choice_indices(message: str, max_len: int) -> List[int]:
    t = norm(message)
    nums = [int(x) for x in re.findall(r"\b\d+\b", t)]
    out: List[int] = []
    seen = set()
    for n in nums:
        idx = n - 1
        if 0 <= idx < max_len and idx not in seen:
            out.append(idx)
            seen.add(idx)
    return out
