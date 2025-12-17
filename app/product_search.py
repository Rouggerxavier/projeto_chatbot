import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database import SessionLocal, Produto
from app.rag_products import search_products_semantic


_GREETINGS = {
    "oi", "ola", "olá", "bom dia", "boa tarde", "boa noite", "eai", "e aí", "ei", "hello", "hi",
}


def _looks_like_greeting(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    if t in _GREETINGS:
        return True
    if any(g in t and len(t) <= len(g) + 5 for g in _GREETINGS):
        return True
    return False


def _sql_fallback_find_products(query: str, k: int = 6) -> List[Produto]:
    db: Session = SessionLocal()
    try:
        q = (query or "").strip()
        if len(q) < 2:
            return []

        return (
            db.query(Produto)
            .filter(
                Produto.ativo == True,  # noqa: E712
                Produto.nome.ilike(f"%{q}%"),
            )
            .limit(k)
            .all()
        )
    finally:
        db.close()


def db_get_product_by_id(product_id: int) -> Optional[Produto]:
    db: Session = SessionLocal()
    try:
        return db.query(Produto).filter(Produto.id == product_id).first()
    finally:
        db.close()


def _normalize_candidate(obj: Any, default_score: float = 0.40) -> Optional[Dict[str, Any]]:
    """
    Normaliza qualquer "candidato" (dict vindo do RAG ou ORM Produto)
    para o formato:
      {"id","nome","preco","unidade","estoque","score"}
    """
    if obj is None:
        return None

    # Caso seja dict (ex.: vindo do RAG)
    if isinstance(obj, dict):
        pid = obj.get("id", None)
        if pid is None:
            pid = obj.get("product_id", None)
        if pid is None:
            return None

        nome = obj.get("nome") or obj.get("name") or ""
        if not nome:
            return None

        preco = obj.get("preco", 0.0)
        unidade = obj.get("unidade") or obj.get("un") or "UN"
        estoque = obj.get("estoque", None)
        if estoque is None:
            estoque = obj.get("estoque_atual", 0)

        score = obj.get("score", default_score)

        try:
            pid = int(pid)
        except Exception:
            return None

        try:
            preco = float(preco) if preco is not None else 0.0
        except Exception:
            preco = 0.0

        try:
            estoque = float(estoque) if estoque is not None else 0.0
        except Exception:
            estoque = 0.0

        try:
            score = float(score) if score is not None else default_score
        except Exception:
            score = default_score

        return {
            "id": pid,
            "nome": nome,
            "preco": preco,
            "unidade": unidade,
            "estoque": estoque,
            "score": score,
        }

    # Caso seja ORM Produto (fallback SQL)
    pid = getattr(obj, "id", None)
    nome = getattr(obj, "nome", "") or ""
    if pid is None or not nome:
        return None

    preco = getattr(obj, "preco", 0.0)
    estoque = getattr(obj, "estoque_atual", 0.0)
    unidade = getattr(obj, "unidade", None) or "UN"

    try:
        preco = float(preco) if preco is not None else 0.0
    except Exception:
        preco = 0.0

    try:
        estoque = float(estoque) if estoque is not None else 0.0
    except Exception:
        estoque = 0.0

    return {
        "id": int(pid),
        "nome": nome,
        "preco": preco,
        "unidade": unidade,
        "estoque": estoque,
        "score": float(default_score),
    }


def db_find_best_products(query: str, k: int = 6) -> List[Dict[str, Any]]:
    """
    Retorna SEMPRE uma lista de dict no formato:
      {"id","nome","preco","unidade","estoque","score"}
    """
    if _looks_like_greeting(query):
        return []

    q = (query or "").strip()
    if len(q) < 2:
        return []

    # 1) tenta semantic search (RAG)
    try:
        sem = search_products_semantic(q, k=k, min_relevance=0.28)
        if sem:
            out: List[Dict[str, Any]] = []
            for item in sem:
                norm = _normalize_candidate(item, default_score=float(item.get("score", 0.65)) if isinstance(item, dict) else 0.65)
                if norm:
                    out.append(norm)
            if out:
                return out[:k]
    except Exception:
        pass

    # 2) fallback SQL ILIKE
    produtos = _sql_fallback_find_products(q, k=k)
    out2: List[Dict[str, Any]] = []
    for p in produtos:
        norm = _normalize_candidate(p, default_score=0.40)
        if norm:
            out2.append(norm)

    return out2[:k]


def format_options(options: List[Dict[str, Any]]) -> str:
    if not options:
        return "Não encontrei opções no catálogo."

    lines = []
    for idx, o in enumerate(options, start=1):
        nome = o.get("nome", "")
        preco = float(o.get("preco", 0.0) or 0.0)
        unidade = o.get("unidade", "UN") or "UN"
        estoque = o.get("estoque", 0) or 0
        lines.append(f"{idx}) {nome} — R$ {preco:.2f}/{unidade} — estoque {estoque:.0f}")
    return "\n".join(lines)


def parse_choice_indices(text: str, max_n: int = None, max_len: int = None) -> List[int]:
    """
    Aceita:
      - "1"
      - "1 e 3"
      - "1,3"
      - "2 4"

    Compatibilidade:
      - versões antigas chamavam parse_choice_indices(text, max_len=...)
      - flows.py chama parse_choice_indices(text, max_n=...)

    Retorna índices **1-based** dentro do range [1, max_total].
    """
    if not text:
        return []

    max_total = max_n if max_n is not None else max_len
    if not max_total or max_total <= 0:
        return []

    nums = re.findall(r"\d+", text)
    out: List[int] = []
    for n in nums:
        i = int(n)
        if 1 <= i <= max_total:
            out.append(i)

    # remove duplicados preservando ordem
    seen = set()
    clean: List[int] = []
    for i in out:
        if i not in seen:
            seen.add(i)
            clean.append(i)
    return clean

    if not text:
        return []
    nums = re.findall(r"\d+", text)
    out: List[int] = []
    for n in nums:
        i = int(n)
        if 1 <= i <= max_len:
            out.append(i - 1)

    seen = set()
    clean: List[int] = []
    for i in out:
        if i not in seen:
            seen.add(i)
            clean.append(i)
    return clean
