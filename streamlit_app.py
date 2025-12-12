import streamlit as st
import requests

# URL da sua API FastAPI
API_URL = "http://localhost:8000/chat"

st.set_page_config(page_title="Chat feirão da construção", page_icon="🧱")

st.title("🤖 Chatbot feirão da construção")

# guarda histórico na sessão do streamlit
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# campo para user_id (opcional)
user_id = st.text_input("ID do usuário (opcional)", value="cliente-teste")

# mostra histórico
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# input do usuário
if prompt := st.chat_input("Digite sua mensagem"):
    # adiciona mensagem do usuário no histórico
    st.session_state["messages"].append({"role": "user", "content": prompt})

    # chama sua API FastAPI
    try:
        resp = requests.post(
            API_URL,
            json={"message": prompt, "user_id": user_id or None},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("reply", "Não recebi resposta do servidor.")
    except Exception as e:
        reply = f"Erro ao chamar a API: {e}"

    # adiciona resposta do bot
    st.session_state["messages"].append({"role": "assistant", "content": reply})

    # renderiza a resposta imediatamente
    with st.chat_message("assistant"):
        st.markdown(reply)
