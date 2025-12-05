import os

import streamlit as st
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage

# ---------------------------------------------------
# Configuração inicial
# ---------------------------------------------------
st.set_page_config(
    page_title="Chatbot Constrular",
    page_icon="🏗️",
    layout="centered",
)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    st.error("GROQ_API_KEY não encontrada. Verifique seu arquivo .env")
    st.stop()

# Opcional, mas ajuda algumas libs a encontrarem:
os.environ["GROQ_API_KEY"] = GROQ_API_KEY

# ---------------------------------------------------
# Modelo Groq
# ---------------------------------------------------
chat_model = ChatGroq(
    model="llama-3.1-8b-instant",  # pode trocar se quiser
    temperature=0.3,
)

SYSTEM_PROMPT = """
Você é um atendente virtual de uma loja de material de construção chamada *Constrular*.

Informações da loja:
- Horário de funcionamento: segunda a sexta, das 7h às 18h, e sábado das 7h as 12h.
- Fazemos entrega para os bairros: Manaíra, Intermares, Aeroclube, Tambáu, e todo o Bessa.
- Prazo médio de entrega: no mesmo dia para pedidos até 15h, ou no dia seguinte.
- Formas de pagamento: dinheiro, cartão de crédito/débito, PIX.

Catálogo básico (exemplos, use para sugerir produtos):
- Cimento CP II 50kg: uso geral em obras, bom para reboco e assentamento.
- Cimento CP III 50kg: indicado para fundações, lajes e estruturas mais pesadas.
- Areia média: usada para reboco e assentamento de tijolos.
- Tijolo 8 furos: indicado para paredes internas.
- Tinta acrílica fosca para interior: boa para paredes internas.
- Tinta acrílica semibrilho para exterior: indicada para áreas externas.

Regras:
- Sempre pergunte o que a pessoa está construindo/reformando antes de indicar produtos.
- Nunca invente preço. Se perguntarem valores, pergunte primeiro se ele quer mais algo para deixar todo o pedido completo e pergunte em seguida se ele já quer ir pro pagamento e assim teria que contatar um atendente.
- Caso o cliente fale que não precisa de mais nada, ou que só precisa de tal material que foi pedido, não ofereça mais nada para não incomodar, mas apenas em casos como esse.
- Fale sempre em português do Brasil, em tom educado, simples e direto.
"""


# ---------------------------------------------------
# Heurística: precisa de atendente humano?
# ---------------------------------------------------
def detect_needs_human(user_message: str) -> bool:
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
        "negociar preço",
        "negociar valor",
        "prazo de pagamento",
        "orçamento",
    ]

    if any(p in text for p in palavras_atendente):
        return True

    if any(p in text for p in palavras_sensiveis):
        return True

    return False


# ---------------------------------------------------
# Estado da sessão
# ---------------------------------------------------
if "messages" not in st.session_state:
    st.session_state["messages"]: list[dict] = []  # {role: "user"/"assistant", "content": str, "needs_human": bool}


def build_langchain_history() -> list[BaseMessage]:
    """Converte o histórico do Streamlit em mensagens do LangChain."""
    history: list[BaseMessage] = []
    for msg in st.session_state["messages"]:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        else:
            history.append(AIMessage(content=msg["content"]))
    return history


def generate_reply(message: str) -> tuple[str, bool]:
    """Gera resposta usando Groq + lógica de encaminhar para humano."""
    needs_human = detect_needs_human(message)
    history = build_langchain_history()

    # Se for caso de humano, não chama o modelo
    if needs_human:
        answer = (
            "Entendi, você quer falar com um atendente humano. "
            "Vou encaminhar seu atendimento para uma pessoa da equipe."
        )
        return answer, True

    # Caso normal: chama modelo
    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        *history,
        HumanMessage(content=message),
    ]

    response = chat_model.invoke(messages)
    return response.content, False


# ---------------------------------------------------
# UI – Sidebar
# ---------------------------------------------------
with st.sidebar:
    st.markdown("## 🏗️ Constrular Chatbot")
    st.markdown(
        """
Bem-vindo ao assistente virtual da **Constrular**!

Aqui você pode:
- Tirar dúvidas sobre materiais de construção  
- Pedir sugestões para reforma/obra  
- Entender melhor que produto usar em cada situação  

⚠️ **Preços reais** não são informados aqui.  
Para valores exatos e formas de pagamento detalhadas,
um atendente humano será acionado.
        """
    )
    if st.button("🔁 Limpar conversa"):
        st.session_state["messages"] = []
        st.experimental_rerun()

# ---------------------------------------------------
# UI – Cabeçalho
# ---------------------------------------------------
st.title("🏗️ Assistente Virtual Constrular")
st.caption("Tire suas dúvidas sobre materiais de construção de forma rápida e simples.")

# ---------------------------------------------------
# Mostrar histórico de mensagens
# ---------------------------------------------------
for msg in st.session_state["messages"]:
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(msg["content"])
    else:
        with st.chat_message("assistant", avatar="🏗️"):
            st.markdown(msg["content"])
            if msg.get("needs_human"):
                st.write("🧑‍💼 *Esse atendimento será encaminhado para um atendente humano.*")

# ---------------------------------------------------
# Entrada de mensagem do usuário
# ---------------------------------------------------
user_input = st.chat_input("Digite sua dúvida sobre materiais de construção...")

if user_input:
    # adiciona mensagem do usuário
    st.session_state["messages"].append(
        {"role": "user", "content": user_input, "needs_human": False}
    )
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    # gera resposta
    with st.chat_message("assistant", avatar="🏗️"):
        with st.spinner("Pensando..."):
            reply, needs_human = generate_reply(user_input)
        st.markdown(reply)
        if needs_human:
            st.write("🧑‍💼 *Esse atendimento será encaminhado para um atendente humano.*")

    # salva mensagem do bot no histórico
    st.session_state["messages"].append(
        {"role": "assistant", "content": reply, "needs_human": needs_human}
    )
