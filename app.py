import streamlit as st
import hmac
import pandas as pd
import io
import unicodedata
from collections import defaultdict
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.colors import HexColor
from ortools.sat.python import cp_model

def aplicar_estilo_visual():
    st.markdown("""
        <style>
        /* Importar fonte moderna */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Roboto', sans-serif;
        }

        /* AQUI ESTÁ A CORREÇÃO:
           Em vez de forçar cores fixas, usamos var(--nome-da-variavel)
           Isso pega a cor que o usuário escolheu nas configurações (Light ou Dark)
        */

        /* Estilo dos Títulos */
        h1, h2, h3 {
            font-weight: 700;
            color: var(--text-color); /* Usa a cor do texto do tema atual */
        }

        /* Cards (Expanders, Forms, Dataframes) */
        div[data-testid="stExpander"], div.stDataFrame, div[data-testid="stForm"] {
            background-color: var(--secondary-background-color); /* Cinza claro no Light, Cinza escuro no Dark */
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); /* Sombra um pouco mais forte para aparecer no escuro */
            border: 1px solid rgba(128, 128, 128, 0.2); /* Borda sutil */
        }

        /* Botão Principal */
        button[kind="primary"] {
            background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
            border: none;
            color: white !important; /* Texto sempre branco no botão azul */
            transition: transform 0.2s;
        }
        button[kind="primary"]:hover {
            transform: scale(1.02);
        }

        /* Botão Secundário (Download) */
        button[kind="secondary"] {
            border-color: var(--text-color);
            color: var(--text-color);
        }

        /* Ajustes na Sidebar */
        section[data-testid="stSidebar"] {
            background-color: var(--secondary-background-color);
        }
        
        /* Remove o padding excessivo do topo */
        .block-container {
            padding-top: 2rem;
        }
        </style>
    """, unsafe_allow_html=True)

def estilizar_tabela_capacidade(df_logs):
    # Função interna para colorir o texto baseado na coluna Status
    def colorir_status(val):
        color = '#2ecc71' if '✅' in val else '#e74c3c' # Verde se OK, Vermelho se Erro
        return f'color: {color}; font-weight: bold'

    # Exibe o dataframe estilizado
    st.dataframe(
        df_logs.style
            .applymap(colorir_status, subset=['Status'])
            # Pinta o fundo da coluna 'Saldo' (Vermelho se negativo, Verde se positivo)
            .background_gradient(subset=['Saldo'], cmap='RdYlGn', vmin=-5, vmax=5)
            # Formata os números para não ter casas decimais estranhas
            .format({'Carga Horária': '{:.0f}', 'Horas Livres': '{:.0f}', 'Saldo': '{:.0f}'}),
        use_container_width=True,
        hide_index=True
    )

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gerador de Horários Escolar", layout="wide")
aplicar_estilo_visual()

# --- INÍCIO DO MENU LATERAL ---
with st.sidebar:
    # Tenta carregar uma logo
    # Se você tiver um arquivo local, use: st.image("sua_logo.png", width=150)
    st.image("logo.png", width=80)
    
    st.title("Sistema Escolar")
    st.markdown("v2.0")
    
    st.markdown("---")
    
    # Menu de Navegação
    # Essa variável 'menu_opcao' vai guardar o que o usuário escolheu
    menu_opcao = st.radio(
        "Navegação",
        ["📁 Upload & Config", "📅 Visualizar Grade", "❓ Ajuda"],
        captions=["Carregue seus dados", "Veja o resultado final", "Como usar"]
    )
    
    st.markdown("---")
    
    # Informações extras no rodapé da barra lateral
    st.info("💡 **Dica:** Se o cálculo demorar, verifique se há muitas janelas configuradas.")
    st.caption("Desenvolvido com Python & OR-Tools")

# --- FIM DO MENU LATERAL ---

# -----------------------------------------------------------
# 2. LOGICA DA PÁGINA PRINCIPAL
# -----------------------------------------------------------

# Agora você usa a variável 'menu_opcao' para decidir o que mostrar
if menu_opcao == "📁 Upload & Config":
    st.title("Configuração da Grade")
    # ... O resto do seu código de Upload começa aqui ...

elif menu_opcao == "📅 Visualizar Grade":
    st.title("Grade de Horários")
    # Aqui você pode mostrar o horário se ele já tiver sido gerado
    if 'resultado_otimizacao' in st.session_state:
        st.write("Aqui vai o resultado...")
    else:
        st.warning("Gere o horário na aba 'Upload' primeiro!")

elif menu_opcao == "❓ Ajuda":
    st.title("Como usar o sistema")
    st.markdown("""
    1. Prepare sua planilha Excel.
    2. Vá na aba **Upload**.
    3. Clique em **Gerar Horário**.
    """)


# ==========================================
#  FUNÇÕES AUXILIARES
# ==========================================
def normalizar_texto(texto):
    if not isinstance(texto, str):
        texto = str(texto)
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII').strip().lower()

