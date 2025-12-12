from contextlib import asynccontextmanager
from fastapi import FastAPI

from database import init_db
from app.api_routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Chatbot Materiais de Construção",
    lifespan=lifespan,
)

app.include_router(router)
