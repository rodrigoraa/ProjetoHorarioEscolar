import streamlit as st
import hmac
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.colors import HexColor
from ortools.sat.python import cp_model
import pandas as pd
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gerador de Horários Escolar", layout="wide")

# ==========================================
#  FUNÇÃO: GERAR MODELO DE EXEMPLO
# ==========================================
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
            if "users" in st.secrets and username_input in st.secrets["users"]:
                if hmac.compare_digest(st.secrets["users"][username_input], password_input):
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

if not login_system():
    st.stop()

# ==========================================
# LÓGICA DO SISTEMA
# ==========================================

def carregar_dados(arquivo_upload):
    try:
        df_turmas = pd.read_excel(arquivo_upload, sheet_name='Turmas')
        df_grade = pd.read_excel(arquivo_upload, sheet_name='Grade_Curricular')
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
                grade_aulas.append({'prof': prof, 'materia': materia, 'turma': turma, 'qtd': aulas})
    
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
                linha_intervalo_idx = 4 

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

# --- LÓGICA DO SOLVER ATUALIZADA (AGORA COM AULAS VAGAS) ---
def resolver_horario(turmas_totais, grade_aulas, dias_semana, bloqueios_globais, materias_para_agrupar=[], mapa_aulas_vagas={}):
    model = cp_model.CpModel()
    horario = {}

    # Variáveis
    for item in grade_aulas:
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        aulas_por_dia = turmas_totais[turma] // 5 
        for d in range(len(dias_semana)):
            for aula in range(aulas_por_dia):
                chave = (turma, d, aula, prof, materia)
                horario[chave] = model.NewBoolVar(f'{turma}_{d}_{aula}_{prof}_{materia}')

    # R1: Choque de Turma
    for turma, total_semanal in turmas_totais.items():
        aulas_por_dia = total_semanal // 5
        for d in range(len(dias_semana)):
            for aula in range(aulas_por_dia):
                vars_neste_horario = []
                for item in grade_aulas:
                    if item['turma'] == turma:
                        chave = (turma, d, aula, item['prof'], item['materia'])
                        if chave in horario:
                            vars_neste_horario.append(horario[chave])
                if vars_neste_horario:
                    model.Add(sum(vars_neste_horario) <= 1)

    # R2: Choque de Professor
    lista_professores = set(item['prof'] for item in grade_aulas)
    max_aulas_escola = max([t // 5 for t in turmas_totais.values()])

    for d in range(len(dias_semana)):
        for aula in range(max_aulas_escola):
            for prof in lista_professores:
                vars_do_prof = []
                for item in grade_aulas:
                    if item['prof'] == prof:
                        chave = (item['turma'], d, aula, prof, item['materia'])
                        if chave in horario:
                            vars_do_prof.append(horario[chave])
                if len(vars_do_prof) > 1:
                    model.Add(sum(vars_do_prof) <= 1)

    # R3: Quantidade de Aulas Total
    for item in grade_aulas:
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        qtd = item['qtd']
        vars_materia = []
        aulas_por_dia = turmas_totais[turma] // 5
        for d in range(len(dias_semana)):
            for aula in range(aulas_por_dia):
                chave = (turma, d, aula, prof, materia)
                if chave in horario:
                    vars_materia.append(horario[chave])
        if vars_materia:
            if qtd > 0: model.Add(sum(vars_materia) == qtd)
            else: model.Add(sum(vars_materia) == 0)

    # R4: Indisponibilidade
    for item in grade_aulas:
        prof = item['prof']
        turma = item['turma']
        materia = item['materia']
        if prof in bloqueios_globais:
            bloqueios_deste_prof = bloqueios_globais[prof]
            aulas_por_dia = turmas_totais[turma] // 5
            for d in range(len(dias_semana)):
                for aula in range(aulas_por_dia):
                    if (d, aula) in bloqueios_deste_prof:
                        chave = (turma, d, aula, prof, materia)
                        if chave in horario:
                            model.Add(horario[chave] == 0)

    # R5: GARANTIA DE AULAS VAGAS (CORRIGIDO AQUI)
    total_slots_semana = max_aulas_escola * len(dias_semana)
    
    for prof, qtd_vagas_exigidas in mapa_aulas_vagas.items():
        # Converte para int para garantir que não venha float ou numpy.int64
        qtd_vagas_int = int(qtd_vagas_exigidas)
        
        if qtd_vagas_int > 0:
            bloqueios_count = 0
            if prof in bloqueios_globais:
                for (d, aula) in bloqueios_globais[prof]:
                    if aula < max_aulas_escola:
                        bloqueios_count += 1
            
            # Cálculo da capacidade
            capacidade_calculada = total_slots_semana - bloqueios_count - qtd_vagas_int
            
            # Garante que seja int nativo do Python
            capacidade_maxima = int(capacidade_calculada)
            
            vars_todas_aulas_prof = []
            for item in grade_aulas:
                if item['prof'] == prof:
                    turma = item['turma']
                    aulas_turma = turmas_totais[turma] // 5
                    for d in range(len(dias_semana)):
                        for aula in range(aulas_turma):
                            chave = (turma, d, aula, prof, item['materia'])
                            if chave in horario:
                                vars_todas_aulas_prof.append(horario[chave])
            
            if vars_todas_aulas_prof:
                # CORREÇÃO CRÍTICA AQUI: Usando o valor já convertido
                model.Add(sum(vars_todas_aulas_prof) <= capacidade_maxima)

    # OBJETIVOS (PENALIDADES)
    todas_penalidades = []

    # 1. EVITAR DOBRADINHAS EXCESSIVAS (Peso 1)
    for item in grade_aulas:
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        aulas_por_dia = turmas_totais[turma] // 5
        
        for d in range(len(dias_semana)):
            vars_dia_materia = []
            for aula in range(aulas_por_dia):
                chave = (turma, d, aula, prof, materia)
                if chave in horario:
                    vars_dia_materia.append(horario[chave])
            
            if vars_dia_materia:
                model.Add(sum(vars_dia_materia) <= 2) 
                tem_dobradinha = model.NewBoolVar(f'dobra_{turma}_{d}_{materia}')
                model.Add(sum(vars_dia_materia) <= 1 + tem_dobradinha)
                todas_penalidades.append(tem_dobradinha)

    # 2. AGRUPAMENTO GLOBAL DE MATÉRIAS (Peso 10)
    if len(materias_para_agrupar) > 1:
        for d in range(len(dias_semana)):
            presenca_materias_no_dia = []
            for mat_nome in materias_para_agrupar:
                vars_dessa_materia_na_escola_toda = []
                for item in grade_aulas:
                    if item['materia'].strip() == mat_nome:
                        turma = item['turma']
                        aulas_dia = turmas_totais[turma] // 5
                        for aula in range(aulas_dia):
                            chave = (turma, d, aula, item['prof'], item['materia'])
                            if chave in horario:
                                vars_dessa_materia_na_escola_toda.append(horario[chave])
                
                tem_na_escola = model.NewBoolVar(f'tem_global_{mat_nome}_{d}')
                if vars_dessa_materia_na_escola_toda:
                    model.Add(sum(vars_dessa_materia_na_escola_toda) > 0).OnlyEnforceIf(tem_na_escola)
                    model.Add(sum(vars_dessa_materia_na_escola_toda) == 0).OnlyEnforceIf(tem_na_escola.Not())
                else:
                    model.Add(tem_na_escola == 0)
                presenca_materias_no_dia.append(tem_na_escola)
            
            if len(presenca_materias_no_dia) >= 2:
                for i in range(len(presenca_materias_no_dia) - 1):
                    var_a = presenca_materias_no_dia[i]
                    var_b = presenca_materias_no_dia[i+1]
                    penalidade_sep = model.NewBoolVar(f'sep_global_{d}_{i}')
                    model.Add(var_a != var_b).OnlyEnforceIf(penalidade_sep)
                    model.Add(var_a == var_b).OnlyEnforceIf(penalidade_sep.Not())
                    for _ in range(10): todas_penalidades.append(penalidade_sep)

    # 3. CONTROLES DE CARGA DO PROFESSOR (MAX 5 e EVITAR 1)
    all_teachers = set(i['prof'] for i in grade_aulas)
    for prof in all_teachers:
        for d in range(len(dias_semana)):
            vars_prof_dia = []
            for item in grade_aulas:
                if item['prof'] == prof:
                    turma = item['turma']
                    max_aulas_turma = turmas_totais[turma] // 5
                    for aula in range(max_aulas_turma):
                         chave = (turma, d, aula, prof, item['materia'])
                         if chave in horario:
                             vars_prof_dia.append(horario[chave])

            if vars_prof_dia:
                excesso_carga = model.NewIntVar(0, 15, f'excesso_{prof}_{d}')
                model.Add(excesso_carga >= sum(vars_prof_dia) - 5)
                for _ in range(5): todas_penalidades.append(excesso_carga)

                eh_um = model.NewBoolVar(f'eh_um_{prof}_{d}')
                model.Add(sum(vars_prof_dia) == 1).OnlyEnforceIf(eh_um)
                model.Add(sum(vars_prof_dia) != 1).OnlyEnforceIf(eh_um.Not())
                for _ in range(5): todas_penalidades.append(eh_um)

    if todas_penalidades:
        model.Minimize(sum(todas_penalidades))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180.0
    
    with st.spinner('🤖 O computador está pensando... (Isso pode levar até 3 minutos)'):
        status = solver.Solve(model)

    return status, solver, horario

# ==========================================
# APP PRINCIPAL (INTERFACE)
# ==========================================

st.title("Gerador de Horários Inteligente")

col_text, col_btn = st.columns([3, 1])

with col_text:
    st.markdown("### 1. Upload da Planilha")
    st.write("Dúvidas sobre o formato? Baixe o modelo ao lado.")
    st.write("O arquivo possui duas planilhas. Fique atento aos nomes das turmas, que devem ser respectivos em ambas planilhas.")
    st.write("Na planilha Turmas, defina as turmas existentes e quantas aulas SEMANAIS cada uma deve ter.")
    st.write("Na planilha Grade_Curricular, defina os professores, matérias, turmas-alvo, quantidade e indisponibilidades.")

with col_btn:
    st.write("") 
    modelo_bytes = gerar_modelo_exemplo()
    st.download_button(
        label="📥 Baixar Modelo.xlsx",
        data=modelo_bytes,
        file_name="Modelo_Horario_Escolar.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

uploaded_file = st.file_uploader("📂 Arraste o arquivo matriz.xlsx aqui", type=["xlsx"], label_visibility="collapsed")

if uploaded_file is not None:
    turmas_totais, grade_aulas, dias_semana, bloqueios_globais = carregar_dados(uploaded_file)
    
    if turmas_totais:
        if verificar_capacidade(grade_aulas, bloqueios_globais):
            st.markdown("### 2. Configurações e Geração")
            
            with st.expander("⚙️ Configurações Avançadas"):
                # 1. Seletor de Matérias Sincronizadas
                st.markdown("#### 🔗 Sincronizar Matérias (Escola Toda)")
                todas_as_materias = sorted(list(set([g['materia'] for g in grade_aulas])))
                materias_selecionadas = st.multiselect(
                    "Selecione matérias:",
                    options=todas_as_materias,
                    default=[],
                    help="As matérias selecionadas acontecerão nos mesmos dias na escola toda."
                )
                
                # 2. Editor de Aulas Vagas
                st.markdown("#### ⏳ Aulas Vagas (Hora-Atividade)")
                st.caption("Defina quantas aulas livres cada professor precisa ter na semana.")
                
                # Cria DataFrame para edição
                lista_profs = sorted(list(set([g['prof'] for g in grade_aulas])))
                df_vagas = pd.DataFrame({
                    "Professor": lista_profs,
                    "Aulas Vagas": [0] * len(lista_profs)
                })
                
                # Mostra tabela editável
                df_editado = st.data_editor(
                    df_vagas, 
                    column_config={
                        "Aulas Vagas": st.column_config.NumberColumn(
                            "Qtd. Aulas Vagas",
                            min_value=0,
                            max_value=15,
                            step=1,
                            help="Quantas aulas este professor precisa ter livre?"
                        )
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                # Converte para dicionário para passar para a função
                mapa_aulas_vagas_user = dict(zip(df_editado["Professor"], df_editado["Aulas Vagas"]))

            if st.button("🚀 Gerar Horário Agora", type="primary"):
                status, solver, horario = resolver_horario(
                    turmas_totais, 
                    grade_aulas, 
                    dias_semana, 
                    bloqueios_globais, 
                    materias_para_agrupar=materias_selecionadas,
                    mapa_aulas_vagas=mapa_aulas_vagas_user # Passa o dicionário novo
                )
                
                if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                    st.success(f"Horário Gerado com Sucesso! (Custo: {solver.ObjectiveValue()})")
                    exibir_estatisticas(grade_aulas, dias_semana, solver, horario)
                    exibir_horarios_na_tela(turmas_totais, dias_semana, solver, horario, grade_aulas)
                    pdf_bytes = gerar_pdf_bytes(turmas_totais, grade_aulas, dias_semana, solver, horario)
                    st.download_button(
                        label="📥 Baixar Horário Final em PDF",
                        data=pdf_bytes,
                        file_name="Horario_Escolar_Final.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("Não foi possível gerar um horário com essas restrições. Verifique se a quantidade de Aulas Vagas solicitada é matematicamente possível.")