def gerar_modelo_exemplo():
    output = io.BytesIO()
    
    dados_turmas = {
        'Turma': ['1º Ano - Fundamental B', '6º Ano - Fundamental', '3º Médio'],
        'Aulas_Semanais': [25, 25, 30] 
    }
    df_t = pd.DataFrame(dados_turmas)
    
    dados_grade = {
        'Professor': [
            'Prof. Márcia', 'Prof. Beto ', 'Prof. Carla ',
            'Prof. Ana ', 'Prof. Carlos', 'Prof. Beatriz ',
            'Prof. João ', 'Prof. Ana '
        ],
        'Materia': [
            'Geografia', 'Ed. Física', 'Artes',
            'Matemática', 'História', 'Português',
            'Física', 'Matemática'
        ],
        'Turmas_Alvo': [
            '1º Ano - Fundamental B', '1º Ano - Fundamental B', '1º Ano - Fundamental B',
            '1º Ano - Fundamental B, 3º Médio', '6º Ano - Fundamental', '6º Ano - Fundamental',
            '3º Médio', '3º Médio'
        ],
        'Aulas_Por_Turma': [
            21, 2, 2, 
            5, 3, 4,
            4, 5
        ],
        'Indisponibilidade': [
            '', '', 'sex',
            '', 'seg:1, seg:2', '',
            'ter:5', ''
        ]
    }
    df_g = pd.DataFrame(dados_grade)
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_t.to_excel(writer, sheet_name='Turmas', index=False)
        df_g.to_excel(writer, sheet_name='Grade_Curricular', index=False)
        workbook = writer.book
        worksheet = writer.sheets['Grade_Curricular']
        worksheet.set_column('A:A', 25) 
        worksheet.set_column('C:C', 20) 
        
    return output.getvalue()

# ==========================================
# SISTEMA DE LOGIN (Versão Robusta)
# ==========================================
def login_system():
    if st.session_state.get("logged_in", False):
        with st.sidebar:
            st.write(f"👤 Logado como: **{st.session_state['username']}**")
            if st.button("🚪 Sair / Logout"):
                st.session_state["logged_in"] = False
                st.rerun()
        return True

    st.markdown("## 🔒 Acesso Restrito ao Gerador de Horários")
    st.info("Este sistema é exclusivo. Faça login ou solicite acesso ao administrador.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Entrar no Sistema")
        username_input = st.text_input("👤 Usuário")
        password_input = st.text_input("🔑 Senha", type="password")
        
        if st.button("Entrar"):
            try:
                users_db = st.secrets["users"]
            except (FileNotFoundError, KeyError, Exception):
                users_db = {"admin": "admin"} # Fallback local
            
            if username_input in users_db:
                stored_pass = users_db[username_input]
                if stored_pass == password_input:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username_input
                    st.success("Login realizado com sucesso!")
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
            else:
                st.error("Usuário não encontrado.")

    with col2:
        st.subheader("Não tem acesso?")
        meu_zap = "+5567999455111"
        link_zap = f"https://wa.me/{meu_zap}?text=Solicito%20acesso%20ao%20Gerador"
        st.link_button("📲 Solicitar Acesso via WhatsApp", link_zap)

    return False

# ==========================================
# LÓGICA DE DADOS
# ==========================================
@st.cache_data(ttl=3600, show_spinner="Lendo arquivo e sanitizando dados...")
def carregar_dados(arquivo_upload):
    try:
        df_turmas = pd.read_excel(arquivo_upload, sheet_name='Turmas')
        df_grade = pd.read_excel(arquivo_upload, sheet_name='Grade_Curricular')
        
        cols_obrigatorias_grade = {'Professor', 'Materia', 'Turmas_Alvo', 'Aulas_Por_Turma'}
        if not cols_obrigatorias_grade.issubset(df_grade.columns):
            st.error(f"Erro: A planilha Grade_Curricular deve conter as colunas: {cols_obrigatorias_grade}")
            return None, None, None, {}

    except Exception as e:
        st.error(f"Erro ao ler Excel: {e}")
        return None, None, None, {}

    turmas_totais = {}
    for _, row in df_turmas.iterrows():
        t = str(row['Turma']).strip()
        turmas_totais[t] = int(row['Aulas_Semanais'])

    grade_aulas = []
    dias_semana = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex']
    bloqueios_globais = {} 
    mapa_dias = {
        'seg': 'Seg', 'ter': 'Ter', 'qua': 'Qua', 'qui': 'Qui', 'sex': 'Sex',
        'mon': 'Seg', 'tue': 'Ter', 'wed': 'Qua', 'thu': 'Qui', 'fri': 'Sex'
    }

    agrupamento_temp = {}

    for _, row in df_grade.iterrows():
        prof_raw = str(row['Professor'])
        prof = prof_raw.lower().replace('prof.', '').replace('profª', '').replace('profa', '').strip().title()
        materia = str(row['Materia']).strip()
        
        try: aulas = int(row['Aulas_Por_Turma'])
        except: aulas = 0
            
        turmas_alvo = str(row['Turmas_Alvo']).split(',')
            
        if prof not in bloqueios_globais:
            bloqueios_globais[prof] = set()

        indisp = str(row['Indisponibilidade'])
        if pd.notna(row['Indisponibilidade']) and str(row['Indisponibilidade']).strip() != '':
            indisp_limpa = indisp.replace(';', ',').lower().replace(' ', '')
            partes = indisp_limpa.split(',')
            for p in partes:
                if ':' in p: 
                    try:
                        dia_sujo, aula_str = p.split(':')
                        chave_dia = dia_sujo[:3] 
                        if chave_dia in mapa_dias:
                            dia_oficial = mapa_dias[chave_dia]
                            d_idx = dias_semana.index(dia_oficial)
                            a_idx = int(aula_str) - 1
                            bloqueios_globais[prof].add((d_idx, a_idx))
                    except: pass
                else: 
                    chave_dia = p[:3]
                    if chave_dia in mapa_dias:
                        dia_oficial = mapa_dias[chave_dia]
                        d_idx = dias_semana.index(dia_oficial)
                        for i in range(10): bloqueios_globais[prof].add((d_idx, i))

        for t_raw in turmas_alvo:
            turma = t_raw.strip()
            if turma in turmas_totais:
                chave_unica = (prof, materia, turma)
                if chave_unica not in agrupamento_temp:
                    agrupamento_temp[chave_unica] = 0
                agrupamento_temp[chave_unica] += aulas

    for (prof, materia, turma), qtd in agrupamento_temp.items():
        grade_aulas.append({'prof': prof, 'materia': materia, 'turma': turma, 'qtd': qtd})
    
    return turmas_totais, grade_aulas, dias_semana, bloqueios_globais

