"""
Projeção de Sinistro — metodologia da planilha (Solicitado × razão histórica)
==============================================================================
Cole este código no seu app.py, substituindo (ou ao lado d)a função projecao_sazonal_de.

RESUMO DA METODOLOGIA (extraída da sua planilha):

1. Para o mês atual, calcula a "Projeção do Solicitado" por regra de três simples:
       Projeção Solicitado = (Solicitado até hoje ÷ dias úteis decorridos) × dias úteis totais do mês

2. Para cada um dos últimos N meses FECHADOS, calcula a MESMA "Projeção do Solicitado" só que
   cortada no MESMO dia do mês (ex.: dia 16), e compara com o Sinistro real (final, já fechado)
   daquele mês:
       razão do mês = Sinistro real ÷ Projeção Solicitado (cortada no mesmo dia)

3. Tira a média dessas razões dos meses fechados.

4. Projeção do Sinistro do mês atual = Projeção Solicitado (mês atual) × média das razões.

MAPEAMENTO PARA O SEU BANCO (Supabase) — já confirmado com seus dados reais:
  - "Solicitado" diário  = st.session_state.lancamentos       (tabela lancamentos_diarios)
  - "Sinistro" mensal    = st.session_state.historico_mensal[k]["real"]   (tabela historico_mensal)

IMPORTANTE — feriados: sua planilha desconta feriados nacionais do cálculo de "dias úteis",
não só finais de semana. Incluí abaixo um calendário de feriados nacionais brasileiros
(fixos + móveis, calculados automaticamente via algoritmo de Páscoa) para bater mais perto
da sua planilha. Se sua empresa também exclui feriados municipais/estaduais específicos,
adicione as datas deles na lista FERIADOS_EXTRAS no final.
"""

from datetime import date, timedelta


