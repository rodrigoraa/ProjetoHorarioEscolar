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

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gerador de Horários Escolar", layout="wide")

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
# SISTEMA DE LOGIN
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
            users_db = st.secrets.get("users", {})
            # Fallback para teste se não houver secrets configurado
            if not users_db: 
                 # Crie um usuário padrão caso não tenha configurado o secrets.toml ainda
                 # Remova isso em produção
                 users_db = {"admin": "admin"} 
            
            if username_input in users_db:
                # Verifica se é senha simples ou hash (para compatibilidade)
                senha_correta = False
                stored_pass = users_db[username_input]
                
                if stored_pass == password_input:
                    senha_correta = True
                
                if senha_correta:
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
        status = "✅"
        if saldo < 0:
            status = "❌ CRÍTICO"
            erros_fatais = True
        elif saldo < 2:
            status = "⚠️ Apertado"
            
        logs.append([prof, carga_total, disponivel, saldo, status])

    df_logs = pd.DataFrame(logs, columns=["Professor", "Carga", "Livre", "Saldo", "Status"])
    st.dataframe(df_logs, use_container_width=True)

    if erros_fatais:
        st.error("Existem professores com SALDO NEGATIVO. O cálculo não será iniciado.")
    else:
        st.success("Capacidade dos professores parece OK.")
        
    return not erros_fatais

# ==========================================
# RELATÓRIOS E VISUALIZAÇÃO
# ==========================================
def gerar_pdf_bytes(turmas_totais, grade_aulas, dias_semana, solver, horario):
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
                        chave_var = (item['turma'], d, aula, prof, materia)
                        if chave_var in horario:
                            if solver.Value(horario[chave_var]) == 1:
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

def exibir_detalhes_custo(solver, audit_penalties):
    st.markdown("---")
    st.subheader("💰 Auditoria do Custo")
    
    if not audit_penalties:
        st.info("Nenhuma regra de penalidade foi configurada.")
        return

    detalhes = []
    custo_total = 0
    
    for item in audit_penalties:
        try:
            val = solver.Value(item['var'])
            if val > 0:
                custo_gerado = val * item['peso']
                custo_total += custo_gerado
                detalhes.append({
                    "Tipo": item['tipo'],
                    "Descrição": item['desc'],
                    "Custo": custo_gerado
                })
        except:
            pass 
            
    if custo_total == 0:
        st.success("🏆 Horário Perfeito! Custo Zero (Nenhuma regra de preferência foi violada).")
    else:
        st.warning(f"O horário foi gerado com um custo de **{custo_total}**. Veja os motivos abaixo:")
        df = pd.DataFrame(detalhes)
        if not df.empty:
            st.dataframe(df, use_container_width=True)

def exibir_estatisticas(grade_aulas, dias_semana, solver, horario):
    st.markdown("---")
    st.subheader("📅 Distribuição de Aulas por Professor (Dia a Dia)")
    professores = sorted(list(set(item['prof'] for item in grade_aulas)))
    contagem = {prof: [0]*len(dias_semana) for prof in professores}
    
    for chave, var in horario.items():
        if solver.Value(var) == 1:
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

def exibir_horarios_na_tela(turmas_totais, dias_semana, solver, horario, grade_aulas):
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
                            if chave in horario and solver.Value(horario[chave]) == 1:
                                conteudo = f"{materia} ({prof})"
                                break
                    linha_dict[dia_nome] = conteudo
                dados_grade.append(linha_dict)
            st.dataframe(pd.DataFrame(dados_grade), use_container_width=True)

