import streamlit as st
import pandas as pd
import io
import time
import auth
from utils import (
    aplicar_estilo_visual, 
    carregar_dados, 
    verificar_capacidade, 
    exibir_horarios,       
    gerar_pdf_bytes, 
    gerar_modelo_exemplo,
    exibir_instrucoes_simples
)

from solver import resolver_horario

st.set_page_config(page_title="Gerador de Horário Escolar", layout="wide")
aplicar_estilo_visual()

def _logout_callback():
    st.session_state['logged_in'] = False
    st.session_state['username'] = ''
    st.session_state['token'] = ''
    st.rerun()

def exibir_contagem_professores(resultado_vars, dias_semana):
    """
    Conta e exibe quantas aulas cada professor tem em cada dia.
    """
    contagem = {}

    for chave in resultado_vars:
        dia_idx = chave[1] 
        prof_nome = chave[3] 
        
        if prof_nome not in contagem:
            contagem[prof_nome] = [0] * len(dias_semana)
        
        contagem[prof_nome][dia_idx] += 1

    df = pd.DataFrame.from_dict(contagem, orient='index', columns=dias_semana)
    df['Total Semanal'] = df.sum(axis=1)
    df = df.sort_index()

    st.subheader("📊 Carga Horária dos Professores")
    st.dataframe(df, use_container_width=True)

