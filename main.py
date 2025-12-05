from fastapi import FastAPI
from pydantic import BaseModel as PydanticBaseModel, ValidationError
from dotenv import load_dotenv
import os
from typing import Dict, List, Optional
import traceback

from langchain_groq import ChatGroq
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.tools import tool

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory

from sqlalchemy.orm import Session


from database import SessionLocal, Produto, ChatHistory, init_db


load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
print("DEBUG GROQ_API_KEY:", GROQ_API_KEY)

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY não encontrada. Verifique seu .env")

os.environ["GROQ_API_KEY"] = GROQ_API_KEY

app = FastAPI(title="Chatbot Materiais de Construção")

init_db()

class ChatRequest(PydanticBaseModel):
    message: str
    user_id: Optional[str] = None


class ChatResponse(PydanticBaseModel):
    reply: str
    needs_human: bool = False

class BotOutput(PydanticBaseModel):
    reply: str
    needs_human: bool = False

chat_model = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.3,
)

def build_product_context(query: str, k: int = 6) -> str:
    db: Session = SessionLocal()
    try:
        produtos = db.query(Produto).filter(Produto.ativo == True).all()
        if not produtos:
            return "Nenhum produto cadastrado no momento."

        q = query.lower()
        words = [w for w in q.split() if len(w) > 2]

        scored = []
        for p in produtos:
            text = f"{p.nome} {p.descricao}".lower()
            score = 0
            for w in words:
                if w in text:
                    score += 1
            if score > 0:
                scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_produtos = [p for _, p in scored[:k]]

        if not top_produtos:
            top_produtos = produtos[:k]

        linhas = []
        for p in top_produtos:
            preco_val = float(p.preco) if p.preco is not None else 0.0
            unidade = p.unidade or "UN"
            linhas.append(
                f"{p.nome} (R$ {preco_val:.2f} por {unidade}) - {p.descricao}"
            )

        return "\n".join(linhas)

    except Exception as e:
        print("Erro ao montar contexto de produtos:", e)
        traceback.print_exc()
        return "Não foi possível carregar o catálogo de produtos no momento."
    finally:
        db.close()

BAIRROS_ENTREGA = ["manaíra", "intermares", "aeroclube", "tambaú", "bessa"]


@tool
def verifica_entrega_bairro(bairro: str) -> str:
    b = bairro.strip().lower()
    if b in BAIRROS_ENTREGA:
        return f"Sim, fazemos entrega no bairro {bairro.title()}."
    return f"No momento, não fazemos entrega no bairro {bairro.title()}."


@tool
def informa_horario_funcionamento() -> str:
    return (
        "Nosso horário de funcionamento é de segunda a sexta, das 7h às 18h, "
        "e sábado das 7h às 12h."
    )


def extract_bairro(message: str) -> Optional[str]:
    text = message.lower()
    for bairro in BAIRROS_ENTREGA:
        if bairro in text:
            return bairro
    return None


def apply_tools_if_needed(message: str) -> str:
    lower = message.lower()
    snippets: List[str] = []

    bairro = extract_bairro(message)
    if bairro is not None:
        result = verifica_entrega_bairro.invoke({"bairro": bairro})
        snippets.append(result)

    if "horário" in lower or "hora" in lower or "funcionam" in lower:
        result = informa_horario_funcionamento.invoke({})
        snippets.append(result)

    return "\n".join(snippets)

SYSTEM_PROMPT = """
Você é um atendente virtual de uma loja de material de construção chamada Constrular.

Informações da loja:
- Horário de funcionamento: segunda a sexta, das 7h às 18h, e sábado das 7h as 12h.
- Fazemos entrega para os bairros: Manaíra, Intermares, Aeroclube, Tambáu, e todo o Bessa.
- Prazo médio de entrega: no mesmo dia para pedidos até 15h, ou no dia seguinte.
- Formas de pagamento: dinheiro, cartão de crédito/débito, PIX.

Regras de atendimento gerais:
- Responda sempre de forma direta, objetiva e educada, em português do Brasil.
- Nunca ignore a pergunta principal do cliente. Primeiro responda o que ele pediu, depois faça perguntas complementares se for necessário.
- Quando fizer sentido, pergunte o que a pessoa está construindo/reformando para sugerir produtos melhores. Mas não fique repetindo isso toda hora se o cliente já explicou o contexto.

Sobre uso de produtos e preços:
- Você recebe um CONTEXTO DE CATÁLOGO (variável `context`) com produtos, unidades e preços aproximados.
- Use SEMPRE esse catálogo como base. Não invente produtos que não estão nele.
- Você PODE usar esses preços para montar um orçamento aproximado quando o cliente pedir.
- Quando o cliente informar quantidades (ex.: "10 metros de areia, 50kg de cimento"), calcule um orçamento aproximado:
  - liste os itens com quantidade, preço unitário e subtotal (quantidade x preço)
  - some o total ao final
  - deixe claro que são valores aproximados, sujeitos a alteração na loja.
- Se o produto não estiver no contexto, explique isso, diga que não consegue informar o preço exato e, se possível, sugira um produto parecido sem inventar valor.

Sobre encaminhar para atendente humano (needs_human):
- Marque needs_human = true APENAS nos casos:
  - o cliente pedir desconto, negociação de preço ou condição especial de pagamento,
  - o cliente pedir parcelamento fora do padrão ou condições muito específicas,
  - o cliente quiser um orçamento formal/fechamento de pedido com todos os dados (nome, documento, endereço completo, etc.),
  - ou pedir explicitamente para falar com um atendente/vendedor/pessoa.
- Se for apenas um orçamento simples ou uma dúvida de quantidade de material, responda normalmente e mantenha needs_human = false.

Resumo de comportamento:
- Responda o que o cliente pediu na medida do possível, usando o catálogo e os preços do contexto.
- Não fuja da pergunta.
- Use perguntas adicionais apenas para entender melhor a obra ou completar o atendimento, sem travar a resposta principal.
"""

