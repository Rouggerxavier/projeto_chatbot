from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

from database import init_db
from app.api_routes import router
from app.whatsapp_webhook import router as whatsapp_router
from app.rag_products import rebuild_product_index
from app.rag_knowledge import rebuild_knowledge_index

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # cria tabelas
    try:
        init_db()
    except Exception as e:
        # não derruba o servidor se o banco estiver fora no boot
        print("[WARN] init_db falhou:", e)

    # (re)indexa catálogo no vector store
    # catálogo pequeno -> pode recriar sempre no startup sem dor
    try:
        rebuild_product_index()
    except Exception as e:
        # não derruba o servidor se embeddings/chroma falharem
        print("[WARN] rebuild_product_index falhou:", e)
    try:
        rebuild_knowledge_index()
    except Exception as e:
        print("[WARN] rebuild_knowledge_index falhou:", e)
    yield


app = FastAPI(title="Chatbot Materiais de Construção", lifespan=lifespan)
app.include_router(router)
app.include_router(whatsapp_router)