if auth.login_system():
    
    st.title("🧩 Gerador de Horário")
    st.markdown("---")

    with st.sidebar:
        if st.session_state.get('logged_in', False):
            st.button("🚪 Sair / Logout", key='logout_main', on_click=_logout_callback)

        st.header("📂 Arquivo de Dados")
        arquivo = st.file_uploader("Faça upload da planilha (.xlsx)", type=['xlsx'])
        
        st.markdown("---")
        with st.expander("📝 Baixar Modelo"):
            st.write("Use este modelo para preencher seus dados.")
            st.download_button(
                "Baixar Excel Exemplo", 
                data=gerar_modelo_exemplo(), 
                file_name="modelo_horario.xlsx"
            )

        exibir_instrucoes_simples()

    if arquivo:
        carregados = carregar_dados(arquivo)

        if not carregados:
            st.error("Erro ao carregar dados. Verifique o arquivo.")
            carregados = (None, None, None, None)

        if isinstance(carregados, (list, tuple)) and len(carregados) == 5:
            turmas, grade, dias, bloqueios, loader_config = carregados
        elif isinstance(carregados, (list, tuple)) and len(carregados) == 4:
            turmas, grade, dias, bloqueios = carregados
            loader_config = None
        else:
            st.error("Formato inesperado retornado por carregar_dados().")
            turmas, grade, dias, bloqueios, loader_config = None, None, None, None, None

        config_itinerario_dados = loader_config if loader_config else {'ativo': False}
        lista_agrupamento = []

        if turmas:
            capacidade_ok = verificar_capacidade(grade, bloqueios)
            
            if capacidade_ok:
                st.write("---")
                st.subheader("⚙️ Configurações da Geração")
                
                with st.container():
                    with st.expander("🎓 Novo Ensino Médio / Itinerários", expanded=False):
                        possui_itin = st.checkbox("Esta grade possui Itinerários Formativos?", value=False)
                        
                        if possui_itin:
                            st.info("O sistema irá alinhar os itinerários de todas as turmas (1º, 2º, 3º ano) no horário escolhido.")
                            
                            col_it1, col_it2, col_it3 = st.columns(3)
                            
                            with col_it1:
                                aula_opcoes = ["1ª Aula", "2ª Aula", "3ª Aula", "4ª Aula", "5ª Aula", "6ª Aula"]
                                aula_escolhida_str = st.selectbox("Qual horário será fixo?", aula_opcoes, index=3) # Padrão 4ª aula
                                aula_idx = int(aula_escolhida_str[0]) - 1 
                            
                            with col_it2:
                                dias_opcoes = ["Seg", "Ter", "Qua", "Qui", "Sex"]
                                dias_escolhidos = st.multiselect("Em quais dias ocorrem?", dias_opcoes, default=["Seg", "Ter"])
                                
                                mapa_dias = {"Seg":0, "Ter":1, "Qua":2, "Qui":3, "Sex":4}
                                dias_idx_lista = [mapa_dias[d] for d in dias_escolhidos]
                                
                            with col_it3:
                                todas_materias = sorted(list(set(i['materia'] for i in grade)))
                                
                                st.markdown("**Quais matérias são itinerários?**")
                                st.caption("Selecione TODAS as matérias de itinerário.")
                                
                                materias_selecionadas = st.multiselect(
                                    "Selecione as matérias:", 
                                    todas_materias
                                )
                            
                            if materias_selecionadas and dias_idx_lista:
                                config_itinerario_dados = {
                                    'ativo': True,
                                    'aula_idx': aula_idx,
                                    'dias_idx': dias_idx_lista,
                                    'materias': materias_selecionadas
                                }
                            elif possui_itin:
                                st.warning("⚠️ Por favor, selecione os dias e as matérias para ativar a lógica.")

                    with st.expander("🔗 Agrupamento de Matérias (Mesmo Dia)", expanded=True):
                        st.write("Selecione matérias que **obrigatoriamente** devem acontecer no mesmo dia.")
                        st.caption("Exemplo: Física e Química sempre juntas, ou Redação e Gramática.")
                        
                        todas_as_materias_geral = sorted(list(set(i['materia'] for i in grade)))
                        
                        lista_agrupamento = st.multiselect(
                            "Selecione as matérias para agrupar:",
                            options=todas_as_materias_geral,
                            help="Se você selecionar Física e Química, o sistema tentará alocá-las sempre no mesmo dia da semana."
                        )
                        
                        if len(lista_agrupamento) == 1:
                            st.warning("⚠️ Selecione pelo menos duas matérias para criar um vínculo.")
                        elif len(lista_agrupamento) > 1:
                            st.info(f"🔒 O sistema tentará manter {', '.join(lista_agrupamento)} juntas nos mesmos dias.")

                st.write("---")
                col1, col2 = st.columns(2)
                with col1:
                    permite_geminada = st.toggle("Permitir duas aulas seguidas", value=True)
                
                if st.button("🚀 Gerar Horário", type="primary"):
                    with st.spinner("Otimizando horários... (Isso pode levar alguns segundos)"):
                        
                        status, vars_res, custo, audit = resolver_horario(
                            turmas_totais=turmas, 
                            grade_aulas=grade, 
                            dias_semana=dias, 
                            bloqueios_globais=bloqueios, 
                            config_itinerarios=config_itinerario_dados,
                            materias_para_agrupar=lista_agrupamento,
                            mapa_aulas_vagas={}, 
                            permite_geminada=permite_geminada
                        )
                        
                        if status == "OK":
                            st.session_state['resultado'] = {
                                'vars': vars_res, 
                                'custo': custo, 
                                'grade': grade, 
                                'turmas': turmas
                            }
                            st.toast("Horário gerado com sucesso!", icon="✅")
                            st.rerun()
                        else:
                            st.error(f"Não foi possível resolver. Status: {status}")
                            if lista_agrupamento:
                                st.warning("⚠️ O erro pode ter sido causado pelo Agrupamento de Matérias. Verifique se as matérias escolhidas possuem cargas horárias compatíveis.")
                            if possui_itin:
                                st.warning("⚠️ Dica: Verifique se a quantidade de aulas dos Itinerários bate com os dias selecionados.")

    if 'resultado' in st.session_state:
        res = st.session_state['resultado']
        dias_list = ['Seg','Ter','Qua','Qui','Sex']
        
        st.markdown("---")
        st.subheader("🗓️ Grade de Horários")
        
        exibir_horarios(res['turmas'], dias_list, res['vars'], res['grade'])
        
        st.markdown("---")
        
        exibir_contagem_professores(res['vars'], dias_list)

        st.markdown("---")
        st.subheader("📥 Downloads")
        
        pdf_bytes = gerar_pdf_bytes(res['turmas'], res['grade'], dias_list, res['vars'])
        
        col_dl_1, col_dl_2 = st.columns(2)
        with col_dl_1:
            st.download_button(
                label="📄 Baixar Grade em PDF",
                data=pdf_bytes,
                file_name="horario_escolar.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )