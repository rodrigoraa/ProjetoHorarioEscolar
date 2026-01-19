import streamlit as st
import jwt
import datetime
import os
from dotenv import load_dotenv

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
    """Gerencia a tela de login com layout centralizado."""
    
    if verify_token():
        pass 
    
    if st.session_state.get("logged_in", False):
        with st.sidebar:
            st.success(f"Logado: **{st.session_state['username']}**")
            if st.button("🚪 Sair / Logout", use_container_width=True):
                st.session_state["logged_in"] = False
                st.session_state["username"] = ""
                st.session_state["token"] = ""
                st.rerun()
        return True
    
    st.write("")
    st.write("")
    st.write("")
    
    col_esq, col_centro, col_dir = st.columns([1, 1.5, 1])

    with col_centro:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center;'>🔐 Acesso Restrito</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Insira suas credenciais para continuar</p>", unsafe_allow_html=True)
            
            st.write("")

            username_input = st.text_input("Usuário", placeholder="Digite seu usuário")
            password_input = st.text_input("Senha", type="password", placeholder="Digite sua senha")

            st.write("")
            
            if st.button("Entrar no Sistema", type="primary", use_container_width=True):
                if "users" in st.secrets:
                    users_db = st.secrets["users"]
                else:
                    st.error("Erro de Configuração: Secrets não encontrado.")
                    st.stop()
                
                if username_input in users_db and users_db[username_input] == password_input:
                    payload = {
                        "username": username_input,
                        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8) # Aumentei para 8h (dia de trabalho)
                    }
                    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
                    
                    st.session_state["token"] = token
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username_input
                    st.toast("Login realizado com sucesso!", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

            st.markdown("---")
            
            meu_zap = "+5567999455111"
            link_zap = f"https://wa.me/{meu_zap}?text=Preciso%20de%20ajuda%20com%20o%20login"
            st.markdown(
                f"<div style='text-align: center;'><a href='{link_zap}' target='_blank' style='text-decoration: none; color: #666;'>Precisa de acesso? Fale com o suporte 📲</a></div>", 
                unsafe_allow_html=True
            )

    return False