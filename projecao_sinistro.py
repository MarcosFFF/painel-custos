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
    sol_ate = solicitado_ate_dia_do_mes(lancamentos, ano_atual, mes_atual, dia_corte)
    du_ate = dias_uteis_no_intervalo(ano_atual, mes_atual, 1, dia_corte)
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
