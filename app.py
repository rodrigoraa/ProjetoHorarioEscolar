import streamlit as st
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

st.title("🏫 Gerador de Horários Inteligente")
st.markdown("Faça upload da planilha, clique em gerar, visualize as abas e baixe o PDF.")

# --- 1. LEITURA DE DADOS ---
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
        
        try:
            aulas = int(row['Aulas_Por_Turma'])
        except:
            aulas = 0
            
        turmas_alvo = str(row['Turmas_Alvo']).split(',')
        
        # CAPTURA DE BLOQUEIOS
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
                    # Bloqueio de dia inteiro
                    chave_dia = p[:3]
                    if chave_dia in mapa_dias:
                        dia_oficial = mapa_dias[chave_dia]
                        d_idx = dias_semana.index(dia_oficial)
                        for i in range(10): 
                            bloqueios_globais[prof].add((d_idx, i))

        for t_raw in turmas_alvo:
            turma = t_raw.strip()
            if turma in turmas_totais:
                grade_aulas.append({
                    'prof': prof,
                    'materia': materia,
                    'turma': turma,
                    'qtd': aulas
                })
    
    return turmas_totais, grade_aulas, dias_semana, bloqueios_globais

# --- VERIFICAR CAPACIDADE ---
def verificar_capacidade(grade_aulas, bloqueios_globais):
    st.subheader("📊 Análise de Capacidade")
    
    carga_prof = {}
    for item in grade_aulas:
        p = item['prof']
        if p not in carga_prof: carga_prof[p] = 0
        carga_prof[p] += item['qtd']

    erros_fatais = False
    max_slots_semana = 30
    
    col1, col2 = st.columns(2)
    
    logs = []
    
    for prof, carga_total in carga_prof.items():
        bloqueios = 0
        if prof in bloqueios_globais:
            bloqueios_uteis = 0
            for (d, a) in bloqueios_globais[prof]:
                if a < 6: 
                    bloqueios_uteis += 1
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

# --- GERAR PDF EM MEMÓRIA ---
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

# --- ESTATÍSTICAS NA TELA ---
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
    
    # Heatmap colorido (Requer matplotlib instalado)
    st.dataframe(
        df_stats.style.background_gradient(subset=dias_semana, cmap="Blues"),
        use_container_width=True
    )

# --- NOVO: VISUALIZAR GRADES NA TELA ---
def exibir_horarios_na_tela(turmas_totais, dias_semana, solver, horario, grade_aulas):
    st.markdown("---")
    st.subheader("🏫 Visualização dos Horários das Turmas")
    
    # Cria abas para cada turma
    lista_turmas = sorted(turmas_totais.keys())
    abas = st.tabs(lista_turmas)
    
    for aba, turma in zip(abas, lista_turmas):
        with aba:
            aulas_por_dia = turmas_totais[turma] // 5
            dados_grade = []
            
            for aula in range(aulas_por_dia):
                # Inserir Intervalo visualmente
                if aula == 3:
                     dados_grade.append({
                        "Horário": "INTERVALO", 
                        "Seg": "---", "Ter": "---", "Qua": "---", "Qui": "---", "Sex": "---"
                    })

                linha_dict = {"Horário": f"{aula + 1}ª Aula"}
                
                for d_idx, dia_nome in enumerate(dias_semana):
                    conteudo = "---"
                    # Busca quem está dando aula neste slot
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
            
            df_grade_visual = pd.DataFrame(dados_grade)
            st.dataframe(df_grade_visual, use_container_width=True)