# ---------- calendário de feriados nacionais (Brasil) ----------
def _pascoa(ano):
    """Calcula a data da Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano):
    """Retorna o conjunto de feriados nacionais brasileiros de um ano (fixos + móveis)."""
    pascoa = _pascoa(ano)
    return {
        date(ano, 1, 1),                       # Confraternização Universal
        pascoa - timedelta(days=48),           # Segunda de Carnaval
        pascoa - timedelta(days=47),           # Terça de Carnaval
        pascoa - timedelta(days=2),            # Sexta-feira Santa
        pascoa + timedelta(days=60),           # Corpus Christi
        date(ano, 4, 21),                      # Tiradentes
        date(ano, 5, 1),                       # Dia do Trabalho
        date(ano, 9, 7),                       # Independência
        date(ano, 10, 12),                     # Nossa Senhora Aparecida
        date(ano, 11, 2),                      # Finados
        date(ano, 11, 15),                     # Proclamação da República
        date(ano, 11, 20),                     # Consciência Negra (feriado nacional desde 2024)
        date(ano, 12, 25),                     # Natal
    }


# Se sua empresa também folga em feriados municipais/estaduais específicos
# (ex.: aniversário da cidade), adicione as datas aqui — formato date(ano, mes, dia).
FERIADOS_EXTRAS = set([
    # date(2026, 7, 26),  # exemplo
])


def eh_dia_util(d: date):
    if d.weekday() >= 5:  # sábado=5, domingo=6
        return False
    if d in feriados_nacionais(d.year):
        return False
    if d in FERIADOS_EXTRAS:
        return False
    return True


def dias_uteis_no_intervalo(ano, mes, dia_inicio, dia_fim):
    total_mes = (date(ano, mes % 12 + 1, 1) - timedelta(days=1)).day if mes < 12 else 31
    fim = min(dia_fim, total_mes)
    return sum(1 for d in range(dia_inicio, fim + 1) if eh_dia_util(date(ano, mes, d)))


# ---------- metodologia da planilha ----------
def projecao_solicitado(solicitado_ate_dia, dias_uteis_decorridos, dias_uteis_totais_mes):
    """Regra de três simples: projeta o Solicitado do mês inteiro a partir do ritmo até agora."""
    if not dias_uteis_decorridos:
        return None
    return (solicitado_ate_dia / dias_uteis_decorridos) * dias_uteis_totais_mes


def solicitado_ate_dia_do_mes(lancamentos: dict, ano, mes, dia_corte):
    """Soma os lançamentos diários (= Solicitado) de um mês até um dia específico."""
    total_mes_dias = (date(ano, mes % 12 + 1, 1) - timedelta(days=1)).day if mes < 12 else 31
    limite = min(dia_corte, total_mes_dias)
    soma = 0.0
    for d in range(1, limite + 1):
        key = f"{ano:04d}-{mes:02d}-{d:02d}"
        if key in lancamentos:
            soma += lancamentos[key]
    return soma


def ultimo_dia_com_dado(lancamentos: dict, ano, mes, dia_corte):
    """
    Encontra o último dia (até dia_corte) que REALMENTE tem lançamento no mês.
    Isso evita contar 'hoje' como dia útil decorrido quando hoje ainda não foi lançado —
    o mesmo problema de contar um dia sem dado como se já tivesse fechado.
    """
    total_mes_dias = (date(ano, mes % 12 + 1, 1) - timedelta(days=1)).day if mes < 12 else 31
    limite = min(dia_corte, total_mes_dias)
    ultimo = 0
    for d in range(1, limite + 1):
        key = f"{ano:04d}-{mes:02d}-{d:02d}"
        if key in lancamentos:
            ultimo = d
    return ultimo


def razao_media_historica(lancamentos: dict, historico_mensal: dict, ano_atual, mes_atual,
                            dia_corte, n_meses=2, metodo="razao_soma"):
    """
    Calcula a razão histórica (Sinistro real ÷ Projeção do Solicitado no mesmo dia de corte)
    para os últimos `n_meses` meses FECHADOS antes do mês atual.

    metodo="media_razoes" -> tira a razão de cada mês e depois faz a média simples delas.
    metodo="razao_soma"   -> soma todos os Sinistros e todas as Projeções dos meses, e divide
                             soma/soma (dá mais peso a meses com valores maiores).

    Testando contra a planilha de referência, n_meses=2 com metodo="razao_soma" foi o que
    chegou mais perto do valor esperado (~0,18% de diferença) — mas vale você comparar com
    a sua planilha ao vivo e ajustar esses dois parâmetros se precisar de mais precisão.
    """
    meses_fechados = []
    y, m = ano_atual, mes_atual
    while len(meses_fechados) < n_meses:
        m -= 1
        if m < 1:
            m, y = 12, y - 1
        meses_fechados.append((y, m))
    meses_fechados.reverse()

    pares = []  # (sinistro_real, projecao_solicitado) de cada mês fechado
    for (y, m) in meses_fechados:
        mk = f"{y:04d}-{m:02d}"
        dado_mensal = historico_mensal.get(mk)
        if not dado_mensal or dado_mensal.get("real") is None:
            continue

        sol_ate = solicitado_ate_dia_do_mes(lancamentos, y, m, dia_corte)
        du_ate = dias_uteis_no_intervalo(y, m, 1, dia_corte)
        du_total = dias_uteis_no_intervalo(y, m, 1, 31)

        proj = projecao_solicitado(sol_ate, du_ate, du_total)
        if proj:
            pares.append((dado_mensal["real"], proj))

    if not pares:
        return None

    if metodo == "razao_soma":
        soma_sinistros = sum(s for s, _ in pares)
        soma_projs = sum(p for _, p in pares)
        return soma_sinistros / soma_projs if soma_projs else None
    else:  # media_razoes
        razoes = [s / p for s, p in pares]
        return sum(razoes) / len(razoes)


def projetar_sinistro_mes_atual(lancamentos: dict, historico_mensal: dict,
                                  ano_atual, mes_atual, dia_corte, n_meses=2, metodo="razao_soma"):
    """
    Função principal: retorna a projeção do Sinistro para o mês atual, seguindo
    exatamente a metodologia da planilha.

    Parâmetros:
      lancamentos       -> st.session_state.lancamentos (Solicitado diário)
      historico_mensal  -> st.session_state.historico_mensal (Sinistro mensal fechado em ["real"])
      ano_atual, mes_atual -> mês sendo projetado
      dia_corte         -> até que dia do mês considerar (ex.: dia de hoje)
      n_meses           -> quantos meses fechados usar (padrão 2 — foi o que mais bateu no teste)
      metodo            -> "razao_soma" (padrão) ou "media_razoes" — teste os dois com sua planilha

    Retorna um dict com todos os valores intermediários, para você conferir/exibir no painel.
    """
    dia_corte_efetivo = ultimo_dia_com_dado(lancamentos, ano_atual, mes_atual, dia_corte)

    sol_ate = solicitado_ate_dia_do_mes(lancamentos, ano_atual, mes_atual, dia_corte_efetivo)
    du_ate = dias_uteis_no_intervalo(ano_atual, mes_atual, 1, dia_corte_efetivo)
    du_total = dias_uteis_no_intervalo(ano_atual, mes_atual, 1, 31)

    proj_sol = projecao_solicitado(sol_ate, du_ate, du_total)
    razao = razao_media_historica(lancamentos, historico_mensal, ano_atual, mes_atual, dia_corte,
                                    n_meses=n_meses, metodo=metodo)

    sinistro_projetado = (proj_sol * razao) if (proj_sol and razao) else None

    return {
        "solicitado_ate_dia": sol_ate,
        "dias_uteis_decorridos": du_ate,
        "dias_uteis_totais": du_total,
        "projecao_solicitado": proj_sol,
        "razao_media_historica": razao,
        "sinistro_projetado": sinistro_projetado,
    }


# ---------- sazonalidade cruzada: semana do mês × dia da semana ----------
def semana_do_mes(dia):
    """Bucket de 7 em 7 dias: dias 1-7=semana1 (índice 0), 8-14=semana2, 15-21=semana3,
    22-28=semana4, 29-31=semana5."""
    return min((dia - 1) // 7, 4)


def indice_semana_dow(lancamentos: dict, min_amostras=5):
    """
    Aprende um índice de sazonalidade CRUZADO (semana do mês × dia da semana) a partir do
    histórico diário completo. Para cada dia do histórico, calcula o quanto ele desviou da
    média do mês a que pertence, e agrupa esses desvios por (semana do mês, dia da semana) —
    assim "3ª terça-feira do mês" tem seu próprio índice, diferente de "1ª terça-feira".

    Retorna um dict {(semana_0a4, dia_semana_0a6): índice}. Combinações sem amostras
    suficientes (min_amostras) caem no valor neutro 1.0, para não distorcer com pouco dado.
    """
    por_mes = {}
    for key, valor in lancamentos.items():
        mk = key[:7]
        por_mes.setdefault(mk, []).append(valor)
    media_mes = {mk: sum(v) / len(v) for mk, v in por_mes.items() if len(v) > 0}

    soma, cont = {}, {}
    for key, valor in lancamentos.items():
        mk = key[:7]
        if media_mes.get(mk, 0) == 0:
            continue
        y, m, d = (int(x) for x in key.split("-"))
        wd = date(y, m, d).weekday()
        sem = semana_do_mes(d)
        chave = (sem, wd)
        soma[chave] = soma.get(chave, 0) + valor / media_mes[mk]
        cont[chave] = cont.get(chave, 0) + 1

    indice = {}
    for sem in range(5):
        for wd in range(7):
            chave = (sem, wd)
            if cont.get(chave, 0) >= min_amostras:
                indice[chave] = soma[chave] / cont[chave]
            else:
                indice[chave] = 1.0
    return indice


def projetar_dias_restantes(lancamentos: dict, ano, mes, dia_corte, min_amostras=5):
    """
    Projeta o valor de CADA dia restante do mês (de dia_corte+1 até o último dia do mês),
    combinando:
      1) o total do mês inteiro projetado por regra de três simples (run-rate de dias úteis);
      2) distribuído pelos dias restantes conforme o índice semana-do-mês × dia-da-semana,
         aprendido do histórico — então dias parecidos (ex.: todas as terças) NÃO recebem
         mais o mesmo valor; cada um pesa conforme seu padrão real naquela posição do mês.

    Retorna:
      {
        "projecao_mes": total projetado do mês inteiro,
        "dias": {dia: valor_projetado, ...}   # só os dias APÓS dia_corte
      }
    """
    total_dias_mes = (date(ano, mes % 12 + 1, 1) - timedelta(days=1)).day if mes < 12 else 31

    dia_corte_efetivo = ultimo_dia_com_dado(lancamentos, ano, mes, dia_corte)

    soma_ate = solicitado_ate_dia_do_mes(lancamentos, ano, mes, dia_corte_efetivo)
    du_ate = dias_uteis_no_intervalo(ano, mes, 1, dia_corte_efetivo)
    du_total = dias_uteis_no_intervalo(ano, mes, 1, 31)

    projecao_mes = projecao_solicitado(soma_ate, du_ate, du_total)
    if projecao_mes is None:
        return {"projecao_mes": None, "dias": {}}

    valor_restante = projecao_mes - soma_ate
    indice = indice_semana_dow(lancamentos, min_amostras=min_amostras)

    pesos = {}
    for d in range(dia_corte_efetivo + 1, total_dias_mes + 1):
        wd = date(ano, mes, d).weekday()
        sem = semana_do_mes(d)
        pesos[d] = indice.get((sem, wd), 1.0)
    soma_pesos = sum(pesos.values())

    dias_projetados = {}
    if soma_pesos > 0:
        for d, peso in pesos.items():
            dias_projetados[d] = valor_restante * (peso / soma_pesos)

    return {"projecao_mes": projecao_mes, "dias": dias_projetados}


# ---------- exemplo de uso dentro do app.py ----------
# resultado = projetar_sinistro_mes_atual(
#     st.session_state.lancamentos,
#     st.session_state.historico_mensal,
#     ANO_HOJE, MES_HOJE, DIA_HOJE,
#     n_meses=2, metodo="razao_soma",
# )
# projecao = resultado["sinistro_projetado"]
#
# Se não bater exato com sua planilha, tente:
#   - n_meses=3 ou n_meses=4
#   - metodo="media_razoes"
# e compare qual combinação reproduz o número que você vê na planilha.

# ---------- exemplo de uso: quebra dia a dia (dias restantes do mês) ----------
# resultado_dias = projetar_dias_restantes(
#     st.session_state.lancamentos,
#     ANO_HOJE, MES_HOJE, DIA_HOJE,
# )
# for dia, valor in sorted(resultado_dias["dias"].items()):
#     print(dia, valor)
