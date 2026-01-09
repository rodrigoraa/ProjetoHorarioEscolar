""" from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.colors import HexColor
from ortools.sat.python import cp_model
import pandas as pd
import os
import datetime
import sys

# --- 1. LEITURA DE DADOS ---
def carregar_dados(arquivo):
    print(f"Lendo arquivo: {arquivo}...")
    try:
        df_turmas = pd.read_excel(arquivo, sheet_name='Turmas')
        df_grade = pd.read_excel(arquivo, sheet_name='Grade_Curricular')
    except Exception as e:
        print(f"Erro ao ler Excel: {e}")
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

    print("Processando a Grade e unificando bloqueios...")
    for _, row in df_grade.iterrows():
        prof_raw = str(row['Professor'])
        prof = prof_raw.lower().replace('prof.', '').replace('profª', '').replace('profa', '').strip().title()
        materia = str(row['Materia']).strip()
        
        try:
            aulas = int(row['Aulas_Por_Turma'])
        except:
            aulas = 0
            
        turmas_alvo = str(row['Turmas_Alvo']).split(',')
        
        # --- CAPTURA DE BLOQUEIOS ---
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

# --- FUNÇÃO: VERIFICAR SE A CONTA FECHA ---
def verificar_capacidade(grade_aulas, bloqueios_globais):
    print("\n>>> VERIFICANDO CAPACIDADE DOS PROFESSORES <<<")
    
    # 1. Somar carga horária de cada professor
    carga_prof = {}
    for item in grade_aulas:
        p = item['prof']
        if p not in carga_prof: carga_prof[p] = 0
        carga_prof[p] += item['qtd']

    # 2. Verificar contra os bloqueios
    erros_fatais = False
    max_slots_semana = 30 # Assumindo 5 dias * 6 aulas
    
    for prof, carga_total in carga_prof.items():
        bloqueios = 0
        if prof in bloqueios_globais:
            bloqueios_uteis = 0
            for (d, a) in bloqueios_globais[prof]:
                if a < 6: # Considera perda apenas se for da 1ª à 6ª aula
                    bloqueios_uteis += 1
            bloqueios = bloqueios_uteis

        disponivel = max_slots_semana - bloqueios
        saldo = disponivel - carga_total
        
        print(f"  > {prof}: Precisa dar {carga_total} aulas. Tem {disponivel} livres. (Saldo: {saldo})")
        
        if saldo < 0:
            print(f"    ❌ ERRO FATAL: {prof} não tem tempo suficiente! Faltam {-saldo} horários.")
            erros_fatais = True
        elif saldo < 2:
            print(f"    ⚠️  Aviso: Agenda muito apertada.")

    print("------------------------------------------------\n")
    return not erros_fatais

# --- 2. GERAR PDF ---
def gerar_pdf_bonito(turmas_totais, grade_aulas, dias_semana, solver, horario):
    timestamp = datetime.datetime.now().strftime("%Hh%Mmin")
    nome_arquivo = f"Horario_FINAL_{timestamp}.pdf"
    
    print(f"Gerando PDF: {nome_arquivo}...")
    doc = SimpleDocTemplate(nome_arquivo, pagesize=landscape(A4))
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
        
        for aula in range(aulas_por_dia):
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
        elements.append(t)
        elements.append(Spacer(1, 25))
        from reportlab.platypus import PageBreak
        elements.append(PageBreak())

    doc.build(elements)
    print(f"PDF SUCESSO! Abra o arquivo: {nome_arquivo}")
    try:
        os.startfile(nome_arquivo)
    except:
        pass

# --- 3. EXECUÇÃO PRINCIPAL ---
def main():
    arquivo_excel = 'matriz.xlsx' 
    if not os.path.exists(arquivo_excel):
        print(f"ERRO: Não encontrei o arquivo '{arquivo_excel}'")
        return

    turmas_totais, grade_aulas, dias_semana, bloqueios_globais = carregar_dados(arquivo_excel)
    if not turmas_totais: return

    # Verifica capacidade antes de tentar resolver
    possivel = verificar_capacidade(grade_aulas, bloqueios_globais)
    if not possivel:
        print("⛔ PARE! O cálculo nem vai começar porque a conta não fecha.")
        return

    print(">>> INICIANDO MODELAGEM <<<")
    model = cp_model.CpModel()
    horario = {}

    # 1. Variáveis
    for item in grade_aulas:
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        aulas_por_dia = turmas_totais[turma] // 5 
        
        for d in range(len(dias_semana)):
            for aula in range(aulas_por_dia):
                chave = (turma, d, aula, prof, materia)
                horario[chave] = model.NewBoolVar(f'{turma}_{d}_{aula}_{prof}_{materia}')

    # --- RESTRIÇÕES OBRIGATÓRIAS ---
    
    # R1: Choque de Turma (Turma só pode ter 1 aula por vez)
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

    # R4: INDISPONIBILIDADE GLOBAL
    print("Aplicando bloqueios globais...")
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

    # =================================================================
    # R5: REGRA INTELIGENTE (PREFERÊNCIA POR 1 AULA)
    # Tenta colocar 1 aula. Se não der, permite 2 (mas pune o solver).
    # Nunca permite 3.
    # =================================================================
    print("Configurando Otimização: Evitar dobradinhas se possível...")
    
    penalidades_dobradinha = []

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
                # 1. Regra DURA: Nunca mais que 2 aulas no mesmo dia
                model.Add(sum(vars_dia_materia) <= 2)

                # 2. Regra SUAVE (Objetivo): Preferência por <= 1
                # Criamos uma variável que vale 1 se houver dobradinha, e 0 se não houver
                tem_dobradinha = model.NewBoolVar(f'dobra_{turma}_{d}_{materia}')
                
                # A lógica matemática é: Soma_Aulas <= 1 + tem_dobradinha
                # Se tem_dobradinha for 0, a soma tem que ser <= 1 (Ideal)
                # Se tem_dobradinha for 1, a soma pode ser até 2 (Aceitável como última opção)
                model.Add(sum(vars_dia_materia) <= 1 + tem_dobradinha)
                
                penalidades_dobradinha.append(tem_dobradinha)

    # Dizemos ao modelo: "Encontre uma solução válida onde a SOMA das penalidades seja a MENOR possível"
    if penalidades_dobradinha:
        model.Minimize(sum(penalidades_dobradinha))

    # --- RESOLVER ---
    print("Otimizando horário (Buscando o menor número de dobradinhas)...")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180.0 
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("\n=== SUCESSO! ===")
        print(f"Custo da solução (quanto menor, menos aulas duplas): {solver.ObjectiveValue()}")
        gerar_pdf_bonito(turmas_totais, grade_aulas, dias_semana, solver, horario)
    else:
        print("\n=== FALHA: INVIÁVEL ===")
        print("Motivos prováveis:")
        print("1. As indisponibilidades dos professores estão travando tudo.")
        print("2. Tente liberar mais horários na planilha.")

if __name__ == '__main__':
    main() """
    
    
    
    
    
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.colors import HexColor
from ortools.sat.python import cp_model
import pandas as pd
import os
import datetime
import sys

