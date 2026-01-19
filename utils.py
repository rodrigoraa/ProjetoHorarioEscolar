import streamlit as st
import pandas as pd
import io
import urllib.parse
import altair as alt
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm

def aplicar_estilo_visual():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; }
        h1, h2, h3 { font-weight: 700; color: #102a43; }
        .stApp .block-container { padding-top: 1.5rem; padding-left: 1.5rem; padding-right: 1.5rem; }
        div[data-testid="stExpander"] > div { background-color: #ffffff; border-radius: 8px; padding: 12px; box-shadow: 0 1px 2px rgba(16,42,67,0.06); }
        .stSidebar .stButton>button { width: 100%; border-radius: 8px; background: linear-gradient(90deg,#0b69a3,#1e90ff); color: white; border: none; padding: 8px 10px; }
        .stDownloadButton>button { background: linear-gradient(90deg,#0b69a3,#1e90ff); color: white; border-radius: 6px; }
        .stDataFrame table { border-radius: 8px; }
        .small-muted { font-size: 12px; color: #6b7280; }
        .section-title { font-size: 18px; font-weight: 600; color: #0b2545; margin-bottom: 6px; }
        .help-box { background: rgba(11,37,69,0.75); border-left: 4px solid #1e90ff; padding: 10px; border-radius: 6px; color: #ffffff; }
        .login-card { background: #ffffff; border-radius: 8px; padding: 16px; box-shadow: 0 6px 18px rgba(2,6,23,0.06); }
        @media (max-width: 600px) { .stSidebar { padding: 8px; } }
        /* Dark theme adjustments */
        [data-theme="dark"] .stApp .block-container { background-color: #071025; color: #e6eef8; }
        [data-theme="dark"] .login-card { background: #071025; box-shadow: none; color: #e6eef8; }
        [data-theme="dark"] .help-box { background: #051427; border-left-color: #3b82f6; color: #ffffff; }
        [data-theme="dark"] .section-title { color: #cfe8ff; }
        [data-theme="dark"] .stSidebar .stButton>button, [data-theme="dark"] .stDownloadButton>button { background: linear-gradient(90deg,#0b69a3,#1e90ff); color: white; }
        </style>
    """, unsafe_allow_html=True)

def exibir_instrucoes_simples():
    st.sidebar.markdown("**Instruções Rápidas**")
    st.sidebar.write("- Faça upload do arquivo Excel no painel 'Arquivo de Dados'.")
    st.sidebar.write("- Verifique a 'Análise de Capacidade' antes de gerar o horário.")
    st.sidebar.write("- Configure Itinerários e Agrupamentos quando necessário e clique em 'Gerar Horário'.")
    with st.sidebar.expander("Formato esperado (resumo)"):
        st.markdown("- Planilhas: **Turmas** e **Grade_Curricular**")
        st.markdown("- Colunas principais em 'Grade_Curricular': Professor, Materia, Turmas_Alvo, Aulas_Por_Turma")
        st.markdown("- Use 'Indisponibilidade' no formato 'seg:1, ter:3' ou nomes de dias (sex, qui)")
    st.sidebar.markdown("---")
    st.sidebar.markdown("<div class='small-muted'>Dica: baixe o modelo de exemplo se estiver em dúvida.</div>", unsafe_allow_html=True)

import streamlit as st

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

        try:
            aulas = int(row['Aulas_Por_Turma'])
        except:
            aulas = 0

        turmas_alvo = str(row['Turmas_Alvo']).split(',')

        if prof not in bloqueios_globais:
            bloqueios_globais[prof] = set()

        indisp = str(row.get('Indisponibilidade', ''))
        if pd.notna(indisp) and indisp.strip() != '' and indisp != 'nan':
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
                    except:
                        pass
                else:
                    chave_dia = p[:3]
                    if chave_dia in mapa_dias:
                        dia_oficial = mapa_dias[chave_dia]
                        d_idx = dias_semana.index(dia_oficial)
                        for i in range(10):
                            bloqueios_globais[prof].add((d_idx, i))

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

def estilizar_tabela_capacidade(df_logs):
    def colorir_status(val):
        if '✅' in val:
            color = '#2ecc71'
        elif '⚠️' in val:
            color = '#f39c12'
        else:
            color = '#e74c3c'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df_logs.style
            .applymap(colorir_status, subset=['Status'])
            .background_gradient(subset=['Saldo'], cmap='RdYlGn', vmin=-2, vmax=2)
            .format({'Carga': '{:.0f}', 'Livre': '{:.0f}', 'Saldo': '{:.0f}'}),
        use_container_width=True,
        hide_index=True
    )

def verificar_capacidade(grade_aulas, bloqueios_globais):
    st.subheader("📊 Análise de Capacidade")

    carga_prof = {}
    for item in grade_aulas:
        p = item['prof']
        if p not in carga_prof:
            carga_prof[p] = 0
        carga_prof[p] += item['qtd']

    erros_fatais = False
    max_slots_semana = 30
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
        status = "✅ OK"

        if saldo < 0:
            status = "❌ CRÍTICO"
            erros_fatais = True
        elif saldo < 2:
            status = "⚠️ Apertado"

        logs.append([prof, carga_total, disponivel, saldo, status])

    df_logs = pd.DataFrame(logs, columns=["Professor", "Carga", "Livre", "Saldo", "Status"])

    estilizar_tabela_capacidade(df_logs)

    if erros_fatais:
        st.error("Existem professores com SALDO NEGATIVO. O cálculo não será iniciado.")
    else:
        st.success("Capacidade dos professores parece OK.")

    return not erros_fatais

def exibir_horarios(turmas, dias, vars_resolvidas, grade):
    lista_turmas = sorted(turmas.keys())
    abas = st.tabs(lista_turmas)
    for aba, turma in zip(abas, lista_turmas):
        with aba:
            dados = []
            aulas = turmas[turma] // 5
            for a in range(aulas):
                if a == 3:
                    dados.append({"Horário": "INTERVALO", **{d: "---" for d in dias}})
                linha = {"Horário": f"{a+1}ª Aula"}
                for d_idx, d_nome in enumerate(dias):
                    txt = "---"
                    for item in grade:
                        if item['turma'] == turma:
                            pass

                    for item in grade:
                        if item['turma'] == turma:
                            key = (turma, d_idx, a, item['prof'], item['materia'])
                            if vars_resolvidas.get(key) == 1:
                                txt = f"{item['materia']} ({item['prof']})"
                                break

                    linha[d_nome] = txt
                dados.append(linha)
            st.dataframe(pd.DataFrame(dados), use_container_width=True)

def gerar_pdf_bytes(turmas_totais, grade_aulas, dias_semana, vars_resolvidas):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*cm, bottomMargin=1*cm, leftMargin=1*cm, rightMargin=1*cm)

    elements = []
    styles = getSampleStyleSheet()

    estilo_tabela = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d3d3d3')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ])

    lista_turmas = sorted(turmas_totais.keys())

    for i, turma in enumerate(lista_turmas):
        titulo = Paragraph(f"<b>Horário: {turma}</b>", styles['Heading3'])
        elements.append(titulo)
        elements.append(Spacer(1, 0.2*cm))

        header_texts = ['Horário'] + dias_semana
        style_header = ParagraphStyle('hdr', parent=styles['Heading4'], fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER, textColor=colors.white)
        style_cell = ParagraphStyle('cell', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=8, alignment=TA_CENTER)

        dados = [[Paragraph(h, style_header) for h in header_texts]]
        linha_intervalo_idx = -1

        if "Médio" in turma:
            aulas_antes_intervalo = 3
            aulas_depois_intervalo = 3
        else:
            aulas_antes_intervalo = 3
            aulas_depois_intervalo = 2

        total_aulas_letivas = aulas_antes_intervalo + aulas_depois_intervalo

        for aula_idx in range(total_aulas_letivas):
            if aula_idx == aulas_antes_intervalo:
                row_intervalo = [Paragraph('INTERVALO', style_header)] + [Paragraph('', style_cell) for _ in dias_semana]
                dados.append(row_intervalo)
                linha_intervalo_idx = len(dados) - 1

            linha = [Paragraph(f"{aula_idx + 1}ª Aula", style_cell)]
            
            for d in range(len(dias_semana)):
                conteudo = "---"
                for item in grade_aulas:
                    if item['turma'] == turma:
                        prof = item['prof']
                        materia = item['materia']
                        key = (item['turma'], d, aula_idx, prof, materia)
                        if vars_resolvidas.get(key) == 1:
                            conteudo = f"{materia}\n({prof})"
                            break
                
                linha.append(Paragraph(conteudo.replace('\n', '<br/>'), style_cell))
            
            dados.append(linha)

        page_width, _ = A4
        available_width = page_width - 2*cm
        first_col_w = 2.0 * cm
        rest_width = available_width - first_col_w
        day_col_w = rest_width / 5
        
        colWidths = [first_col_w] + [day_col_w] * 5

        t = Table(dados, colWidths=colWidths)
        t.setStyle(estilo_tabela)

        if linha_intervalo_idx != -1:
            estilo_intervalo = TableStyle([
                ('BACKGROUND', (0, linha_intervalo_idx), (-1, linha_intervalo_idx), colors.HexColor('#95a5a6')),
                ('TEXTCOLOR', (0, linha_intervalo_idx), (-1, linha_intervalo_idx), colors.white),
                ('SPAN', (0, linha_intervalo_idx), (-1, linha_intervalo_idx)),
                ('FONTNAME', (0, linha_intervalo_idx), (-1, linha_intervalo_idx), 'Helvetica-Bold'),
                ('ALIGN', (0, linha_intervalo_idx), (-1, linha_intervalo_idx), 'CENTER'),
            ])
            t.setStyle(estilo_intervalo)

        elements.append(t)

        if (i + 1) % 2 == 0:
            if i < len(lista_turmas) - 1:
                elements.append(PageBreak())
        else:
            elements.append(Spacer(1, 1.5*cm))

    doc.build(elements)
    buffer.seek(0)
    return buffer

def gerar_modelo_exemplo():
    output = io.BytesIO()

    dados_turmas = {
        'Turma': ['1º Ano - Fundamental B', '6º Ano - Fundamental', '3º Médio'],
        'Aulas_Semanais': [25, 25, 30]
    }
    df_t = pd.DataFrame(dados_turmas)

    dados_grade = {
        'Professor': ['Prof. Márcia', 'Prof. Beto', 'Prof. Carla', 'Prof. Ana', 'Prof. Carlos', 'Prof. Beatriz', 'Prof. João', 'Prof. Ana'],
        'Materia': ['Geografia', 'Ed. Física', 'Artes', 'Matemática', 'História', 'Português', 'Física', 'Matemática'],
        'Turmas_Alvo': ['1º Ano - Fundamental B', '1º Ano - Fundamental B', '1º Ano - Fundamental B', '1º Ano - Fundamental B, 3º Médio', '6º Ano - Fundamental', '6º Ano - Fundamental', '3º Médio', '3º Médio'],
        'Aulas_Por_Turma': [2, 2, 2, 5, 3, 4, 4, 5],
        'Indisponibilidade': ['', '', 'sex', '', 'seg:1, seg:2', '', 'ter:5', '']
    }
    df_g = pd.DataFrame(dados_grade)

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_t.to_excel(writer, sheet_name='Turmas', index=False)
        df_g.to_excel(writer, sheet_name='Grade_Curricular', index=False)
        worksheet = writer.sheets['Grade_Curricular']
        worksheet.set_column('A:A', 25)
        worksheet.set_column('C:C', 20)

    return output.getvalue()

def exibir_contagem_professores(resultado_vars, dias_semana):
    """
    Conta e exibe quantas aulas cada professor tem, com tabela estilizada
    e gráfico colorido por professor.
    """
    contagem = {}

    for chave, valor in resultado_vars.items():
        if valor == 1:
            dia_idx = chave[1]
            prof_nome = chave[3]

            if prof_nome not in contagem:
                contagem[prof_nome] = [0] * len(dias_semana)

            contagem[prof_nome][dia_idx] += 1

    if not contagem:
        st.warning("Nenhuma aula alocada para exibir.")
        return

    df = pd.DataFrame.from_dict(contagem, orient='index', columns=dias_semana)
    df['Total'] = df.sum(axis=1)
    df = df.sort_values(by='Total', ascending=False)

    st.subheader("📊 Carga Horária Detalhada")
    st.dataframe(
        df.style
        .background_gradient(cmap="Blues", subset=dias_semana)
        .highlight_max(axis=0, color="#ffcccb")
        .format("{:.0f}"),
        use_container_width=True
    )

    st.markdown("### 🎨 Gráfico de Aulas por Professor")
    
    df_grafico = df.reset_index().rename(columns={'index': 'Professor'})

    grafico = alt.Chart(df_grafico).mark_bar().encode(
        x=alt.X('Professor', sort='-y', title='Professor'),
        y=alt.Y('Total', title='Qtd de Aulas'),
        color=alt.Color('Professor', legend=None), 
        tooltip=['Professor', 'Total'] 
    ).properties(
        height=400
    )

    st.altair_chart(grafico, use_container_width=True)