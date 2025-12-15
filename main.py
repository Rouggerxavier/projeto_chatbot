from contextlib import asynccontextmanager
from fastapi import FastAPI

from database import init_db
from app.api_routes import router
from app.rag_products import rebuild_product_index


@asynccontextmanager
async def lifespan(app: FastAPI):
    # cria tabelas
    init_db()

    # (re)indexa catálogo no vector store
    # catálogo pequeno -> pode recriar sempre no startup sem dor
    rebuild_product_index()

    yield


app = FastAPI(title="Chatbot Materiais de Construção", lifespan=lifespan)
app.include_router(router)