# --- Função Auxiliar de Estilo (Nova) ---
def estilizar_tabela_capacidade(df_logs):
    # Define cores para o Status
    def colorir_status(val):
        if '✅' in val:
            color = '#2ecc71' # Verde
        elif '⚠️' in val:
            color = '#f39c12' # Laranja
        else:
            color = '#e74c3c' # Vermelho
        return f'color: {color}; font-weight: bold'

    # Aplica o estilo
    st.dataframe(
        df_logs.style
            .applymap(colorir_status, subset=['Status'])
            # Pinta o fundo da coluna Saldo (Vermelho se negativo, Verde se positivo)
            .background_gradient(subset=['Saldo'], cmap='RdYlGn', vmin=-2, vmax=2)
            # Garante que os números não tenham casas decimais (.0f)
            .format({'Carga': '{:.0f}', 'Livre': '{:.0f}', 'Saldo': '{:.0f}'}),
        use_container_width=True,
        hide_index=True
    )

# --- Sua Função Atualizada ---
def verificar_capacidade(grade_aulas, bloqueios_globais):
    st.subheader("📊 Análise de Capacidade")
    
    carga_prof = {}
    for item in grade_aulas:
        p = item['prof']
        if p not in carga_prof: carga_prof[p] = 0
        carga_prof[p] += item['qtd']

    erros_fatais = False
    max_slots_semana = 30 
    logs = []
    
    for prof, carga_total in carga_prof.items():
        bloqueios = 0
        if prof in bloqueios_globais:
            bloqueios_uteis = 0
            for (d, a) in bloqueios_globais[prof]:
                if a < 6: bloqueios_uteis += 1
            bloqueios = bloqueios_uteis

        disponivel = max_slots_semana - bloqueios
        saldo = disponivel - carga_total
        status = "✅ OK"
        
        if saldo < 0:
            status = "❌ CRÍTICO"
            erros_fatais = True
        elif saldo < 2:
            status = "⚠️ Apertado"
            
        logs.append([prof, carga_total, disponivel, saldo, status])

    df_logs = pd.DataFrame(logs, columns=["Professor", "Carga", "Livre", "Saldo", "Status"])
    
    # -------------------------------------------------------
    # AQUI ESTÁ A MUDANÇA VISUAL
    # Substituímos o st.dataframe simples pela função estilizada
    # -------------------------------------------------------
    estilizar_tabela_capacidade(df_logs)

    if erros_fatais:
        st.error("Existem professores com SALDO NEGATIVO. O cálculo não será iniciado.")
    else:
        st.success("Capacidade dos professores parece OK.")
        
    return not erros_fatais 

