import pandas as pd

def verificar_soma_turmas():
    print("==================================================")
    print("      VERIFICADOR DE CARGA HORÁRIA POR TURMA")
    print("==================================================")
    
    arquivo = 'matriz.xlsx' # Ou 'escola_completa.xlsx'
    
    try:
        df_turmas = pd.read_excel(arquivo, sheet_name='Turmas')
        df_grade = pd.read_excel(arquivo, sheet_name='Grade_Curricular')
    except Exception as e:
        print(f"Erro ao ler arquivo: {e}")
        return

    # 1. Cria dicionário com o limite de cada turma
    # Ex: {'1M': 30, '6A': 25}
    limites = {}
    for _, row in df_turmas.iterrows():
        t = str(row['Turma']).strip()
        limites[t] = int(row['Aulas_Semanais'])

    # 2. Soma o que está sendo pedido na Grade
    pedidos = {t: 0 for t in limites}
    detalhes = {t: [] for t in limites} # Para mostrar quem está enchendo a turma

    print("\nSomando aulas pedidas no Excel...")
    
    for _, row in df_grade.iterrows():
        materia = str(row['Materia']).strip()
        prof = str(row['Professor']).strip()
        try:
            qtd = int(row['Aulas_Por_Turma'])
        except:
            continue # Pula se não tiver número
            
        turmas_alvo = str(row['Turmas_Alvo']).split(',')
        
        for t_raw in turmas_alvo:
            turma = t_raw.strip()
            
            # Se a turma existe no cadastro
            if turma in pedidos:
                pedidos[turma] += qtd
                detalhes[turma].append(f"{materia} ({qtd})")

    # 3. Relatório Final
    print("\n--- RELATÓRIO DE CAPACIDADE ---")
    erro_encontrado = False
    
    for turma in sorted(limites.keys()):
        limite = limites[turma]
        solicitado = pedidos[turma]
        saldo = limite - solicitado
        
        if saldo < 0:
            print(f"🔴 TURMA {turma}: ESTOUROU O LIMITE!")
            print(f"   Capacidade: {limite} aulas")
            print(f"   Solicitado: {solicitado} aulas")
            print(f"   Excesso:    {saldo * -1} aulas a mais (Remova matérias!)")
            erro_encontrado = True
        elif saldo == 0:
            print(f"🟢 Turma {turma}: Perfeita (Cheia: {solicitado}/{limite})")
        else:
            print(f"🟡 Turma {turma}: Tem folga ({solicitado}/{limite} - Sobram {saldo})")

    if erro_encontrado:
        print("\n❌ CONCLUSÃO: O horário é impossível porque não cabe tanta aula na semana.")
        print("   Você precisa diminuir a quantidade de aulas de alguma matéria nas turmas marcadas em VERMELHO.")
    else:
        print("\n✅ CONCLUSÃO: As turmas cabem na semana. Se ainda der erro, verifique se os nomes das turmas estão escritos iguais nas duas abas.")

if __name__ == '__main__':
    verificar_soma_turmas()