import streamlit as st
import requests

# URL da sua API FastAPI
API_URL = "http://localhost:8000/chat"

st.set_page_config(page_title="Chat feirão da construção", page_icon="🧱")

st.title("🤖 Chatbot feirão da construção")

# session_id retornado pela API (usado quando user_id ficar vazio)
if "session_id" not in st.session_state:
    st.session_state["session_id"] = None

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
        # Se o usuário não informar um user_id, reutilizamos o session_id retornado na primeira resposta
        effective_id = (user_id or "").strip() or st.session_state.get("session_id")
        payload = {"message": prompt, "user_id": effective_id} if effective_id else {"message": prompt}

        resp = requests.post(
            API_URL,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("reply", "Não recebi resposta do servidor.")
        # guarda para as próximas mensagens (quando user_id estiver vazio)
        st.session_state["session_id"] = data.get("session_id") or st.session_state.get("session_id")
    except Exception as e:
        reply = f"Erro ao chamar a API: {e}"

    # adiciona resposta do bot
    st.session_state["messages"].append({"role": "assistant", "content": reply})

    # renderiza a resposta imediatamente
    with st.chat_message("assistant"):
        st.markdown(reply)