bot_output_parser = PydanticOutputParser(pydantic_object=BotOutput)

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            SYSTEM_PROMPT
            + """

Abaixo está um trecho do catálogo relevante da loja (context):

{context}

Use esse catálogo para embasar suas sugestões.

Responda SEMPRE no seguinte formato (JSON):

{format_instructions}
            """,
        ),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ]
).partial(format_instructions=bot_output_parser.get_format_instructions())

base_chain = prompt | chat_model | bot_output_parser

store: Dict[str, ChatMessageHistory] = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()

    history = store[session_id]

    if len(history.messages) > 10:
        history.messages = history.messages[-10:]

    return history


chat_with_history = RunnableWithMessageHistory(
    base_chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history",
)

def detect_needs_human_keywords(user_message: str) -> bool:
    text = user_message.lower()

    palavras_atendente = [
        "atendente",
        "vendedor",
        "vendedora",
        "humano",
        "pessoa",
        "falar com alguém",
        "falar com uma pessoa",
        "me liga",
        "pode me ligar",
        "quero falar com",
        "transferir para",
        "me passa para",
    ]

    palavras_sensiveis = [
        "desconto",
        "condição de pagamento",
        "condições de pagamento",
        "parcelamento",
        "preço exato",
        "valor exato",
        "orçamento detalhado",
        "orçamento formal",
        "negociar preço",
        "negociar valor",
        "prazo de pagamento",
    ]

    if any(p in text for p in palavras_atendente):
        return True

    if any(p in text for p in palavras_sensiveis):
        return True

    return False

async def generate_reply(message: str, user_id: Optional[str] = None) -> ChatResponse:
    session_id = user_id or "anon"

    context = build_product_context(message)

    try:
        bot_output: BotOutput = await chat_with_history.ainvoke(
            {"input": message, "context": context},
            config={"configurable": {"session_id": session_id}},
        )

        reply_text = bot_output.reply
        needs_human_flag = bot_output.needs_human or detect_needs_human_keywords(message)

    except ValidationError as e:
        print("Erro de validação ao interpretar resposta do modelo:", e)
        traceback.print_exc()

        history_obj = get_session_history(session_id)
        history_msgs: List[BaseMessage] = history_obj.messages

        msgs: List[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT + "\nResponda em português do Brasil."),
            *history_msgs,
            HumanMessage(content=message),
        ]

        raw_resp = await chat_model.ainvoke(msgs)
        reply_text = raw_resp.content
        needs_human_flag = detect_needs_human_keywords(message)

    except Exception as e:
        print("Erro inesperado ao gerar resposta:", e)
        traceback.print_exc()

        reply_text = (
            "Tivemos um problema técnico ao processar sua mensagem agora. "
            "Você pode tentar novamente em alguns instantes ou falar com um atendente humano."
        )
        needs_human_flag = True

    tools_extra = apply_tools_if_needed(message)
    if tools_extra:
        final_reply = f"{reply_text}\n\n{tools_extra}"
    else:
        final_reply = reply_text

    db: Session = SessionLocal()
    try:
        registro = ChatHistory(
            user_id=session_id,
            message=message,
            reply=final_reply,
            needs_human=needs_human_flag,
        )
        db.add(registro)
        db.commit()
    except Exception as e:
        print("Erro ao salvar no banco:", e)
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

    return ChatResponse(reply=final_reply, needs_human=needs_human_flag)

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    result = await generate_reply(body.message, body.user_id)
    return result
