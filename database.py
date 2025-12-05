# database.py
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Boolean,
    TIMESTAMP,
    Numeric,
    ForeignKey,
    text,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from dotenv import load_dotenv
import os

load_dotenv()

# Variáveis do .env
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1327")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "constrular")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================
# MODELOS DO BANCO
# ============================

class CategoriaProduto(Base):
    __tablename__ = "categorias_produto"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    descricao = Column(Text)

    produtos = relationship("Produto", back_populates="categoria")


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    descricao = Column(Text)
    unidade = Column(String(10))
    preco = Column(Numeric(10, 2))
    estoque_atual = Column(Numeric(10, 2))
    id_categoria = Column(Integer, ForeignKey("categorias_produto.id"))
    ativo = Column(Boolean, default=True)

    categoria = relationship("CategoriaProduto", back_populates="produtos")


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    telefone = Column(String(20))
    bairro = Column(String(80))
    endereco = Column(Text)


class Pedido(Base):
    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    id_cliente = Column(Integer, ForeignKey("clientes.id"))
    data_pedido = Column(TIMESTAMP, server_default=text("NOW()"))
    status = Column(String(20), default="aberto")
    observacoes = Column(Text)


class ItemPedido(Base):
    __tablename__ = "itens_pedido"

    id = Column(Integer, primary_key=True, index=True)
    id_pedido = Column(Integer, ForeignKey("pedidos.id", ondelete="CASCADE"))
    id_produto = Column(Integer, ForeignKey("produtos.id"))
    quantidade = Column(Numeric(10, 2), nullable=False)
    valor_unitario = Column(Numeric(10, 2), nullable=False)
    valor_total = Column(Numeric(10, 2), nullable=False)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100))
    message = Column(Text)
    reply = Column(Text)
    needs_human = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))


def init_db():
    """Cria as tabelas no banco, se ainda não existirem."""
    Base.metadata.create_all(bind=engine)