# --- LÓGICA DO SOLVER ---
def resolver_horario(turmas_totais, grade_aulas, dias_semana, bloqueios_globais):
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
            if qtd > 0:
                model.Add(sum(vars_materia) == qtd)
            else:
                model.Add(sum(vars_materia) == 0)

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

    # OBJETIVOS (PENALIDADES)
    todas_penalidades = []

    # 1. EVITAR DOBRADINHAS EXCESSIVAS
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
                # OBRIGATÓRIO: Nunca > 2
                model.Add(sum(vars_dia_materia) <= 2)

                # PREFERÊNCIA: Tenta ser <= 1
                tem_dobradinha = model.NewBoolVar(f'dobra_{turma}_{d}_{materia}')
                model.Add(sum(vars_dia_materia) <= 1 + tem_dobradinha)
                todas_penalidades.append(tem_dobradinha)

    # 2. AGRUPAR ARTES E ED FISICA
    lista_turmas_unicas = list(turmas_totais.keys())
    for turma in lista_turmas_unicas:
        for d in range(len(dias_semana)):
            vars_arte = []
            vars_edfis = []
            
            # Busca vars
            for item in grade_aulas:
                if item['turma'] == turma:
                    if 'arte' in item['materia'].lower():
                        aulas_por_dia = turmas_totais[turma] // 5
                        for aula in range(aulas_por_dia):
                            chave = (turma, d, aula, item['prof'], item['materia'])
                            if chave in horario: vars_arte.append(horario[chave])
                    elif 'educa' in item['materia'].lower() and 'física' in item['materia'].lower():
                        aulas_por_dia = turmas_totais[turma] // 5
                        for aula in range(aulas_por_dia):
                            chave = (turma, d, aula, item['prof'], item['materia'])
                            if chave in horario: vars_edfis.append(horario[chave])
            
            if vars_arte and vars_edfis:
                tem_arte = model.NewBoolVar(f'tem_arte_{turma}_{d}')
                tem_edfis = model.NewBoolVar(f'tem_edfis_{turma}_{d}')
                
                model.Add(sum(vars_arte) > 0).OnlyEnforceIf(tem_arte)
                model.Add(sum(vars_arte) == 0).OnlyEnforceIf(tem_arte.Not())
                model.Add(sum(vars_edfis) > 0).OnlyEnforceIf(tem_edfis)
                model.Add(sum(vars_edfis) == 0).OnlyEnforceIf(tem_edfis.Not())
                
                penalidade_separacao = model.NewBoolVar(f'sep_arte_edfis_{turma}_{d}')
                model.Add(tem_arte != tem_edfis).OnlyEnforceIf(penalidade_separacao)
                model.Add(tem_arte == tem_edfis).OnlyEnforceIf(penalidade_separacao.Not())
                
                # Peso 10
                for _ in range(10): todas_penalidades.append(penalidade_separacao)

    if todas_penalidades:
        model.Minimize(sum(todas_penalidades))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180.0
    
    with st.spinner('🤖 O computador está pensando... (Isso pode levar até 3 minutos)'):
        status = solver.Solve(model)

    return status, solver, horario

# --- APP PRINCIPAL ---
uploaded_file = st.file_uploader("📂 Arraste o arquivo matriz.xlsx aqui", type=["xlsx"])

if uploaded_file is not None:
    turmas_totais, grade_aulas, dias_semana, bloqueios_globais = carregar_dados(uploaded_file)
    
    if turmas_totais:
        if verificar_capacidade(grade_aulas, bloqueios_globais):
            if st.button("🚀 Gerar Horário Agora"):
                status, solver, horario = resolver_horario(turmas_totais, grade_aulas, dias_semana, bloqueios_globais)
                
                if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                    st.success(f"Horário Gerado com Sucesso! (Custo: {solver.ObjectiveValue()})")
                    
                    # 1. MOSTRAR MAPA DE CALOR DOS PROFESSORES
                    exibir_estatisticas(grade_aulas, dias_semana, solver, horario)
                    
                    # 2. MOSTRAR GRADES VISUAIS EM ABAS (NOVIDADE)
                    exibir_horarios_na_tela(turmas_totais, dias_semana, solver, horario, grade_aulas)

                    # 3. BOTÃO DE DOWNLOAD
                    pdf_bytes = gerar_pdf_bytes(turmas_totais, grade_aulas, dias_semana, solver, horario)
                    
                    st.download_button(
                        label="📥 Baixar Horário em PDF",
                        data=pdf_bytes,
                        file_name="Horario_Escolar.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("Não foi possível gerar um horário com essas restrições.")