# ==========================================
# RELATÓRIOS E VISUALIZAÇÃO
# ==========================================
def gerar_pdf_bytes(turmas_totais, grade_aulas, dias_semana, vars_resolvidas):
    # vars_resolvidas é um dict com os valores True/False já extraídos
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []
    styles = getSampleStyleSheet()
    
    estilo_tabela = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2c3e50')), 
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#d3d3d3')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HexColor('#f0f0f0')]),
    ])

    lista_turmas = sorted(turmas_totais.keys())
    for turma in lista_turmas:
        elements.append(Paragraph(f"Horário: {turma}", styles['Title']))
        elements.append(Spacer(1, 10))
        dados = [['Horário'] + dias_semana]
        aulas_por_dia = turmas_totais[turma] // 5
        linha_intervalo_idx = -1 

        for aula in range(aulas_por_dia):
            if aula == 3:
                dados.append(["INTERVALO", "", "", "", "", ""]) 
                linha_intervalo_idx = len(dados) - 1

            linha = [f"{aula + 1}ª Aula"]
            for d in range(len(dias_semana)):
                conteudo = "---"
                for item in grade_aulas:
                    if item['turma'] == turma:
                        prof = item['prof']
                        materia = item['materia']
                        # Verifica se está no dicionário de resolvidos
                        chave_var = (item['turma'], d, aula, prof, materia)
                        if chave_var in vars_resolvidas and vars_resolvidas[chave_var] == 1:
                            conteudo = f"{materia}\n({prof})"
                            break 
                linha.append(conteudo)
            dados.append(linha)
            
        t = Table(dados, colWidths=[60] + [140]*5)
        t.setStyle(estilo_tabela)
        if linha_intervalo_idx != -1:
            estilo_intervalo = TableStyle([
                ('BACKGROUND', (0, linha_intervalo_idx), (-1, linha_intervalo_idx), HexColor('#95a5a6')), 
                ('TEXTCOLOR', (0, linha_intervalo_idx), (-1, linha_intervalo_idx), colors.white),
                ('SPAN', (0, linha_intervalo_idx), (-1, linha_intervalo_idx)), 
                ('FONTNAME', (0, linha_intervalo_idx), (-1, linha_intervalo_idx), 'Helvetica-Bold'),
                ('ALIGN', (0, linha_intervalo_idx), (-1, linha_intervalo_idx), 'CENTER'),
            ])
            t.setStyle(estilo_intervalo)
        elements.append(t)
        elements.append(Spacer(1, 25))
        elements.append(PageBreak())

    doc.build(elements)
    buffer.seek(0)
    return buffer

def exibir_detalhes_custo(detalhes_penalidades):
    st.markdown("---")
    st.subheader("💰 Auditoria do Custo")
    
    if not detalhes_penalidades:
        st.success("🏆 Horário Perfeito! Custo Zero.")
        return

    custo_total = sum(d['Custo'] for d in detalhes_penalidades)
    st.warning(f"O horário foi gerado com um custo de **{custo_total}**. Veja os motivos:")
    df = pd.DataFrame(detalhes_penalidades)
    st.dataframe(df, use_container_width=True)

def exibir_estatisticas(grade_aulas, dias_semana, vars_resolvidas):
    st.markdown("---")
    st.subheader("📅 Distribuição de Aulas por Professor (Dia a Dia)")
    professores = sorted(list(set(item['prof'] for item in grade_aulas)))
    contagem = {prof: [0]*len(dias_semana) for prof in professores}
    
    for chave, valor in vars_resolvidas.items():
        if valor == 1:
            prof = chave[3]
            dia_idx = chave[1]
            contagem[prof][dia_idx] += 1

    dados_tabela = []
    for prof in professores:
        linha = {'Professor': prof}
        total = 0
        for i, dia in enumerate(dias_semana):
            qtd = contagem[prof][i]
            linha[dia] = qtd
            total += qtd
        linha['TOTAL'] = total
        dados_tabela.append(linha)
        
    df_stats = pd.DataFrame(dados_tabela)
    st.dataframe(df_stats.style.background_gradient(subset=dias_semana, cmap="Blues"), use_container_width=True)

def exibir_horarios_na_tela(turmas_totais, dias_semana, vars_resolvidas, grade_aulas):
    st.markdown("---")
    st.subheader("🏫 Visualização dos Horários das Turmas")
    lista_turmas = sorted(turmas_totais.keys())
    abas = st.tabs(lista_turmas)
    for aba, turma in zip(abas, lista_turmas):
        with aba:
            aulas_por_dia = turmas_totais[turma] // 5
            dados_grade = []
            for aula in range(aulas_por_dia):
                if aula == 3:
                      dados_grade.append({"Horário": "INTERVALO", "Seg": "---", "Ter": "---", "Qua": "---", "Qui": "---", "Sex": "---"})
                linha_dict = {"Horário": f"{aula + 1}ª Aula"}
                for d_idx, dia_nome in enumerate(dias_semana):
                    conteudo = "---"
                    for item in grade_aulas:
                        if item['turma'] == turma:
                            prof = item['prof']
                            materia = item['materia']
                            chave = (turma, d_idx, aula, prof, materia)
                            if chave in vars_resolvidas and vars_resolvidas[chave] == 1:
                                conteudo = f"{materia} ({prof})"
                                break
                    linha_dict[dia_nome] = conteudo
                dados_grade.append(linha_dict)
            st.dataframe(pd.DataFrame(dados_grade), use_container_width=True)