# --- 1. LEITURA DE DADOS ---
def carregar_dados(arquivo):
    print(f"Lendo arquivo: {arquivo}...")
    try:
        df_turmas = pd.read_excel(arquivo, sheet_name='Turmas')
        df_grade = pd.read_excel(arquivo, sheet_name='Grade_Curricular')
    except Exception as e:
        print(f"Erro ao ler Excel: {e}")
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

    print("Processando a Grade e unificando bloqueios...")
    for _, row in df_grade.iterrows():
        prof_raw = str(row['Professor'])
        prof = prof_raw.lower().replace('prof.', '').replace('profª', '').replace('profa', '').strip().title()
        materia = str(row['Materia']).strip()
        
        try:
            aulas = int(row['Aulas_Por_Turma'])
        except:
            aulas = 0
            
        turmas_alvo = str(row['Turmas_Alvo']).split(',')
        
        # --- CAPTURA DE BLOQUEIOS ---
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

# --- FUNÇÃO: VERIFICAR SE A CONTA FECHA ---
def verificar_capacidade(grade_aulas, bloqueios_globais):
    print("\n>>> VERIFICANDO CAPACIDADE DOS PROFESSORES <<<")
    
    # 1. Somar carga horária de cada professor
    carga_prof = {}
    for item in grade_aulas:
        p = item['prof']
        if p not in carga_prof: carga_prof[p] = 0
        carga_prof[p] += item['qtd']

    # 2. Verificar contra os bloqueios
    erros_fatais = False
    max_slots_semana = 30 # Assumindo 5 dias * 6 aulas
    
    for prof, carga_total in carga_prof.items():
        bloqueios = 0
        if prof in bloqueios_globais:
            bloqueios_uteis = 0
            for (d, a) in bloqueios_globais[prof]:
                if a < 6: # Considera perda apenas se for da 1ª à 6ª aula
                    bloqueios_uteis += 1
            bloqueios = bloqueios_uteis

        disponivel = max_slots_semana - bloqueios
        saldo = disponivel - carga_total
        
        print(f"  > {prof}: Precisa dar {carga_total} aulas. Tem {disponivel} livres. (Saldo: {saldo})")
        
        if saldo < 0:
            print(f"    ❌ ERRO FATAL: {prof} não tem tempo suficiente! Faltam {-saldo} horários.")
            erros_fatais = True
        elif saldo < 2:
            print(f"    ⚠️  Aviso: Agenda muito apertada.")

    print("------------------------------------------------\n")
    return not erros_fatais

