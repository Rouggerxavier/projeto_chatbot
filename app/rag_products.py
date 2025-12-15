from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

from database import SessionLocal, Produto


# ============================
# Configurações do índice
# ============================

# Modelo bom para PT-BR e buscas "parecidas"
EMBED_MODEL_NAME = os.getenv(
    "EMBED_MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join("data", "chroma_products"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "products")

# Controle interno
_lock = threading.Lock()
_embeddings: Optional[HuggingFaceEmbeddings] = None
_vectorstore: Optional[Chroma] = None
_index_built: bool = False
_last_index_count: int = -1


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME)
    return _embeddings


def _produto_to_doc(p: Produto) -> Document:
    preco = float(p.preco) if p.preco is not None else 0.0
    estoque = float(p.estoque_atual) if p.estoque_atual is not None else 0.0
    unidade = (p.unidade or "UN").strip()

    # Conteúdo usado para embedding / busca
    content_parts = [
        f"Nome: {p.nome}",
        f"Descrição: {p.descricao or ''}",
        f"Unidade: {unidade}",
    ]
    content = "\n".join([x for x in content_parts if x.strip()])

    metadata = {
        "id_produto": int(p.id),
        "nome": p.nome,
        "unidade": unidade,
        "preco": preco,
        "estoque": estoque,
        "ativo": bool(p.ativo),
    }

    return Document(page_content=content, metadata=metadata)


def rebuild_products_index(force: bool = False) -> int:
    """
    Recria o índice vetorial a partir do banco (produtos ativos).
    Retorna a quantidade de documentos indexados.
    """
    global _vectorstore, _index_built, _last_index_count

    with _lock:
        db = SessionLocal()
        try:
            produtos = db.query(Produto).filter(Produto.ativo == True).all()
            docs = [_produto_to_doc(p) for p in produtos]

            # Heurística simples: se quantidade não mudou e já existe índice, não refaz
            if not force and _index_built and _last_index_count == len(docs) and _vectorstore is not None:
                return _last_index_count

            os.makedirs(CHROMA_DIR, exist_ok=True)

            embeddings = _get_embeddings()

            # Sempre recria do zero (mais previsível)
            # Apaga a collection anterior removendo o diretório inteiro? (opcional)
            # Aqui a gente simplesmente cria uma nova store e persiste em disco.
            _vectorstore = Chroma.from_documents(
                documents=docs,
                embedding=embeddings,
                collection_name=CHROMA_COLLECTION,
                persist_directory=CHROMA_DIR,
            )
            _vectorstore.persist()

            _index_built = True
            _last_index_count = len(docs)
            return _last_index_count

        finally:
            db.close()


def _ensure_index_ready() -> None:
    global _vectorstore, _index_built
    with _lock:
        if _index_built and _vectorstore is not None:
            return

        os.makedirs(CHROMA_DIR, exist_ok=True)
        embeddings = _get_embeddings()

        # Tenta abrir índice persistido (se existir)
        _vectorstore = Chroma(
            collection_name=CHROMA_COLLECTION,
            embedding_function=embeddings,
            persist_directory=CHROMA_DIR,
        )

        # Se não tiver nada ainda, cria a partir do banco
        # (Chroma não expõe um "count" 100% padronizado em todas versões, então fazemos rebuild se vazio)
        try:
            # Algumas versões: _collection.count()
            count = _vectorstore._collection.count()  # type: ignore[attr-defined]
        except Exception:
            count = 0

        if count == 0:
            rebuild_products_index(force=True)
        else:
            _index_built = True


def search_products(query: str, k: int = 6, min_score: float = 0.15) -> List[Dict[str, Any]]:
    """
    Busca produtos por similaridade semântica.
    Retorna lista de dicts com {id_produto, nome, unidade, preco, estoque, score}.
    """
    if not query or not query.strip():
        return []

    _ensure_index_ready()
    if _vectorstore is None:
        return []

    q = query.strip()

    results: List[Dict[str, Any]] = []
    try:
        # Retorna (Document, score) onde score costuma ser similaridade (depende do backend)
        docs_scores: List[Tuple[Document, float]] = _vectorstore.similarity_search_with_relevance_scores(q, k=k)
    except Exception:
        # fallback caso a versão não suporte relevance_scores
        docs = _vectorstore.similarity_search(q, k=k)
        docs_scores = [(d, 1.0) for d in docs]

    for doc, score in docs_scores:
        md = doc.metadata or {}
        if float(score) < float(min_score):
            continue

        results.append(
            {
                "id_produto": md.get("id_produto"),
                "nome": md.get("nome"),
                "unidade": md.get("unidade"),
                "preco": md.get("preco"),
                "estoque": md.get("estoque"),
                "score": float(score),
            }
        )

    # Ordena maior score primeiro
    results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return results


def format_rag_options(items: List[Dict[str, Any]]) -> str:
    """
    Formata as opções encontradas (para o chatbot mostrar).
    """
    if not items:
        return "Não encontrei nada parecido no catálogo."

    lines = []
    for i, it in enumerate(items, start=1):
        nome = it.get("nome", "—")
        preco = it.get("preco", 0.0)
        unidade = it.get("unidade", "UN")
        estoque = it.get("estoque", 0.0)

        try:
            preco_f = float(preco)
        except Exception:
            preco_f = 0.0

        try:
            estoque_f = float(estoque)
        except Exception:
            estoque_f = 0.0

        lines.append(f"{i}) {nome} — R$ {preco_f:.2f}/{unidade} — estoque {estoque_f:.0f}")

    return "\n".join(lines)

def search_products_semantic(query: str, k: int = 6) -> List[Dict[str, Any]]:
    # compatibilidade com import antigo
    return search_products(query=query, k=k)

def rebuild_product_index(force: bool = False) -> int:
    # alias para compatibilidade com main.py antigo
    return rebuild_products_index(force=force)
