from __future__ import annotations

import os
import threading
import math
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
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
_embeddings_failed: bool = False


def _get_embeddings() -> Optional[HuggingFaceEmbeddings]:
    global _embeddings, _embeddings_failed
    
    if _embeddings_failed:
        return None
    
    if _embeddings is not None:
        return _embeddings
    
    offline_mode = os.getenv("HF_OFFLINE", "0") == "1"
    
    if offline_mode:
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"
    
    max_retries = 2 if not offline_mode else 1
    for attempt in range(max_retries):
        try:
            if not offline_mode and attempt == 0:
                os.environ["TRANSFORMERS_OFFLINE"] = "0"
                os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_HUB_OFFLINE"] = "1"
            
            _embeddings = HuggingFaceEmbeddings(
                model_name=EMBED_MODEL_NAME,
                model_kwargs={"trust_remote_code": True},
                encode_kwargs={"normalize_embeddings": True},
            )
            print(f"✅ Modelo de embeddings carregado: {EMBED_MODEL_NAME} (offline={os.environ.get('TRANSFORMERS_OFFLINE', '0')})")
            return _embeddings
        except Exception as e:
            attempt_num = attempt + 1
            error_str = str(e)
            
            if "huggingface.co" in error_str.lower() or "timeout" in error_str.lower() or "connection" in error_str.lower():
                print(f"⚠️ Problema de conexão com HuggingFace (tentativa {attempt_num}/{max_retries})")
                if attempt < max_retries - 1:
                    print("   Tentando novamente em modo offline...")
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    continue
            else:
                print(f"⚠️ Erro ao carregar embeddings: {error_str[:200]}")
            
            if attempt >= max_retries - 1:
                print("❌ Falha ao carregar modelo de embeddings. Buscas semânticas desabilitadas.")
                _embeddings_failed = True
                return None
    
    return None


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
            if embeddings is None:
                print("❌ Não foi possível reconstruir o índice: modelo de embeddings indisponível")
                return 0

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


def _ensure_index_ready() -> bool:
    global _vectorstore, _index_built
    with _lock:
        if _index_built and _vectorstore is not None:
            return True
        
        if _embeddings_failed:
            print("⚠️ Não é possível usar buscas semânticas (modelo de embeddings falhou).")
            return False

        os.makedirs(CHROMA_DIR, exist_ok=True)
        embeddings = _get_embeddings()
        
        if embeddings is None:
            return False

        try:
            # Tenta abrir índice persistido (se existir)
            _vectorstore = Chroma(
                collection_name=CHROMA_COLLECTION,
                embedding_function=embeddings,
                persist_directory=CHROMA_DIR,
            )

            # Se não tiver nada ainda, cria a partir do banco
            try:
                count = _vectorstore._collection.count()  # type: ignore[attr-defined]
            except Exception:
                count = 0

            if count == 0:
                rebuild_products_index(force=True)
            else:
                _index_built = True
            
            return True
        except Exception as e:
            print(f"❌ Erro ao inicializar índice Chroma: {str(e)}")
            return False


def _distance_to_score(x: float) -> float:
    """Converte um 'score' ou 'distance' em algo comparável em [0,1]."""
    try:
        v = float(x)
    except Exception:
        return 0.0
    # Se for distância (>=0): 0 é melhor -> score = 1/(1+dist)
    if v >= 0:
        return 1.0 / (1.0 + v)
    # Se vier similaridade negativa (ex.: dot-product), aplica sigmoid
    try:
        return 1.0 / (1.0 + math.exp(-v))
    except Exception:
        return 0.0


def search_products(query: str, k: int = 6, min_score: float = 0.15) -> List[Dict[str, Any]]:
    """
    Busca produtos por similaridade semântica.
    Retorna lista de dicts com {id_produto, nome, unidade, preco, estoque, score}.

    Evita o warning de "relevance scores fora de [0,1]" usando, primeiro,
    similarity_search_with_score (distância) e convertendo para score.
    """
    if not query or not query.strip():
        return []

    if not _ensure_index_ready():
        print(f"⚠️ Buscas semânticas indisponíveis. Retornando lista vazia para: {query}")
        return []
    
    if _vectorstore is None:
        return []

    q = query.strip()

    docs_scores: List[Tuple[Document, float]] = []

    # 1) preferir "with_score" (geralmente distância)
    try:
        docs_dist = _vectorstore.similarity_search_with_score(q, k=k)  # type: ignore[attr-defined]
        docs_scores = [(doc, _distance_to_score(dist)) for doc, dist in docs_dist]
    except Exception:
        # 2) fallback: relevance_scores (normaliza)
        try:
            raw: List[Tuple[Document, float]] = _vectorstore.similarity_search_with_relevance_scores(q, k=k)
            docs_scores = [(doc, _distance_to_score(score)) for doc, score in raw]
        except Exception:
            # 3) último fallback: sem score
            docs = _vectorstore.similarity_search(q, k=k)
            docs_scores = [(d, 0.5) for d in docs]

    results: List[Dict[str, Any]] = []
    for doc, score in docs_scores:
        md = doc.metadata or {}
        s = float(score)
        if s < float(min_score):
            continue

        results.append(
            {
                "id_produto": md.get("id_produto"),
                "nome": md.get("nome"),
                "unidade": md.get("unidade"),
                "preco": md.get("preco"),
                "estoque": md.get("estoque"),
                "score": s,
            }
        )

    results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return results


def search_products_semantic(query: str, k: int = 6, min_relevance: float = None, min_score: float = None) -> List[Dict[str, Any]]:
    """Compatibilidade com chamadas antigas (min_relevance) e novas (min_score)."""
    if min_score is None:
        min_score = 0.15 if min_relevance is None else float(min_relevance)
    return search_products(query=query, k=k, min_score=float(min_score))

def rebuild_product_index(force: bool = False) -> int:
    # alias para compatibilidade com main.py antigo
    return rebuild_products_index(force=force)
