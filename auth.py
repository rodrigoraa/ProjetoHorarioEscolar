import streamlit as st
import jwt
import datetime
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

def login_system():
    """Gerencia a tela de login e sessão do usuário com autenticação JWT."""
    SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    if not SECRET_KEY:
        st.error("Erro: Chave secreta JWT não configurada. Verifique o arquivo .env.")
        return False

    if st.session_state.get("logged_in", False):
        with st.sidebar:
            st.write(f"👤 Logado como: **{st.session_state['username']}**")
            if st.button("🚪 Sair / Logout"):
                st.session_state["logged_in"] = False
                st.session_state["username"] = ""
                st.session_state["token"] = ""
                st.rerun()
        return True

    st.markdown("## 🔒 Acesso Restrito ao Gerador")
    st.info("Faça login para acessar o sistema.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Entrar")
        username_input = st.text_input("👤 Usuário")
        password_input = st.text_input("🔑 Senha", type="password")

        if st.button("Entrar"):
            try:
                users_db = st.secrets["users"]
            except (FileNotFoundError, KeyError, Exception):
                users_db = {"admin": "admin"} 

            if username_input in users_db:
                stored_pass = users_db[username_input]
                if stored_pass == password_input:
                    # Gerar token JWT
                    payload = {
                        "username": username_input,
                        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # Token válido por 1 hora
                    }
                    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username_input
                    st.session_state["token"] = token

                    st.success("Login realizado!")
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
            else:
                st.error("Usuário não encontrado.")

    with col2:
        st.subheader("Suporte")
        meu_zap = "+5567999455111"
        link_zap = f"https://wa.me/{meu_zap}?text=Solicito%20acesso%20ao%20Gerador"
        st.markdown(f"[📲 Solicitar Acesso (WhatsApp)]({link_zap})")

    return False

def verify_token():
    """Verifica a validade do token JWT armazenado na sessão."""
    SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    if not SECRET_KEY:
        st.error("Erro: Chave secreta JWT não configurada. Verifique o arquivo .env.")
        return False

    token = st.session_state.get("token", None)

    if not token:
        return False

    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        st.session_state["username"] = decoded_token["username"]
        return True
    except ExpiredSignatureError:
        st.error("Sessão expirada. Faça login novamente.")
    except InvalidTokenError:
        st.error("Token inválido. Faça login novamente.")

    return False