# ==========================================
# MOTOR DE OTIMIZAÇÃO (SOLVER)
# ==========================================
def resolver_horario(
    turmas_totais,
    grade_aulas,
    dias_semana,
    bloqueios_globais,
    materias_para_agrupar=[],
    mapa_aulas_vagas={}
):

    model = cp_model.CpModel()
    horario_vars = {}

    termos_custo = []
    detalhes_audit = []

    # Mapas auxiliares para facilitar a busca de variáveis
    mapa_turma_horario = defaultdict(list)
    mapa_prof_horario = defaultdict(list)
    mapa_turma_prof_horario = defaultdict(list)
    
    # Mapa reverso para saber quais matérias/profs existem em cada turma
    # Estrutura: mapa_conteudo_turma[turma] = set((prof, materia))
    mapa_conteudo_turma = defaultdict(set)

    aulas_por_turma_idx = {t: t_val // 5 for t, t_val in turmas_totais.items()}
    max_aulas_escola = max(aulas_por_turma_idx.values()) if aulas_por_turma_idx else 5

    # =========================
    # 1. CRIAÇÃO DAS VARIÁVEIS
    # =========================
    for item in grade_aulas:
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        aulas_dia = aulas_por_turma_idx[turma]
        
        mapa_conteudo_turma[turma].add((prof, materia))

        for d in range(len(dias_semana)):
            for a in range(aulas_dia):
                key = (turma, d, a, prof, materia)
                var = model.NewBoolVar(f"H_{turma}_{prof}_{materia}_{d}_{a}")
                horario_vars[key] = var

                mapa_turma_horario[(turma, d, a)].append(var)
                mapa_prof_horario[(prof, d, a)].append(var)
                mapa_turma_prof_horario[(turma, prof, d)].append(var)

    # =========================
    # 2. HARD CONSTRAINTS (Regras Rígidas)
    # =========================
    
    # A) Colisão de Turma: Uma turma só tem 1 aula por horário
    for vars_list in mapa_turma_horario.values():
        model.Add(sum(vars_list) <= 1)

    # B) Colisão de Professor: Professor só em 1 lugar ao mesmo tempo
    for vars_list in mapa_prof_horario.values():
        model.Add(sum(vars_list) <= 1)

    # C) Quantidade de Aulas: Respeitar a grade curricular
    for item in grade_aulas:
        vars_materia = []
        turma, prof, materia = item['turma'], item['prof'], item['materia']
        aulas_dia = aulas_por_turma_idx[turma]
        for d in range(len(dias_semana)):
            for a in range(aulas_dia):
                vars_materia.append(horario_vars[(turma, d, a, prof, materia)])
        
        # Se a grade pede X aulas, deve ter exatamente X aulas
        model.Add(sum(vars_materia) == item['qtd'])

    # D) Indisponibilidade Declarada
    for prof, bloqueios in bloqueios_globais.items():
        for d, a in bloqueios:
            if (prof, d, a) in mapa_prof_horario:
                for var in mapa_prof_horario[(prof, d, a)]:
                    model.Add(var == 0)

    # =========================
    # 3. CONSTRAINTS AVANÇADAS (O que faltava)
    # =========================

    # --- E) JANELAS (Aulas Vagas) ---
    # Limita o tempo ocioso do professor entre a primeira e a última aula do dia
    
    PESO_JANELA_EXTRA = 50  # Penalidade se estourar um pouco (soft) ou Hard se preferir

    # Agrupamos todas as vars de um professor por dia e aula
    profs_unicos = set(item['prof'] for item in grade_aulas)
    
    for prof in profs_unicos:
        limite_janelas = mapa_aulas_vagas.get(prof, 2) # Padrão 2 se não definido
        
        for d in range(len(dias_semana)):
            # Variáveis que indicam se o prof trabalha na aula 'a' do dia 'd'
            trabalha_no_horario = [] 
            
            # Como as aulas variam por turma, pegamos o maximo global (ex: 5 ou 6 aulas)
            for a in range(max_aulas_escola):
                # Soma todas as turmas que esse prof pode estar nesse dia/horario
                vars_slot = mapa_prof_horario.get((prof, d, a), [])
                
                if not vars_slot:
                    # Se não tem aula nenhuma possível nesse slot, é 0 constante
                    trabalha_no_horario.append(0)
                else:
                    # Cria var booleana: 1 se der aula, 0 se não
                    var_trab = model.NewBoolVar(f"trab_{prof}_{d}_{a}")
                    model.Add(sum(vars_slot) == var_trab) # Soma será 0 ou 1
                    trabalha_no_horario.append(var_trab)
            
            # Se o professor não trabalha no dia, janelas = 0. Precisamos tratar isso.
            tem_aula_dia = model.NewBoolVar(f"tem_aula_{prof}_{d}")
            model.Add(sum(trabalha_no_horario) > 0).OnlyEnforceIf(tem_aula_dia)
            model.Add(sum(trabalha_no_horario) == 0).OnlyEnforceIf(tem_aula_dia.Not())

            # Definir Início (primeira aula) e Fim (última aula)
            inicio = model.NewIntVar(0, max_aulas_escola, f"inicio_{prof}_{d}")
            fim = model.NewIntVar(0, max_aulas_escola, f"fim_{prof}_{d}")
            
            # Restrições para encontrar inicio e fim
            for idx, var_bin in enumerate(trabalha_no_horario):
                # Se trabalha no idx, o inicio deve ser <= idx
                if isinstance(var_bin, int) and var_bin == 0: continue
                
                model.Add(inicio <= idx).OnlyEnforceIf(var_bin)
                model.Add(fim >= idx).OnlyEnforceIf(var_bin)
            
            # Span (Duração da estadia na escola) = Fim - Inicio + 1
            span = model.NewIntVar(0, max_aulas_escola, f"span_{prof}_{d}")
            model.Add(span == fim - inicio + 1).OnlyEnforceIf(tem_aula_dia)
            model.Add(span == 0).OnlyEnforceIf(tem_aula_dia.Not())
            
            # Janelas = Span - Aulas Dadas
            # Ex: Aula na 1 e na 3. Span = 3-1+1 = 3. Aulas = 2. Janelas = 1.
            qtd_janelas = model.NewIntVar(0, max_aulas_escola, f"janelas_{prof}_{d}")
            
            # Precisamos somar as variaveis da lista trabalha_no_horario (tratando int 0)
            soma_aulas = sum(v for v in trabalha_no_horario if not isinstance(v, int) or v != 0)
            
            model.Add(qtd_janelas == span - soma_aulas).OnlyEnforceIf(tem_aula_dia)
            model.Add(qtd_janelas == 0).OnlyEnforceIf(tem_aula_dia.Not())

            # Hard Constraint Relaxada: Se passar do limite, penaliza MUITO forte
            # Isso evita que o Solver retorne "Impossible" se for matematicamente impossível
            # mas tenta ao máximo respeitar.
            excesso_janela = model.NewIntVar(0, max_aulas_escola, f"exc_jan_{prof}_{d}")
            model.Add(excesso_janela >= qtd_janelas - limite_janelas)
            model.Add(excesso_janela >= 0) # ReLU
            
            PESO_JANELA = 500 # Peso alto para funcionar quase como Hard Constraint
            termos_custo.append(excesso_janela * PESO_JANELA)
            
            detalhes_audit.append({
                "tipo": "Janelas em Excesso",
                "desc": f"{prof} excedeu limite de janelas ({dias_semana[d]})",
                "var": excesso_janela,
                "peso": PESO_JANELA
            })

    # --- F) AGRUPAMENTO DE MATÉRIAS (Mesmo Dia) ---
    # Se Matéria A e B estão no grupo, tentamos forçar que ocorram no mesmo dia na turma
    
    PESO_AGRUPAMENTO = 150

    if materias_para_agrupar:
        for grupo in materias_para_agrupar:
            # O grupo é uma lista de nomes, ex: ['Artes', 'Ed. Física']
            if len(grupo) < 2: continue
            
            materia_lider = grupo[0]
            materias_seguidoras = grupo[1:]
            
            for turma in turmas_totais:
                conteudos_turma = mapa_conteudo_turma[turma]
                
                # Verifica se essa turma tem essas matérias
                tem_lider = any(m == materia_lider for p, m in conteudos_turma)
                if not tem_lider: continue

                for m_seg in materias_seguidoras:
                    tem_seg = any(m == m_seg for p, m in conteudos_turma)
                    if not tem_seg: continue
                    
                    # Agora sabemos que a turma tem as duas matérias.
                    # Vamos alinhar dia a dia.
                    for d in range(len(dias_semana)):
                        
                        # Bool: Lider ocorre hoje?
                        lider_hoje = model.NewBoolVar(f"lid_{turma}_{materia_lider}_{d}")
                        vars_lider = []
                        # Pegar var da materia lider (pode ser qqr prof, mas geralmente é 1)
                        for (p, m) in conteudos_turma:
                            if m == materia_lider:
                                aulas_dia = aulas_por_turma_idx[turma]
                                for a in range(aulas_dia):
                                    vars_lider.append(horario_vars.get((turma, d, a, p, m), 0))
                        
                        # Se soma > 0, então lider_hoje = 1
                        # Truque CP: sum(vars) > 0 <=> lider_hoje
                        soma_l = sum(vars_lider)
                        if isinstance(soma_l, int) and soma_l == 0:
                             model.Add(lider_hoje == 0)
                        else:
                             model.Add(soma_l > 0).OnlyEnforceIf(lider_hoje)
                             model.Add(soma_l == 0).OnlyEnforceIf(lider_hoje.Not())

                        # Bool: Seguidora ocorre hoje?
                        seg_hoje = model.NewBoolVar(f"seg_{turma}_{m_seg}_{d}")
                        vars_seg = []
                        for (p, m) in conteudos_turma:
                            if m == m_seg:
                                aulas_dia = aulas_por_turma_idx[turma]
                                for a in range(aulas_dia):
                                    vars_seg.append(horario_vars.get((turma, d, a, p, m), 0))
                        
                        soma_s = sum(vars_seg)
                        if isinstance(soma_s, int) and soma_s == 0:
                             model.Add(seg_hoje == 0)
                        else:
                             model.Add(soma_s > 0).OnlyEnforceIf(seg_hoje)
                             model.Add(soma_s == 0).OnlyEnforceIf(seg_hoje.Not())

                        # Penalidade se forem diferentes (uma tem aula, a outra não)
                        # abs(lider - seg)
                        diferenca = model.NewIntVar(0, 1, f"diff_{turma}_{materia_lider}_{m_seg}_{d}")
                        model.Add(diferenca == lider_hoje - seg_hoje).OnlyEnforceIf(lider_hoje) # Se lider=1, diff = 1 - seg
                        model.Add(diferenca == seg_hoje - lider_hoje).OnlyEnforceIf(lider_hoje.Not()) # Se lider=0, diff = seg - 0
                        
                        termos_custo.append(diferenca * PESO_AGRUPAMENTO)
                        detalhes_audit.append({
                            "tipo": "Agrupamento Falhou",
                            "desc": f"{turma}: {materia_lider} e {m_seg} separados em {dias_semana[d]}",
                            "var": diferenca,
                            "peso": PESO_AGRUPAMENTO
                        })


    # =========================
    # 4. SOFT CONSTRAINTS (Qualidade de Vida)
    # =========================

    # G) Evitar Repetição no Mesmo Dia (GEMINADAS PERMITIDAS)
    # Regra Ajustada: Até 2 aulas (dobradinha) é OK. 3 ou mais penaliza.
    
    PESO_REPETICAO_EXCESSIVA = 100

    for turma in turmas_totais:
        # Analisar por professor
        profs_da_turma = set(p for p, m in mapa_conteudo_turma[turma])
        
        for prof in profs_da_turma:
            for d in range(len(dias_semana)):
                vars_dia = mapa_turma_prof_horario.get((turma, prof, d), [])
                if not vars_dia: continue

                total_no_dia = model.NewIntVar(0, max_aulas_escola, f"tot_rep_{turma}_{prof}_{d}")
                model.Add(total_no_dia == sum(vars_dia))

                # Penalidade se > 2 (permitimos geminadas)
                excesso_geminada = model.NewIntVar(0, max_aulas_escola, f"exc_gem_{turma}_{prof}_{d}")
                model.Add(excesso_geminada >= total_no_dia - 2)
                model.Add(excesso_geminada >= 0)

                termos_custo.append(excesso_geminada * PESO_REPETICAO_EXCESSIVA)
                detalhes_audit.append({
                    "tipo": "Muitas aulas seguidas",
                    "desc": f"{prof} na {turma} ({dias_semana[d]}) > 2 aulas",
                    "var": excesso_geminada,
                    "peso": PESO_REPETICAO_EXCESSIVA
                })

    # H) Distribuição Homogênea (Professores não devem ter 5 aulas num dia e 0 no outro se possível)
    PESO_EXCESSO_DIARIO = 200
    LIMITE_SUAVE_DIARIO = 4 

    for prof in profs_unicos:
        for d in range(len(dias_semana)):
            # Reciclando o calculo de 'trabalha_no_horario' feito nas janelas? 
            # Não, precisamos da soma total de aulas, não bools.
            
            vars_dia_prof = []
            for a in range(max_aulas_escola):
                 vars_dia_prof.extend(mapa_prof_horario.get((prof, d, a), []))
            
            if not vars_dia_prof: continue

            total_dia = model.NewIntVar(0, max_aulas_escola, f"total_prof_{prof}_{d}")
            model.Add(total_dia == sum(vars_dia_prof))

            excesso = model.NewIntVar(0, max_aulas_escola, f"overload_{prof}_{d}")
            model.Add(excesso >= total_dia - LIMITE_SUAVE_DIARIO)
            model.Add(excesso >= 0)

            termos_custo.append(excesso * PESO_EXCESSO_DIARIO)
            detalhes_audit.append({
                "tipo": "Concentração Diária",
                "desc": f"{prof} sobrecarregado em {dias_semana[d]}",
                "var": excesso,
                "peso": PESO_EXCESSO_DIARIO
            })

    # =========================
    # 5. OBJETIVO E SOLUÇÃO
    # =========================
    if termos_custo:
        model.Minimize(sum(termos_custo))

    solver = cp_model.CpSolver()
    # De 45 para 300 segundos (5 minutos) ou até 600 (10 minutos)
    solver.parameters.max_time_in_seconds = 45
    # Se estiver rodando no seu PC, 8 é bom. Na nuvem grátis, deixe 4 ou 8 mesmo
    solver.parameters.num_search_workers = 8
    # Linearização ajuda em problemas de agendamento
    solver.parameters.linearization_level = 0 
    # DICA PRO: Habilite o log para ver o progresso no terminal (tela preta)
    solver.parameters.log_search_progress = True
    status = solver.Solve(model)

    resultados = {}
    auditoria = []

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for k, v in horario_vars.items():
            if solver.Value(v) == 1:
                resultados[k] = 1

        for item in detalhes_audit:
            try:
                val = solver.Value(item['var'])
                if val > 0:
                    auditoria.append({
                        "Tipo": item["tipo"],
                        "Descrição": item["desc"],
                        "Custo": val * item["peso"]
                    })
            except: pass

        return "OK", resultados, solver.ObjectiveValue(), auditoria

    return "ERRO", {}, 0, []


# ==========================================
# APP PRINCIPAL (EXECUÇÃO)
# ==========================================

# 1. Verifica Login
if not login_system():
    st.stop()

# 2. Interface Principal
st.title("🧩 Gerador de Horários Escolar")
st.markdown("---")

col1, col2 = st.columns([1, 2])

with col1:
    st.info("Download do Modelo")
    modelo_excel = gerar_modelo_exemplo()
    st.download_button(
        label="📥 Baixar Planilha Modelo",
        data=modelo_excel,
        file_name="Modelo_Horario_Escolar.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# 3. Upload e Controle de Estado
if 'resultado_otimizacao' not in st.session_state:
    st.session_state['resultado_otimizacao'] = None

uploaded_file = st.file_uploader("Faça upload da sua planilha preenchida (.xlsx)", type=['xlsx'])

if uploaded_file is not None:
    turmas_totais, grade_aulas, dias_semana, bloqueios_globais = carregar_dados(uploaded_file)
    
    if turmas_totais:
        dados_ok = verificar_capacidade(grade_aulas, bloqueios_globais)

        st.markdown("### 📊 Resumo da Escola")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        total_aulas = sum(turmas_totais.values())
        qtd_profs = len(set(g['prof'] for g in grade_aulas))
        qtd_turmas = len(turmas_totais)

        # Exibe os cards
        kpi1.metric("Total de Turmas", qtd_turmas, "🏫")
        kpi2.metric("Professores", qtd_profs, "👨‍🏫")
        kpi3.metric("Aulas Semanais", total_aulas, "📚")
        
        # Cria um status visual
        label_status = "Tudo Certo" if dados_ok else "Atenção Necessária"
        cor_status = "normal" if dados_ok else "inverse" # inverse fica vermelho no tema light
        kpi4.metric("Status Capacidade", label_status, delta_color=cor_status)
        
        st.markdown("---")

        if dados_ok:
            st.markdown("### 2. Configurações")
            
            with st.expander("⚙️ Configurações Avançadas", expanded=True):
                
                # =========================
                # AULAS VAGAS (HORA-ATIVIDADE)
                # =========================
                st.markdown("#### ⏳ Aulas Vagas (Hora-Atividade)")
                
                lista_profs = sorted(list(set(g['prof'] for g in grade_aulas)))
                
                df_vagas = pd.DataFrame({
                    "Professor": lista_profs,
                    "Aulas Vagas": [0] * len(lista_profs)
                })
                
                df_editado = st.data_editor(
                    df_vagas, 
                    column_config={
                        "Aulas Vagas": st.column_config.NumberColumn(
                            "Qtd. Aulas Vagas", min_value=0, max_value=15, step=1
                        )
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                mapa_aulas_vagas_user = dict(
                    zip(df_editado["Professor"], df_editado["Aulas Vagas"])
                )

                # =========================
                # MATÉRIAS NO MESMO DIA
                # =========================
                st.markdown("#### 🔗 Matérias que devem ocorrer no MESMO DIA")

                lista_materias = sorted(list(set(g['materia'] for g in grade_aulas)))

                materias_mesmo_dia = st.multiselect(
                    "Selecione matérias que devem acontecer no mesmo dia da semana",
                    options=lista_materias,
                    help="Exemplo: Artes e Ed. Física"
                )

                materias_para_agrupar = []
                if len(materias_mesmo_dia) >= 2:
                    materias_para_agrupar.append(materias_mesmo_dia)

            st.write("---")

            # --- BOTÃO DE AÇÃO ---
            if st.button("🚀 Gerar Horário Agora", type="primary", use_container_width=True):
                with st.spinner('🤖 Construindo modelo matemático e calculando (Isso pode demorar)...'):
                    try:
                        status, vars_resolvidas, custo, detalhes_penal = resolver_horario(
                            turmas_totais,
                            grade_aulas,
                            dias_semana,
                            bloqueios_globais,
                            materias_para_agrupar=materias_para_agrupar,  # 👈 AQUI
                            mapa_aulas_vagas=mapa_aulas_vagas_user
                        )

                        if status == "OK":
                            # Salva na memória do Streamlit
                            st.session_state['resultado_otimizacao'] = {
                                'vars': vars_resolvidas,
                                'custo': custo,
                                'detalhes': detalhes_penal,
                                'grade': grade_aulas,  # snapshot
                                'turmas': turmas_totais
                            }
                            st.rerun()  # Recarrega a página para mostrar resultados
                        else:
                            st.error("Não foi possível gerar um horário viável. Tente relaxar as restrições.")
                    except Exception as e:
                        st.error(f"Erro Crítico no motor de cálculo: {e}")
                        st.write("Verifique se instalou o OR-Tools: `pip install ortools`")

# --- EXIBIÇÃO DE RESULTADOS (FORA DO BOTÃO) ---
if st.session_state['resultado_otimizacao']:
    res = st.session_state['resultado_otimizacao']

    st.success(f"Horário Gerado com Sucesso! (Custo: {res['custo']})")

    # Só exibe se os dados ainda baterem
    if res['turmas'].keys() == turmas_totais.keys():
        exibir_detalhes_custo(res['detalhes'])
        exibir_estatisticas(res['grade'], dias_semana, res['vars'])
        exibir_horarios_na_tela(res['turmas'], dias_semana, res['vars'], res['grade'])

        pdf_bytes = gerar_pdf_bytes(res['turmas'], res['grade'], dias_semana, res['vars'])
        st.download_button(
            label="📥 Baixar PDF Final",
            data=pdf_bytes,
            file_name="Horario_Escolar_Final.pdf",
            mime="application/pdf"
        )
    else:
        st.warning("⚠️ Os dados do arquivo mudaram. Gere o horário novamente.")
