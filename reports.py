import streamlit as st
import pandas as pd
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.colors import HexColor

def aplicar_estilo_visual():
    """Injeta CSS personalizado na página."""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
        html, body, [class*="css"] { font-family: 'Roboto', sans-serif; }
        div.stDataFrame {
            border-radius: 10px; padding: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        button[kind="primary"] {
            background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
            border: none; color: white !important;
        }
        </style>
    """, unsafe_allow_html=True)


def exibir_detalhes_custo(detalhes_penalidades):
    """Mostra uma tabela explicando por que o horário não foi perfeito (custo > 0)."""
    st.markdown("---")
    st.subheader("💰 Auditoria do Custo")
    
    if not detalhes_penalidades:
        st.success("🏆 Horário Perfeito! Custo Zero (ou detalhes não calculados).")
        return

    custo_total = sum(d['Custo'] for d in detalhes_penalidades)
    st.warning(f"O horário foi gerado com um custo de **{custo_total}**. Veja os motivos:")
    df = pd.DataFrame(detalhes_penalidades)
    st.dataframe(df, use_container_width=True)

def exibir_estatisticas(grade_aulas, dias_semana, vars_resolvidas):
    """Mostra um mapa de calor da carga horária dos professores por dia."""
    st.markdown("---")
    st.subheader("📅 Distribuição de Aulas por Professor (Dia a Dia)")
    professores = sorted(list(set(item['prof'] for item in grade_aulas)))
    contagem = {prof: [0]*len(dias_semana) for prof in professores}
    
    for chave, valor in vars_resolvidas.items():
        if valor == 1:
            prof = chave[3]
            dia_idx = chave[1]
            if prof in contagem:
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


def exibir_horarios_tela(turmas, dias, vars_resolvidas, grade):
    """Mostra os horários em abas interativas no Streamlit."""
    lista_turmas = sorted(turmas.keys())
    abas = st.tabs(lista_turmas)
    for aba, turma in zip(abas, lista_turmas):
        with aba:
            dados = []
            aulas = turmas[turma] // 5
            for a in range(aulas):
                if a == 3: dados.append({"Horário": "INTERVALO", **{d: "---" for d in dias}})
                linha = {"Horário": f"{a+1}ª Aula"}
                for d_idx, d_nome in enumerate(dias):
                    txt = "---"
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
    """Gera o PDF profissional para impressão."""
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
                        key = (item['turma'], d, aula, prof, materia)
                        if vars_resolvidas.get(key) == 1:
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