# ==========================================
# MOTOR DE OTIMIZAÇÃO (SOLVER)
# ==========================================
def resolver_horario(turmas_totais, grade_aulas, dias_semana, bloqueios_globais, materias_para_agrupar=[], mapa_aulas_vagas={}):
    model = cp_model.CpModel()
    horario = {}
    audit_penalties = [] 

    # --- VARS ---
    mapa_turma_horario = defaultdict(list)
    mapa_prof_horario = defaultdict(list)
    mapa_turma_prof_horario = defaultdict(list)

    aulas_por_turma_idx = {t: t_val // 5 for t, t_val in turmas_totais.items()}
    max_aulas_escola = max(aulas_por_turma_idx.values()) if aulas_por_turma_idx else 5

    for item in grade_aulas:
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        aulas_dia = aulas_por_turma_idx.get(turma, 5)
        
        for d in range(len(dias_semana)):
            for aula in range(aulas_dia):
                chave = (turma, d, aula, prof, materia)
                var = model.NewBoolVar(f'H_{turma}_{d}_{aula}_{prof}_{materia}')
                horario[chave] = var
                
                mapa_turma_horario[(turma, d, aula)].append(var)
                mapa_prof_horario[(prof, d, aula)].append(var)
                mapa_turma_prof_horario[(turma, prof, d, aula)].append(var)

    # --- R1 e R2: CHOQUES ---
    for _, vars_list in mapa_turma_horario.items():
        if len(vars_list) > 1: model.Add(sum(vars_list) <= 1)
    for _, vars_list in mapa_prof_horario.items():
        if len(vars_list) > 1: model.Add(sum(vars_list) <= 1)

    # --- R3: QUANTIDADE ---
    for item in grade_aulas:
        vars_materia = []
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        aulas_dia = aulas_por_turma_idx.get(turma, 5)
        for d in range(len(dias_semana)):
            for aula in range(aulas_dia):
                chave = (turma, d, aula, prof, materia)
                if chave in horario: vars_materia.append(horario[chave])
        if vars_materia: model.Add(sum(vars_materia) == item['qtd'])

    # --- R4: INDISPONIBILIDADE ---
    for prof, bloqueios in bloqueios_globais.items():
        for (d, aula) in bloqueios:
            vars_no_slot = mapa_prof_horario.get((prof, d, aula), [])
            for var in vars_no_slot: model.Add(var == 0)

    # --- R5: AULAS VAGAS ---
    total_slots_semana = max_aulas_escola * len(dias_semana)
    for prof, qtd_vagas_exigidas in mapa_aulas_vagas.items():
        qtd_vagas_int = int(qtd_vagas_exigidas)
        if qtd_vagas_int > 0:
            bloqueios_count = 0
            if prof in bloqueios_globais:
                for (d, aula) in bloqueios_globais[prof]:
                    if aula < max_aulas_escola: bloqueios_count += 1
            capacidade_maxima = int(total_slots_semana - bloqueios_count - qtd_vagas_int)
            all_vars_prof = []
            for d in range(len(dias_semana)):
                for aula in range(max_aulas_escola):
                    all_vars_prof.extend(mapa_prof_horario.get((prof, d, aula), []))
            if all_vars_prof: model.Add(sum(all_vars_prof) <= capacidade_maxima)

    # --- PENALIDADES ---
    todas_penalidades = []
    lista_turmas = list(turmas_totais.keys())
    lista_profs = list(set([i['prof'] for i in grade_aulas]))

    # 1. EVITAR DOBRADINHAS (PESO 100.000)
    for turma in lista_turmas:
        aulas_dia = aulas_por_turma_idx.get(turma, 5)
        for prof in lista_profs:
            for d in range(len(dias_semana)):
                for aula in range(aulas_dia - 1):
                    vars_atual = mapa_turma_prof_horario.get((turma, prof, d, aula), [])
                    vars_prox = mapa_turma_prof_horario.get((turma, prof, d, aula+1), [])
                    
                    if vars_atual and vars_prox:
                        tem_aula_atual = model.NewBoolVar(f'tem_{turma}_{prof}_{d}_{aula}')
                        model.Add(sum(vars_atual) == tem_aula_atual)
                        tem_aula_prox = model.NewBoolVar(f'tem_{turma}_{prof}_{d}_{aula+1}')
                        model.Add(sum(vars_prox) == tem_aula_prox)

                        eh_dobra = model.NewBoolVar(f'dobra_{turma}_{prof}_{d}_{aula}')
                        model.Add(tem_aula_atual + tem_aula_prox <= 1 + eh_dobra)
                        
                        # HIPER-PENALIDADE
                        for _ in range(100000): todas_penalidades.append(eh_dobra)
                        audit_penalties.append({'tipo': 'Dobradinha (Evitar)', 'desc': f'{prof} na {turma}', 'var': eh_dobra, 'peso': 100000})

    # 2. EVITAR JANELAS (PESO 500)
    for prof in lista_profs:
        for d in range(len(dias_semana)):
            trabalha_no_slot = {} 
            for aula in range(max_aulas_escola):
                vars_no_slot = mapa_prof_horario.get((prof, d, aula), [])
                if vars_no_slot:
                    ocupado = model.NewBoolVar(f'Ocupado_{prof}_{d}_{aula}')
                    model.Add(sum(vars_no_slot) == ocupado)
                    trabalha_no_slot[aula] = ocupado
                else:
                    trabalha_no_slot[aula] = model.NewConstant(0)

            for aula in range(max_aulas_escola - 2):
                v1 = trabalha_no_slot[aula]
                v2 = trabalha_no_slot[aula+1]
                v3 = trabalha_no_slot[aula+2]
                
                eh_janela = model.NewBoolVar(f'janela_{prof}_{d}_{aula}')
                model.AddBoolAnd([v1, v2.Not(), v3]).OnlyEnforceIf(eh_janela)
                model.AddBoolOr([v1.Not(), v2, v3.Not()]).OnlyEnforceIf(eh_janela.Not())
                
                for _ in range(500): todas_penalidades.append(eh_janela)
                audit_penalties.append({'tipo': 'Janela', 'desc': f'{prof}', 'var': eh_janela, 'peso': 500})

            # Aula Isolada (Peso 100)
            soma_dia = sum(trabalha_no_slot.values())
            eh_um = model.NewBoolVar(f'eh_um_{prof}_{d}')
            model.Add(soma_dia == 1).OnlyEnforceIf(eh_um)
            model.Add(soma_dia != 1).OnlyEnforceIf(eh_um.Not())
            for _ in range(100): todas_penalidades.append(eh_um)
            audit_penalties.append({'tipo': 'Aula Isolada', 'desc': f'{prof}', 'var': eh_um, 'peso': 100})

    if todas_penalidades:
        model.Minimize(sum(todas_penalidades))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180.0
    
    with st.spinner('🤖 O computador está calculando...'):
        status = solver.Solve(model)

    return status, solver, horario, audit_penalties

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

# 3. Upload (CRUCIAL: Isso deve vir antes de qualquer 'if uploaded_file')
uploaded_file = st.file_uploader("Faça upload da sua planilha preenchida (.xlsx)", type=['xlsx'])

if uploaded_file is not None:
    turmas_totais, grade_aulas, dias_semana, bloqueios_globais = carregar_dados(uploaded_file)
    
    if turmas_totais:
        # Checa capacidade para liberar ou travar botão
        dados_ok = verificar_capacidade(grade_aulas, bloqueios_globais)

        if dados_ok:
            st.markdown("### 2. Configurações")
            
            with st.expander("⚙️ Configurações Avançadas", expanded=True):
                st.markdown("#### 🔗 Sincronizar Matérias")
                todas_as_materias = sorted(list(set([g['materia'] for g in grade_aulas])))
                materias_selecionadas = st.multiselect(
                    "Selecione matérias:",
                    options=todas_as_materias,
                    default=[],
                    help="Essas matérias acontecerão juntas na escola toda."
                )
                
                st.markdown("#### ⏳ Aulas Vagas (Hora-Atividade)")
                lista_profs = sorted(list(set([g['prof'] for g in grade_aulas])))
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
                mapa_aulas_vagas_user = dict(zip(df_editado["Professor"], df_editado["Aulas Vagas"]))

            st.write("---")
            if st.button("🚀 Gerar Horário Agora", type="primary", use_container_width=True):
                status, solver, horario, audit_penalties = resolver_horario(
                    turmas_totais, 
                    grade_aulas, 
                    dias_semana, 
                    bloqueios_globais, 
                    materias_para_agrupar=materias_selecionadas,
                    mapa_aulas_vagas=mapa_aulas_vagas_user
                )
                
                if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                    st.success(f"Horário Gerado! (Custo: {solver.ObjectiveValue()})")
                    exibir_detalhes_custo(solver, audit_penalties)
                    exibir_estatisticas(grade_aulas, dias_semana, solver, horario)
                    exibir_horarios_na_tela(turmas_totais, dias_semana, solver, horario, grade_aulas)
                    pdf_bytes = gerar_pdf_bytes(turmas_totais, grade_aulas, dias_semana, solver, horario)
                    st.download_button(
                        label="📥 Baixar PDF Final",
                        data=pdf_bytes,
                        file_name="Horario_Escolar_Final.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("Não foi possível gerar um horário. Tente relaxar as restrições.")
        else:
            st.error("🚫 BOTÃO TRAVADO: Verifique o saldo negativo na tabela acima.")