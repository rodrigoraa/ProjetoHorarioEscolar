import pandas as pd
import streamlit as st
import io

@st.cache_data(ttl=3600, show_spinner="Lendo e processando dados...")
def carregar_dados(arquivo_upload):
    try:
        df_turmas = pd.read_excel(arquivo_upload, sheet_name='Turmas')
        df_grade = pd.read_excel(arquivo_upload, sheet_name='Grade_Curricular')
        
        cols_obrigatorias = {'Professor', 'Materia', 'Turmas_Alvo', 'Aulas_Por_Turma'}
        if not cols_obrigatorias.issubset(df_grade.columns):
            st.error(f"Erro: Faltam colunas na aba Grade_Curricular: {cols_obrigatorias}")
            return None, None, None, {}, {}

    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return None, None, None, {}, {}

    turmas_totais = {}
    config_itinerarios = {}

    for _, row in df_turmas.iterrows():
        t = str(row['Turma']).strip()
        aulas_sem = int(row['Aulas_Semanais'])
        turmas_totais[t] = aulas_sem
        
        if aulas_sem > 25:
             config_itinerarios[t] = [] 

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
    
    bloqueios_finais = {k: list(v) for k, v in bloqueios_globais.items()}

    return turmas_totais, grade_aulas, dias_semana, bloqueios_finais, config_itinerarios

def gerar_modelo_exemplo():
    """Gera o arquivo Excel padrão para download."""
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