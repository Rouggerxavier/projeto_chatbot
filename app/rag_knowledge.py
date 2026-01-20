import json
import os
import threading
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma


# Diretórios e modelo
EMBED_MODEL_NAME = os.getenv(
    "EMBED_MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
CHROMA_DIR = os.getenv("CHROMA_KNOWLEDGE_DIR", os.path.join("data", "chroma_knowledge"))
CHROMA_COLLECTION = os.getenv("CHROMA_KNOWLEDGE_COLLECTION", "knowledge_base")
FAQ_PATH = os.getenv("KNOWLEDGE_FAQ_PATH", os.path.join("data", "knowledge", "faq.json"))

# Estado interno (thread-safe)
_lock = threading.Lock()
_embeddings: Optional[HuggingFaceEmbeddings] = None
_vectorstore: Optional[Chroma] = None
_index_built: bool = False


def _get_embeddings() -> Optional[HuggingFaceEmbeddings]:
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    try:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME)
    except Exception as e:
        print(f"[knowledge] Falha ao carregar embeddings ({EMBED_MODEL_NAME}): {e}")
        _embeddings = None
    return _embeddings


def _load_faq_docs() -> List[Document]:
    if not os.path.exists(FAQ_PATH):
        print(f"[knowledge] FAQ nao encontrado em {FAQ_PATH}")
        return []

    try:
        with open(FAQ_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[knowledge] Erro lendo FAQ: {e}")
        return []

    docs: List[Document] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        content = (entry.get("content") or "").strip()
        if not content:
            continue
        doc = Document(
            page_content=content,
            metadata={
                "id": entry.get("id"),
                "title": entry.get("title"),
                "tags": entry.get("tags") or [],
            },
        )
        docs.append(doc)
    return docs


def _ensure_index_ready(force: bool = False) -> bool:
    global _vectorstore, _index_built

    with _lock:
        if not force and _index_built and _vectorstore is not None:
            return True

        embeddings = _get_embeddings()
        if embeddings is None:
            return False

        # Se force, apaga o diretório para reconstruir
        if force and os.path.exists(CHROMA_DIR):
            try:
                import shutil
                shutil.rmtree(CHROMA_DIR, ignore_errors=True)
            except Exception as e:
                print(f"[knowledge] Nao consegui limpar o indice: {e}")

        docs = _load_faq_docs()
        if not docs:
            print("[knowledge] Nenhum documento para indexar.")
            return False

        try:
            _vectorstore = Chroma.from_documents(
                documents=docs,
                embedding=embeddings,
                persist_directory=CHROMA_DIR,
                collection_name=CHROMA_COLLECTION,
            )
            _index_built = True
            return True
        except Exception as e:
            print(f"[knowledge] Falha ao construir indice: {e}")
            _vectorstore = None
            _index_built = False
            return False


def rebuild_knowledge_index(force: bool = False) -> int:
    """Reconstrói o índice de conhecimento e retorna a contagem de docs."""
    ok = _ensure_index_ready(force=force)
    if not ok or _vectorstore is None:
        return 0
    try:
        count = _vectorstore._collection.count()  # type: ignore[attr-defined]
    except Exception:
        count = 0
    return int(count)


def search_knowledge(query: str, k: int = 5, min_score: float = 0.35) -> List[Dict[str, Any]]:
    """Busca no FAQ técnico usando similaridade. Retorna lista com metadados."""
    if not query or not query.strip():
        return []

    if not _ensure_index_ready():
        return []

    try:
        docs_scores = _vectorstore.similarity_search_with_relevance_scores(query, k=k)  # type: ignore[operator]
    except Exception as e:
        print(f"[knowledge] Falha na busca: {e}")
        return []

    results: List[Dict[str, Any]] = []
    for doc, score in docs_scores:
        s = float(score or 0.0)
        if s < float(min_score):
            continue
        md = doc.metadata or {}
        results.append(
            {
                "id": md.get("id"),
                "title": md.get("title"),
                "content": doc.page_content,
                "score": s,
            }
        )

    results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return results


def format_knowledge_answer(question: str, hint: Optional[str] = None, k: int = 3) -> Optional[str]:
    """
    Formata uma resposta curta baseada no FAQ tecnico.
    Retorna None se nao houver match suficiente.
    """
    query = " ".join(filter(None, [question or "", hint or ""])).strip()
    hits = search_knowledge(query, k=k)
    if not hits:
        return None

    top_hits = hits[: min(k, 2)]
    lines = ["Encontrei orientacoes tecnicas para sua pergunta:"]
    for h in top_hits:
        snippet = (h.get("content") or "").strip()
        if len(snippet) > 420:
            snippet = snippet[:417] + "..."
        title = h.get("title") or "Referencia tecnica"
        lines.append(f"- {title}: {snippet}")
    lines.append("Fonte: base tecnica interna (valores aproximados; confirme em obra/engenharia quando for estrutural).")
    return "\n".join(lines)
