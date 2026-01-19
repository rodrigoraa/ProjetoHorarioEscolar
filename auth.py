import streamlit as st
import jwt
import datetime
import os
from dotenv import load_dotenv
from datetime import timezone

load_dotenv()

SECRET_KEY = st.secrets.get("JWT_SECRET_KEY")

def verify_token():
    """Verifica silenciosamente se já existe um token válido na sessão."""
    if not SECRET_KEY: return False
    
    token = st.session_state.get("token")
    if not token: return False

    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        st.session_state["logged_in"] = True
        st.session_state["username"] = decoded["username"]
        return True
    except:
        st.session_state["logged_in"] = False
        return False

def login_system():
    """Gerencia a tela de login."""
    
    if verify_token():
        pass 
    
    if st.session_state.get("logged_in", False):
        with st.sidebar:
            st.write(f"👤 Logado como: **{st.session_state['username']}**")
            if st.button("🚪 Sair / Logout"):
                st.session_state["logged_in"] = False
                st.session_state["username"] = ""
                st.session_state["token"] = ""
                st.rerun()
        return True

    st.markdown("## 🔒 Acesso Restrito")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        username_input = st.text_input("👤 Usuário")
        password_input = st.text_input("🔑 Senha", type="password")

        if st.button("Entrar"):
            if "users" in st.secrets:
                users_db = st.secrets["users"]
            else:
                st.error("Erro de Configuração: Banco de usuários não encontrado no secrets.")
                st.stop()
            
            if username_input in users_db and users_db[username_input] == password_input:
                payload = {
                    "username": username_input,
                    "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
                }
                token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
                
                st.session_state["token"] = token
                st.session_state["logged_in"] = True
                st.session_state["username"] = username_input
                st.success("Logado com sucesso!")
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")

    with col2:
        st.info("Entre em contato para solicitar acesso.")

    return False