# --- 2. GERAR PDF ---
def gerar_pdf_bonito(turmas_totais, grade_aulas, dias_semana, solver, horario):
    timestamp = datetime.datetime.now().strftime("%Hh%Mmin")
    nome_arquivo = f"Horario_FINAL_{timestamp}.pdf"
    
    print(f"Gerando PDF: {nome_arquivo}...")
    doc = SimpleDocTemplate(nome_arquivo, pagesize=landscape(A4))
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
        
        for aula in range(aulas_por_dia):
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
        elements.append(t)
        elements.append(Spacer(1, 25))
        from reportlab.platypus import PageBreak
        elements.append(PageBreak())

    doc.build(elements)
    print(f"PDF SUCESSO! Abra o arquivo: {nome_arquivo}")
    try:
        os.startfile(nome_arquivo)
    except:
        pass

# --- 3. EXECUÇÃO PRINCIPAL ---
def main():
    arquivo_excel = 'matriz.xlsx' 
    if not os.path.exists(arquivo_excel):
        print(f"ERRO: Não encontrei o arquivo '{arquivo_excel}'")
        return

    turmas_totais, grade_aulas, dias_semana, bloqueios_globais = carregar_dados(arquivo_excel)
    if not turmas_totais: return

    # Verifica capacidade
    possivel = verificar_capacidade(grade_aulas, bloqueios_globais)
    if not possivel:
        print("⛔ PARE! O cálculo nem vai começar porque a conta não fecha.")
        return

    print(">>> INICIANDO MODELAGEM <<<")
    model = cp_model.CpModel()
    horario = {}

    # 1. Variáveis
    for item in grade_aulas:
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        aulas_por_dia = turmas_totais[turma] // 5 
        
        for d in range(len(dias_semana)):
            for aula in range(aulas_por_dia):
                chave = (turma, d, aula, prof, materia)
                horario[chave] = model.NewBoolVar(f'{turma}_{d}_{aula}_{prof}_{materia}')

    # --- RESTRIÇÕES OBRIGATÓRIAS ---
    
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

    # R4: INDISPONIBILIDADE GLOBAL
    print("Aplicando bloqueios globais...")
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

    # =================================================================
    # OBJETIVOS (PENALIDADES)
    # =================================================================
    
    # Lista de coisas que o sistema vai tentar evitar
    todas_penalidades = []

    # 1. EVITAR DOBRADINHAS (Peso 1)
    print("Configurando: Preferência por aulas únicas...")
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
                # OBRIGATÓRIO: Nunca mais que 2
                model.Add(sum(vars_dia_materia) <= 2)

                # PREFERÊNCIA: Tenta ser <= 1
                tem_dobradinha = model.NewBoolVar(f'dobra_{turma}_{d}_{materia}')
                model.Add(sum(vars_dia_materia) <= 1 + tem_dobradinha)
                
                # Adiciona na lista de "custo" (Peso 1)
                todas_penalidades.append(tem_dobradinha)

    # 2. AGRUPAR ARTES E EDUCAÇÃO FÍSICA (Peso 10 - Alta prioridade)
    print("Configurando: Artes e Ed. Física no mesmo dia (Imã)...")
    
    # Lista de turmas únicas
    lista_turmas_unicas = list(turmas_totais.keys())

    for turma in lista_turmas_unicas:
        for d in range(len(dias_semana)):
            # Pega as variáveis de Artes deste dia
            vars_arte = []
            for item in grade_aulas:
                if item['turma'] == turma and ('arte' in item['materia'].lower() or 'artes' in item['materia'].lower()):
                    prof = item['prof']
                    materia = item['materia']
                    aulas_por_dia = turmas_totais[turma] // 5
                    for aula in range(aulas_por_dia):
                        chave = (turma, d, aula, prof, materia)
                        if chave in horario:
                            vars_arte.append(horario[chave])

            # Pega as variáveis de Ed Física deste dia
            vars_edfis = []
            for item in grade_aulas:
                if item['turma'] == turma and ('física' in item['materia'].lower() or 'fisica' in item['materia'].lower()):
                     # Cuidado para não pegar "Física" (materia de exatas). Procura "Educação" ou nome completo.
                     if 'educa' in item['materia'].lower():
                        prof = item['prof']
                        materia = item['materia']
                        aulas_por_dia = turmas_totais[turma] // 5
                        for aula in range(aulas_por_dia):
                            chave = (turma, d, aula, prof, materia)
                            if chave in horario:
                                vars_edfis.append(horario[chave])
            
            # Se a turma tem as duas matérias cadastradas, cria a regra
            if vars_arte and vars_edfis:
                tem_arte_hj = model.NewBoolVar(f'tem_arte_{turma}_{d}')
                tem_edfis_hj = model.NewBoolVar(f'tem_edfis_{turma}_{d}')
                
                # Conecta as variáveis de aula com a variável "Tem aula hoje?"
                model.Add(sum(vars_arte) > 0).OnlyEnforceIf(tem_arte_hj)
                model.Add(sum(vars_arte) == 0).OnlyEnforceIf(tem_arte_hj.Not())
                
                model.Add(sum(vars_edfis) > 0).OnlyEnforceIf(tem_edfis_hj)
                model.Add(sum(vars_edfis) == 0).OnlyEnforceIf(tem_edfis_hj.Not())
                
                # Penalidade se forem diferentes (Um tem aula, o outro não)
                # Se tem_arte != tem_edfis, penalidade = 1
                penalidade_separacao = model.NewBoolVar(f'sep_arte_edfis_{turma}_{d}')
                model.Add(tem_arte_hj != tem_edfis_hj).OnlyEnforceIf(penalidade_separacao)
                model.Add(tem_arte_hj == tem_edfis_hj).OnlyEnforceIf(penalidade_separacao.Not())
                
                # Peso 10: O sistema odeia separar essas matérias 10x mais do que odeia dobradinhas
                # Mas como são booleans, adicionamos 10 vezes na lista ou multiplicamos no minimize
                # Vamos adicionar 10 variáveis iguais para simular peso 10
                for _ in range(10):
                    todas_penalidades.append(penalidade_separacao)

    # --- MINIMIZAR O SOFRIMENTO DO HORÁRIO ---
    if todas_penalidades:
        model.Minimize(sum(todas_penalidades))

    # --- RESOLVER ---
    print("Otimizando horário (Isso pode levar até 3 min)...")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180.0 
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("\n=== SUCESSO! ===")
        print(f"Custo de Imperfeição: {solver.ObjectiveValue()} (Zero é perfeito)")
        gerar_pdf_bonito(turmas_totais, grade_aulas, dias_semana, solver, horario)
    else:
        print("\n=== FALHA: INVIÁVEL ===")
        print("Tente liberar mais horários na planilha.")

if __name__ == '__main__':
    main()