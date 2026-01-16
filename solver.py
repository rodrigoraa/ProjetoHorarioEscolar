import math
from ortools.sat.python import cp_model
from collections import defaultdict

def resolver_horario(
    turmas_totais,
    grade_aulas,
    dias_semana,
    bloqueios_globais,
    config_itinerarios={},
    materias_para_agrupar=[],
    mapa_aulas_vagas={},
    permite_geminada=True
):
    """
    Motor de otimização Google OR-Tools.
    Responsável por distribuir as aulas respeitando as restrições e Itinerários.
    """
    model = cp_model.CpModel()
    horario_vars = {}
    termos_custo = []
    detalhes_audit = []

    mapa_turma_horario = defaultdict(list)
    mapa_prof_horario = defaultdict(list)
    mapa_turma_prof_materia = defaultdict(list)
    mapa_conteudo_turma = defaultdict(set)

    slots_por_turma = {}
    for t, qtd_aulas in turmas_totais.items():
        slots = math.ceil(qtd_aulas / 5)
        slots_por_turma[t] = max(5, slots)

    max_aulas_escola = max(slots_por_turma.values()) if slots_por_turma else 5

    for item in grade_aulas:
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']

        aulas_dia = slots_por_turma.get(turma, 5)
        mapa_conteudo_turma[turma].add((prof, materia))

        for d in range(len(dias_semana)):
            for a in range(aulas_dia):
                key = (turma, d, a, prof, materia)
                var = model.NewBoolVar(f"H_{turma}_{prof}_{materia}_{d}_{a}")
                horario_vars[key] = var

                mapa_turma_horario[(turma, d, a)].append(var)
                mapa_prof_horario[(prof, d, a)].append(var)
                mapa_turma_prof_materia[(turma, prof, materia, d, a)] = var

    for vars_list in mapa_turma_horario.values():
        model.Add(sum(vars_list) <= 1)

    for vars_list in mapa_prof_horario.values():
        model.Add(sum(vars_list) <= 1)

    for item in grade_aulas:
        vars_materia = []
        turma = item['turma']
        prof = item['prof']
        materia = item['materia']
        aulas_dia = slots_por_turma.get(turma, 5)

        for d in range(len(dias_semana)):
            for a in range(aulas_dia):
                k = (turma, d, a, prof, materia)
                if k in horario_vars:
                    vars_materia.append(horario_vars[k])
        model.Add(sum(vars_materia) == item['qtd'])

    for prof, bloqueios in bloqueios_globais.items():
        for d, a in bloqueios:
            if (prof, d, a) in mapa_prof_horario:
                for var in mapa_prof_horario[(prof, d, a)]:
                    model.Add(var == 0)

    if config_itinerarios and config_itinerarios.get('ativo'):
        aula_fixa = config_itinerarios['aula_idx']
        dias_fixos = config_itinerarios['dias_idx']
        materias_itin = set(config_itinerarios['materias'])

        turmas_com_itinerario = set()
        for item in grade_aulas:
            if item['materia'] in materias_itin:
                turmas_com_itinerario.add(item['turma'])

        for k, var in horario_vars.items():
            t, d, a, prof, mat = k

            if mat in materias_itin:
                if a != aula_fixa or d not in dias_fixos:
                    model.Add(var == 0)
            else:
                if t in turmas_com_itinerario:
                    if a == aula_fixa and d in dias_fixos:
                        model.Add(var == 0)

    if not permite_geminada:
        for turma in turmas_totais:
            profs_dessa_turma = set(p for (p, m) in mapa_conteudo_turma[turma])
            aulas_dia = slots_por_turma.get(turma, 5)

            for prof in profs_dessa_turma:
                materias_do_prof = [m for (p, m) in mapa_conteudo_turma[turma] if p == prof]
                for d in range(len(dias_semana)):
                    for a in range(aulas_dia - 1):
                        vars_agora = []
                        vars_depois = []
                        for mat in materias_do_prof:
                            v_now = mapa_turma_prof_materia.get((turma, prof, mat, d, a))
                            v_next = mapa_turma_prof_materia.get((turma, prof, mat, d, a+1))
                            if v_now is not None:
                                vars_agora.append(v_now)
                            if v_next is not None:
                                vars_depois.append(v_next)

                        if vars_agora and vars_depois:
                            model.Add(sum(vars_agora) + sum(vars_depois) <= 1)

    PESO_JANELA = 500
    PESO_DIA_CHEIO = 200

    profs_unicos = set(item['prof'] for item in grade_aulas)

    for prof in profs_unicos:
        limite_janelas = mapa_aulas_vagas.get(prof, 2)

        for d in range(len(dias_semana)):
            vars_dia_prof = []
            for a in range(max_aulas_escola):
                vars_dia_prof.extend(mapa_prof_horario.get((prof, d, a), []))

            if not vars_dia_prof:
                continue

            total_dia = model.NewIntVar(0, max_aulas_escola, f"tot_{prof}_{d}")
            model.Add(total_dia == sum(vars_dia_prof))

            excesso = model.NewIntVar(0, max_aulas_escola, f"over_{prof}_{d}")
            model.Add(excesso >= total_dia - 4)
            model.Add(excesso >= 0)
            termos_custo.append(excesso * PESO_DIA_CHEIO)

            PESO_SINGLE = 1000
            is_single = model.NewBoolVar(f"single_{prof}_{d}")
            model.Add(total_dia == 1).OnlyEnforceIf(is_single)
            model.Add(total_dia != 1).OnlyEnforceIf(is_single.Not())
            termos_custo.append(is_single * PESO_SINGLE)
            detalhes_audit.append({
                "tipo": "Single",
                "desc": f"{prof} (Dia {d}) - aula única",
                "var": is_single,
                "peso": PESO_SINGLE
            })

            trabalha_no_horario = []
            for a in range(max_aulas_escola):
                vars_slot = mapa_prof_horario.get((prof, d, a), [])
                if vars_slot:
                    b = model.NewBoolVar(f"trab_{prof}_{d}_{a}")
                    model.Add(sum(vars_slot) == b)
                    trabalha_no_horario.append(b)
                else:
                    trabalha_no_horario.append(0)

            tem_aula = model.NewBoolVar(f"tem_{prof}_{d}")
            soma_trab = sum(t for t in trabalha_no_horario if not isinstance(t, int))
            model.Add(soma_trab > 0).OnlyEnforceIf(tem_aula)
            model.Add(soma_trab == 0).OnlyEnforceIf(tem_aula.Not())

            ini = model.NewIntVar(0, max_aulas_escola, f"ini_{prof}_{d}")
            fim = model.NewIntVar(0, max_aulas_escola, f"fim_{prof}_{d}")

            for idx, val in enumerate(trabalha_no_horario):
                if not isinstance(val, int):
                    model.Add(ini <= idx).OnlyEnforceIf(val)
                    model.Add(fim >= idx).OnlyEnforceIf(val)

            span = model.NewIntVar(0, max_aulas_escola, f"span_{prof}_{d}")
            model.Add(span == fim - ini + 1).OnlyEnforceIf(tem_aula)
            model.Add(span == 0).OnlyEnforceIf(tem_aula.Not())

            qtd_janelas = model.NewIntVar(0, max_aulas_escola, f"jan_{prof}_{d}")
            model.Add(qtd_janelas == span - soma_trab).OnlyEnforceIf(tem_aula)

            exc_jan = model.NewIntVar(0, max_aulas_escola, f"exc_j_{prof}_{d}")
            model.Add(exc_jan >= qtd_janelas - limite_janelas)
            model.Add(exc_jan >= 0)
            termos_custo.append(exc_jan * PESO_JANELA)

            detalhes_audit.append({
                "tipo": "Janelas",
                "desc": f"{prof} (Dia {d})",
                "var": exc_jan,
                "peso": PESO_JANELA
            })

    if permite_geminada:
        PESO_GEMINADA = 10

        for item in grade_aulas:
            if item['qtd'] < 2:
                continue

            turma = item['turma']
            prof = item['prof']
            materia = item['materia']
            aulas_dia = slots_por_turma.get(turma, 5)

            for d in range(len(dias_semana)):
                for a in range(aulas_dia - 1):
                    var1 = mapa_turma_prof_materia.get((turma, prof, materia, d, a))
                    var2 = mapa_turma_prof_materia.get((turma, prof, materia, d, a+1))

                    if var1 is not None and var2 is not None:
                        foi_geminada = model.NewBoolVar(f"gem_{turma}_{prof}_{materia}_{d}_{a}")

                        model.AddBoolAnd([var1, var2]).OnlyEnforceIf(foi_geminada)
                        model.AddBoolOr([var1.Not(), var2.Not()]).OnlyEnforceIf(foi_geminada.Not())

                        termos_custo.append(foi_geminada * -PESO_GEMINADA)

    if termos_custo:
        model.Minimize(sum(termos_custo))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    solver.parameters.linearization_level = 0

    status = solver.Solve(model)

    resultados = {}
    auditoria_final = []

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for k, v in horario_vars.items():
            if solver.Value(v) == 1:
                resultados[k] = 1

        for item in detalhes_audit:
            try:
                val = solver.Value(item['var'])
                if val > 0:
                    auditoria_final.append({
                        "Tipo": item["tipo"],
                        "Descrição": item["desc"],
                        "Custo": val * item["peso"]
                    })
            except:
                pass

        return "OK", resultados, solver.ObjectiveValue(), auditoria_final

    return "ERRO", {}, 0, []