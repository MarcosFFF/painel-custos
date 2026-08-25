import streamlit as st
import pandas as pd
import os
from datetime import date, datetime
from supabase import create_client, Client
import plotly.express as px
from projecao_sinistro import projetar_sinistro_mes_atual, projetar_dias_restantes
from severidade import (
    carregar_base_severidade, aplicar_filtros, ranking_por, evolucao_mensal,
    ranking_severidade, identificar_ofensores, calcular_desvios, montar_watchlist,
    comparacao_mensal,
)

# ============================================================
# Painel de Projeção de Custos — versão Streamlit
# Usa o MESMO banco Supabase já configurado (tabelas, RLS e usuários
# não precisam ser refeitos — só a "casca" da interface mudou).
# ============================================================

# ---------- logo (detectada ANTES do set_page_config, para virar também o ícone da aba) ----------
LOGO_PATH = None
for ext in ("png", "jpg", "jpeg", "svg", "webp"):
    candidato = f"logo_pbi.{ext}"
    if os.path.exists(candidato):
        LOGO_PATH = candidato
        break

st.set_page_config(page_title="Painel de Custos", page_icon=(LOGO_PATH or "📊"), layout="wide")

st.markdown("""
<style>
html, body { font-size: 14px !important; }
h1 { font-size: 1.6rem !important; }
h2 { font-size: 1.3rem !important; }
h3 { font-size: 1.1rem !important; }
[data-testid="stMetricValue"] { font-size: 1.3rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.78rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }
[data-testid="stCaptionContainer"] { font-size: 0.75rem !important; }
div[data-testid="stDataFrame"] * { font-size: 0.8rem !important; }

/* espaçamento mais compacto */
.block-container { padding-top: 3rem !important; padding-bottom: 1.5rem !important; }
div[data-testid="stVerticalBlock"] { gap: 0.35rem !important; }
hr { margin: 0.4rem 0 !important; }
div[data-testid="stMetric"] { padding: 0.15rem 0 !important; }
div.element-container { margin-bottom: 0.1rem !important; }
</style>
""", unsafe_allow_html=True)


MESES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho",
         "Agosto","Setembro","Outubro","Novembro","Dezembro"]
MESES_ABREV = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
DOW_NOMES = ["seg","ter","qua","qui","sex","sáb","dom"]  # Python: weekday() 0=seg...6=dom

hoje = date.today()
ANO_HOJE, MES_HOJE, DIA_HOJE = hoje.year, hoje.month, hoje.day

# ---------- conexão com o Supabase ----------
@st.cache_resource
def get_client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])

supabase = get_client()
ADMIN_EMAIL = st.secrets["ADMIN_EMAIL"]

def titulo_com_logo():
    if LOGO_PATH:
        col_logo, col_txt = st.columns([1, 6], vertical_alignment="center")
        with col_logo:
            st.image(LOGO_PATH, use_container_width=True)
        with col_txt:
            st.title("Painel de Projeção de Custos")
    else:
        st.title("📊 Painel de Projeção de Custos")


# ---------- funções de calendário ----------
def dias_no_mes(y, m):
    if m == 12:
        return (date(y + 1, 1, 1) - date(y, 12, 1)).days
    return (date(y, m + 1, 1) - date(y, m, 1)).days

def eh_fim_de_semana(y, m, d):
    return date(y, m, d).weekday() >= 5  # sáb=5, dom=6

def calendario(y, m):
    total = dias_no_mes(y, m)
    dn = sum(1 for d in range(1, total + 1) if eh_fim_de_semana(y, m, d))
    du = total - dn
    return total, du, dn

def fmt_brl(v):
    if v is None:
        return "—"
    s = f"{v:,.2f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"R$ {s}"

def label_mes(key):
    y, m = key.split("-")
    return f"{MESES_ABREV[int(m) - 1]}/{y}"

def mes_key(y, m):
    return f"{y:04d}-{m:02d}"

def date_key(y, m, d):
    return f"{y:04d}-{m:02d}-{d:02d}"

# ---------- validação de entrada (0,00 é um valor válido!) ----------
def valor_valido(v):
    """Um número (incluindo 0.0) é válido. None/NaN é 'vazio' e deve ser ignorado."""
    return v is not None and not (isinstance(v, float) and pd.isna(v))

# ---------- autenticação (Supabase Auth) ----------
def buscar_nome_usuario(email):
    try:
        res = supabase.table("perfis").select("nome").eq("email", email).maybe_single().execute()
        return res.data["nome"] if res.data else None
    except Exception:
        return None  # tabela "perfis" pode não existir ainda — segue sem nome

def fazer_login(email, senha):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": senha})
        return True, res.user.email, ""
    except Exception as e:
        return False, None, str(e)

def fazer_logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    for k in ["user_email", "role", "nome_usuario", "lancamentos", "historico_mensal"]:
        st.session_state.pop(k, None)

# ---------- carregamento dos dados ----------
def carregar_dados():
    diarios = supabase.table("lancamentos_diarios").select("data, valor").execute().data
    mensal = supabase.table("historico_mensal").select("mes_ano, projetado, real").execute().data
    lancamentos = {row["data"]: float(row["valor"]) for row in diarios}
    historico_mensal = {
        row["mes_ano"]: {"projetado": row["projetado"], "real": row["real"]} for row in mensal
    }
    st.session_state.lancamentos = lancamentos
    st.session_state.historico_mensal = historico_mensal

def gravar_dia(key, valor):
    """Upsert de UM dia — nunca sobrescreve os demais (chave primária = data)."""
    try:
        supabase.table("lancamentos_diarios").upsert({"data": key, "valor": float(valor)}).execute()
        st.session_state.lancamentos[key] = float(valor)
        return True, ""
    except Exception as e:
        return False, str(e)

def gravar_real_mensal(key, valor):
    if key >= mes_key(ANO_HOJE, MES_HOJE):
        return False, "O mês atual não é editável aqui — o valor real vem dos lançamentos diários."
    atual = st.session_state.historico_mensal.get(key, {"projetado": None, "real": None})
    try:
        supabase.table("historico_mensal").upsert(
            {"mes_ano": key, "projetado": atual["projetado"], "real": float(valor)}
        ).execute()
        st.session_state.historico_mensal[key] = {"projetado": atual["projetado"], "real": float(valor)}
        return True, ""
    except Exception as e:
        return False, str(e)

# ---------- cálculos (mesma lógica da versão HTML) ----------
def entradas_do_mes(y, m, total):
    return {
        d: st.session_state.lancamentos[date_key(y, m, d)]
        for d in range(1, total + 1)
        if date_key(y, m, d) in st.session_state.lancamentos
    }

def acumulado_de(entradas):
    return sum(entradas.values())

def acumulado_ate_dia(y, m, dia_limite):
    """Soma os lançamentos de um mês só até um determinado dia (para comparar 'até o mesmo ponto')."""
    total_m = dias_no_mes(y, m)
    limite = min(dia_limite, total_m)
    return sum(
        st.session_state.lancamentos[date_key(y, m, d)]
        for d in range(1, limite + 1)
        if date_key(y, m, d) in st.session_state.lancamentos
    )

def mes_anterior_de(y, m):
    return (y, m - 1) if m > 1 else (y - 1, 12)

def dias_uteis_decorridos_de(y, m, total, entradas):
    return sum(1 for d, v in entradas.items() if not eh_fim_de_semana(y, m, d))

# ============================================================
# LOGIN
# ============================================================
if "user_email" not in st.session_state:
    st.session_state.user_email = None
    st.session_state.role = None

if st.session_state.user_email is None:
    col_esq, col_meio, col_dir = st.columns([1, 2, 1])
    with col_meio:
        if LOGO_PATH:
            st.image(LOGO_PATH, width=120)
        st.title("Painel de Projeção de Custos")
        st.caption("Controladoria · faça login para continuar")
        with st.form("login_form"):
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)
        if entrar:
            if not email.strip() or not senha.strip():
                st.error("Preencha e-mail e senha.")
            else:
                ok, user_email, erro = fazer_login(email.strip(), senha)
                if ok:
                    st.session_state.user_email = user_email
                    st.session_state.role = "admin" if user_email == ADMIN_EMAIL else "viewer"
                    st.session_state.nome_usuario = buscar_nome_usuario(user_email)
                    carregar_dados()
                    st.rerun()
                else:
                    st.error(f"Login inválido: {erro}")
    st.stop()

is_admin = st.session_state.role == "admin"

if "lancamentos" not in st.session_state:
    carregar_dados()

# ============================================================
# CABEÇALHO
# ============================================================
titulo_com_logo()

nome_exibicao = st.session_state.get("nome_usuario") or st.session_state.user_email
badge = "🟢 Administrador" if is_admin else "🔵 Visualização"
col_info, col_sair = st.columns([5, 1])
with col_info:
    st.caption(f"**{nome_exibicao}** · {badge}")
with col_sair:
    if st.button("Sair", use_container_width=True):
        fazer_logout()
        st.rerun()

st.divider()

# ============================================================
# NAVEGAÇÃO PRINCIPAL — Projeção × Severidade
# ============================================================
if "pagina" not in st.session_state:
    st.session_state.pagina = "projecao"

nav1, nav2, nav_resto = st.columns([1, 1, 4])
with nav1:
    if st.button("📈 Projeção", use_container_width=True,
                 type="primary" if st.session_state.pagina == "projecao" else "secondary"):
        st.session_state.pagina = "projecao"
        st.rerun()
with nav2:
    if st.button("🔬 Severidade", use_container_width=True,
                 type="primary" if st.session_state.pagina == "severidade" else "secondary"):
        st.session_state.pagina = "severidade"
        st.rerun()

st.divider()

# ============================================================
# PÁGINA: PROJEÇÃO (funcionalidade existente, sem mudanças)
# ============================================================

if st.session_state.pagina == "projecao":

    # ---------- navegação de mês ----------
    if "view_year" not in st.session_state:
        st.session_state.view_year = ANO_HOJE
        st.session_state.view_month = MES_HOJE

    eh_mes_atual_nav = (st.session_state.view_year == ANO_HOJE and st.session_state.view_month == MES_HOJE)

    c1, c2, c3 = st.columns([1, 4, 1])
    with c1:
        if st.button("◀ Anterior", use_container_width=True):
            vy, vm = st.session_state.view_year, st.session_state.view_month - 1
            if vm < 1:
                vm, vy = 12, vy - 1
            st.session_state.view_year, st.session_state.view_month = vy, vm
            st.rerun()
    with c2:
        st.markdown(f"<h3 style='text-align:center; margin:0;'>{MESES[st.session_state.view_month - 1]} / {st.session_state.view_year}</h3>", unsafe_allow_html=True)
    with c3:
        if st.button("Seguinte ▶", use_container_width=True, disabled=eh_mes_atual_nav):
            vy, vm = st.session_state.view_year, st.session_state.view_month + 1
            if vm > 12:
                vm, vy = 1, vy + 1
            st.session_state.view_year, st.session_state.view_month = vy, vm
            st.rerun()

    c4, c5 = st.columns(2)
    with c4:
        if st.button("Ir para o mês atual", use_container_width=True, disabled=eh_mes_atual_nav):
            st.session_state.view_year, st.session_state.view_month = ANO_HOJE, MES_HOJE
            st.rerun()
    with c5:
        if st.button("🔄 Atualizar dados", use_container_width=True):
            carregar_dados()
            st.rerun()

    view_year, view_month = st.session_state.view_year, st.session_state.view_month
    total, du_total, dn_total = calendario(view_year, view_month)
    entradas = entradas_do_mes(view_year, view_month, total)
    acumulado = acumulado_de(entradas)
    decorridos = dias_uteis_decorridos_de(view_year, view_month, total, entradas)
    mes_key_atual = mes_key(view_year, view_month)
    eh_mes_atual = (view_year == ANO_HOJE and view_month == MES_HOJE)
    dado_mensal_do_mes_visto = st.session_state.historico_mensal.get(mes_key_atual)

    # ---------- projeção ----------
    if eh_mes_atual:
        resultado_sinistro = projetar_sinistro_mes_atual(
            st.session_state.lancamentos,
            st.session_state.historico_mensal,
            view_year, view_month, DIA_HOJE,
            n_meses=2, metodo="razao_soma",
        )
        projecao = resultado_sinistro["sinistro_projetado"]
        label_projetado = "Valor projetado (Sinistro)"
        if resultado_sinistro["projecao_solicitado"] is not None and resultado_sinistro["razao_media_historica"] is not None:
            nota = (f"Solicitado projetado: {fmt_brl(resultado_sinistro['projecao_solicitado'])} · "
                    f"razão histórica: {resultado_sinistro['razao_media_historica']:.2%}")
        else:
            nota = "Dados insuficientes (dias úteis decorridos ou meses fechados com Real) para calcular a projeção do Sinistro."
    elif dado_mensal_do_mes_visto and dado_mensal_do_mes_visto["projetado"] is not None:
        projecao = dado_mensal_do_mes_visto["projetado"]
        label_projetado = "Valor projetado (oficial)"
        nota = f"Projetado oficial informado para {label_mes(mes_key_atual)} (não é recalculado pela soma diária)."
    else:
        projecao = acumulado
        label_projetado = "Valor projetado (sem oficial)"
        nota = f"Sem Projetado oficial cadastrado para {label_mes(mes_key_atual)} — mostrando a soma dos lançamentos diários."

    # ============================================================
    # HERO — métricas principais
    # ============================================================
    m1, m2, m3 = st.columns(3)
    m1.metric(label_projetado, fmt_brl(projecao))
    m2.metric("Valor acumulado", fmt_brl(acumulado))
    m3.metric("Dias lançados", f"{len(entradas)} de {total}")
    st.caption(nota)

    st.divider()

    ind1, ind2, ind3 = st.columns(3)
    ind1.metric("Dias úteis decorridos / total", f"{decorridos} / {du_total}")
    ind2.metric("Total de dias de fins de semana no mês", dn_total)
    ind3.metric("Total de dias no mês", total)

    st.divider()

    # ============================================================
    # COMPARATIVOS — mês anterior e mesmo mês no ano anterior
    # (acumulado sempre cortado no dia de hoje, para comparar "até o mesmo ponto")
    # ============================================================
    st.subheader("Comparativos")

    ano_ant_mes, mes_ant_mes = mes_anterior_de(view_year, view_month)
    key_mes_anterior = mes_key(ano_ant_mes, mes_ant_mes)
    key_mesmo_mes_ano_anterior = mes_key(view_year - 1, view_month)

    dado_mes_anterior = st.session_state.historico_mensal.get(key_mes_anterior)
    dado_mesmo_mes_ano_anterior = st.session_state.historico_mensal.get(key_mesmo_mes_ano_anterior)

    proj_mes_anterior = dado_mes_anterior["projetado"] if dado_mes_anterior else None
    proj_mesmo_mes_ano_anterior = dado_mesmo_mes_ano_anterior["projetado"] if dado_mesmo_mes_ano_anterior else None

    acum_mes_anterior = acumulado_ate_dia(ano_ant_mes, mes_ant_mes, DIA_HOJE)
    acum_mesmo_mes_ano_anterior = acumulado_ate_dia(view_year - 1, view_month, DIA_HOJE)

    _, du_mes_anterior, _ = calendario(ano_ant_mes, mes_ant_mes)
    _, du_mesmo_mes_ano_anterior, _ = calendario(view_year - 1, view_month)

    def variacao_pct(atual, referencia):
        if atual is None or referencia is None or referencia == 0:
            return None
        return (atual - referencia) / referencia * 100

    col_comp1, col_comp2 = st.columns(2)
    with col_comp1:
        st.markdown(f"**{label_mes(key_mes_anterior)}** (mês anterior)")
        st.caption(f"Dias úteis totais: {du_mes_anterior}")
        delta_proj = variacao_pct(projecao, proj_mes_anterior)
        delta_acum = variacao_pct(acumulado, acum_mes_anterior)
        st.metric("Valor projetado", fmt_brl(proj_mes_anterior),
                   delta=(f"{delta_proj:+.1f}%" if delta_proj is not None else None),
                   delta_color="inverse")
        st.metric(f"Valor acumulado até dia {DIA_HOJE:02d}", fmt_brl(acum_mes_anterior),
                   delta=(f"{delta_acum:+.1f}%" if delta_acum is not None else None),
                   delta_color="inverse")
    with col_comp2:
        st.markdown(f"**{label_mes(key_mesmo_mes_ano_anterior)}** (mesmo mês, ano anterior)")
        st.caption(f"Dias úteis totais: {du_mesmo_mes_ano_anterior}")
        delta_proj_aa = variacao_pct(projecao, proj_mesmo_mes_ano_anterior)
        delta_acum_aa = variacao_pct(acumulado, acum_mesmo_mes_ano_anterior)
        st.metric("Valor projetado", fmt_brl(proj_mesmo_mes_ano_anterior),
                   delta=(f"{delta_proj_aa:+.1f}%" if delta_proj_aa is not None else None),
                   delta_color="inverse")
        st.metric(f"Valor acumulado até dia {DIA_HOJE:02d}", fmt_brl(acum_mesmo_mes_ano_anterior),
                   delta=(f"{delta_acum_aa:+.1f}%" if delta_acum_aa is not None else None),
                   delta_color="inverse")

    if projecao is None:
        st.warning("O % de variação do 'Valor projetado' não aparece porque a projeção do mês atual voltou vazia (meses fechados insuficientes com 'Real' preenchido para a metodologia do Sinistro). O % do 'Valor acumulado' continua funcionando normalmente, pois não depende da projeção.")

    st.caption("Variação % em relação ao mês/ano corrente sendo visualizado — vermelho = aumento de custo, verde = redução.")

    st.divider()

    # ============================================================
    # LANÇAMENTOS DO MÊS (retrátil — mostra ontem + hoje por padrão)
    # ============================================================
    st.subheader("Lançamentos do mês")

    linhas = []
    for d in range(1, total + 1):
        finde = eh_fim_de_semana(view_year, view_month, d)
        wd = DOW_NOMES[date(view_year, view_month, d).weekday()]
        is_hoje = eh_mes_atual and d == DIA_HOJE
        rotulo = f"{wd}{' · fim de semana' if finde else ''}{' · hoje' if is_hoje else ''}"
        linhas.append({"Dia": d, "Dia da semana": rotulo, "Valor (R$)": entradas.get(d)})

    df_dias = pd.DataFrame(linhas)

    dia_ancora = min(DIA_HOJE, total) if eh_mes_atual else total
    dias_visiveis_default = {d for d in [dia_ancora - 1, dia_ancora] if d >= 1}

    if "lista_expandida" not in st.session_state:
        st.session_state.lista_expandida = False

    expandir = st.checkbox(f"Mostrar todos os {total} dias", value=st.session_state.lista_expandida)
    st.session_state.lista_expandida = expandir

    df_exibida = df_dias if expandir else df_dias[df_dias["Dia"].isin(dias_visiveis_default)]

    editado = st.data_editor(
        df_exibida,
        hide_index=True,
        use_container_width=True,
        disabled=["Dia", "Dia da semana"] if is_admin else True,
        column_config={
            "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", step=0.01),
        },
        key=f"editor_dias_{view_year}_{view_month}_{expandir}",
    )

    if is_admin:
        for _, row in editado.iterrows():
            d = int(row["Dia"])
            novo = row["Valor (R$)"]
            atual = entradas.get(d)
            if valor_valido(novo) and novo != atual:
                key = date_key(view_year, view_month, d)
                ok, erro = gravar_dia(key, novo)
                if ok:
                    st.rerun()
                else:
                    st.error(f"Erro ao salvar dia {d:02d}: {erro}")

    st.caption("0,00 é um lançamento válido (dia sem valor) e não afeta os demais dias.")

    if eh_mes_atual:
        with st.expander("📅 Projeção dia a dia (dias restantes do mês)"):
            resultado_dias = projetar_dias_restantes(
                st.session_state.lancamentos, view_year, view_month, DIA_HOJE
            )
            if resultado_dias["dias"]:
                linhas_proj = []
                for dia, valor in sorted(resultado_dias["dias"].items()):
                    wd = date(view_year, view_month, dia).weekday()
                    linhas_proj.append({"Dia": dia, "Dia da semana": DOW_NOMES[wd], "Projetado": fmt_brl(valor)})
                st.dataframe(pd.DataFrame(linhas_proj), hide_index=True, use_container_width=True)
                st.caption("Distribuído conforme o padrão de cada dia da semana dentro de cada semana do mês (aprendido do histórico), calibrado pelo ritmo observado nos dias já lançados.")
            else:
                st.caption("Sem dias restantes para projetar, ou dados insuficientes para calcular.")

    st.divider()

    # ============================================================
    # HISTÓRICO MENSAL — Projetado × Real
    # ============================================================
    with st.expander("📊 Histórico mensal · Projetado × Real"):
        linhas_mensal = []
        mes_corrente_label = None
        opcoes_edicao = []  # (label, key) só dos meses fechados, para o formulário de edição
        for k in sorted(st.session_state.historico_mensal.keys(), reverse=True):
            dado = st.session_state.historico_mensal[k]
            eh_atual = k >= mes_key(ANO_HOJE, MES_HOJE)
            if eh_atual:
                mes_corrente_label = label_mes(k)
            else:
                opcoes_edicao.append((label_mes(k), k))
            linhas_mensal.append({
                "Mês": label_mes(k),
                "Projetado": "mês corrente" if eh_atual else fmt_brl(dado["projetado"]),
                "Real": "mês corrente" if eh_atual else fmt_brl(dado["real"]),
            })

        df_mensal_exibir = pd.DataFrame(linhas_mensal)

        if mes_corrente_label:
            st.caption(f"{mes_corrente_label} é o mês corrente — o Real dele é calculado automaticamente pelo acumulado diário (veja no topo da página).")

        st.dataframe(df_mensal_exibir, hide_index=True, use_container_width=True)

        if is_admin and opcoes_edicao:
            st.markdown("**✏️ Corrigir o Real de um mês encerrado**")
            labels_edicao = [lbl for lbl, _ in opcoes_edicao]
            escolha = st.selectbox("Mês", labels_edicao, key="select_mes_editar")
            key_escolhida = dict(opcoes_edicao)[escolha]
            valor_atual = st.session_state.historico_mensal[key_escolhida]["real"]
            novo_valor = st.number_input(
                f"Novo valor Real para {escolha}",
                value=float(valor_atual) if valor_atual is not None else 0.0,
                step=0.01,
                format="%.2f",
                key=f"input_real_{key_escolhida}",
            )
            if st.button("Salvar", key=f"salvar_real_{key_escolhida}"):
                ok, erro = gravar_real_mensal(key_escolhida, novo_valor)
                if ok:
                    st.success(f"Real de {escolha} atualizado para {fmt_brl(novo_valor)}.")
                    st.rerun()
                else:
                    st.error(f"Erro ao salvar: {erro}")

# ============================================================
# PÁGINA: SEVERIDADE
# ============================================================
elif st.session_state.pagina == "severidade":
    col_titulo_sev, col_atualizar_sev = st.columns([5, 1])
    with col_titulo_sev:
        st.subheader("🔬 Severidade")
    with col_atualizar_sev:
        if st.button("🔄 Recarregar", use_container_width=True):
            carregar_base_severidade.clear()
            st.rerun()

    agregado, aviso_carga = carregar_base_severidade(".")

    if agregado is None:
        st.error(f"Não consegui carregar os dados de severidade: {aviso_carga}")
        st.stop()

    if aviso_carga:
        st.warning(aviso_carga)

    # ---------- filtros ----------
    with st.container(border=True):
        st.markdown("**Filtros**")
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            f_mes = st.multiselect("Mês", options=sorted(agregado["MES"].dropna().unique(), reverse=True))
            f_uf = st.multiselect("UF", options=sorted(agregado["UF"].dropna().unique()))
        with fc2:
            f_regiao = st.multiselect("Região", options=sorted(agregado["REGIAO"].dropna().unique()))
            f_especialidade = st.multiselect("Especialidade", options=sorted(agregado["ESPECIALIDADE"].dropna().unique()))
        with fc3:
            f_plano = st.multiselect("Plano", options=sorted(agregado["NR_PLANO"].dropna().unique()))
            f_cluster = st.multiselect("Cluster", options=sorted(agregado["CLUSTER"].dropna().unique()))

        volume_minimo = st.slider(
            "Volume mínimo de procedimentos para considerar uma variação relevante",
            min_value=1, max_value=200, value=30,
        )

    df_filtrado = aplicar_filtros(
        agregado,
        meses=f_mes or None, ufs=f_uf or None, regioes=f_regiao or None,
        especialidades=f_especialidade or None, planos=f_plano or None, clusters=f_cluster or None,
    )

    if df_filtrado.empty:
        st.info("Nenhum dado para esses filtros.")
        st.stop()

    m1, m2, m3 = st.columns(3)
    m1.metric("Procedimentos", f"{int(df_filtrado['qtd_procedimentos'].sum()):,}".replace(",", "."))
    m2.metric("Valor pago", fmt_brl(df_filtrado["soma_vl_pago"].sum()))
    m3.metric("Quantidade de uso", f"{int(df_filtrado['soma_uso'].sum()):,}".replace(",", "."))

    st.divider()

    tab_rank, tab_evolucao, tab_watch, tab_severidade, tab_ofensores = st.tabs(
        ["Rankings", "Evolução mensal", "Watchlist", "Severidade", "Ofensores"]
    )

    # ---------- RANKINGS (tabela + gráfico de barras com rótulo) ----------
    def _grafico_ranking(df_rank, coluna, titulo):
        fig = px.bar(
            df_rank.sort_values("valor_pago"), x="valor_pago", y=coluna, orientation="h",
            text="valor_pago", title=titulo,
        )
        fig.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
        fig.update_layout(height=400, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with tab_rank:
        rc1, rc2 = st.columns(2)
        with rc1:
            rank_esp = ranking_por(df_filtrado, "ESPECIALIDADE")
            _grafico_ranking(rank_esp, "ESPECIALIDADE", "Por especialidade")
            st.dataframe(rank_esp, hide_index=True, use_container_width=True)

            rank_uf = ranking_por(df_filtrado, "UF")
            _grafico_ranking(rank_uf, "UF", "Por UF")
            st.dataframe(rank_uf, hide_index=True, use_container_width=True)
        with rc2:
            rank_proc = ranking_por(df_filtrado, "NOME_PROCEDIMENTO")
            _grafico_ranking(rank_proc, "NOME_PROCEDIMENTO", "Por procedimento")
            st.dataframe(rank_proc, hide_index=True, use_container_width=True)

            rank_reg = ranking_por(df_filtrado, "REGIAO")
            _grafico_ranking(rank_reg, "REGIAO", "Por região")
            st.dataframe(rank_reg, hide_index=True, use_container_width=True)

    # ---------- EVOLUÇÃO MENSAL (gráfico de linha) ----------
    with tab_evolucao:
        evolucao = evolucao_mensal(df_filtrado)
        fig_valor = px.line(evolucao, x="MES", y="valor_pago", markers=True, text="valor_pago", title="Valor pago por mês")
        fig_valor.update_traces(texttemplate="R$ %{text:,.0f}", textposition="top center")
        fig_valor.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_valor, use_container_width=True)

        fig_uso = px.line(evolucao, x="MES", y=["quantidade_uso", "media_uso"], markers=True, title="Uso por mês")
        fig_uso.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_uso, use_container_width=True)

        st.dataframe(evolucao, hide_index=True, use_container_width=True)

    with tab_watch:
        st.caption("Combinação de custo médio, uso médio e tendência de crescimento, ponderada pelo volume (0-100).")
        watchlist = montar_watchlist(df_filtrado)
        if not watchlist.empty:
            fig_watch = px.bar(
                watchlist.sort_values("pontuacao"), x="pontuacao", y="CD_PRESTADOR", orientation="h",
                text="pontuacao", title="Prestadores que merecem atenção",
            )
            fig_watch.update_traces(texttemplate="%{text:.0f}", textposition="outside")
            fig_watch.update_layout(height=500, margin=dict(l=10, r=10, t=40, b=10), yaxis_type="category")
            st.plotly_chart(fig_watch, use_container_width=True)
        st.dataframe(watchlist, hide_index=True, use_container_width=True)

    with tab_severidade:
        dims = {
            "Região": "REGIAO", "Cidade": "CIDADE_PRESTADOR", "Prestador (código)": "CD_PRESTADOR",
            "Procedimento": "NOME_PROCEDIMENTO", "Especialidade": "ESPECIALIDADE", "Cluster": "CLUSTER",
        }
        dim_escolhida = st.selectbox("Dimensão", list(dims.keys()))
        rank_sev = ranking_severidade(df_filtrado, dims[dim_escolhida])
        if not rank_sev.empty:
            fig_sev = px.bar(
                rank_sev.sort_values("indice_severidade"), x="indice_severidade", y=dims[dim_escolhida],
                orientation="h", text="indice_severidade", title=f"Severidade por {dim_escolhida}",
            )
            fig_sev.update_traces(texttemplate="%{text:.2f}", textposition="outside")
            fig_sev.update_layout(height=450, margin=dict(l=10, r=10, t=40, b=10), yaxis_type="category")
            st.plotly_chart(fig_sev, use_container_width=True)
        st.dataframe(rank_sev, hide_index=True, use_container_width=True)

    with tab_ofensores:
        st.markdown("**Prestadores ofensores** (destaque em pelo menos 2 de 3: custo médio, volume, uso médio — top 5%)")
        ofensores = identificar_ofensores(df_filtrado)
        st.dataframe(ofensores, hide_index=True, use_container_width=True)

        st.markdown("**Desvios** (prestador vs. média da própria especialidade)")
        desvios = calcular_desvios(df_filtrado)
        st.dataframe(desvios, hide_index=True, use_container_width=True)

        st.markdown("**Comparação com o mês anterior** (respeitando o volume mínimo)")
        comp, msg_comp = comparacao_mensal(df_filtrado, "NOME_PROCEDIMENTO", volume_minimo=volume_minimo)
        st.caption(msg_comp)
        if not comp.empty:
            comp_relevante = comp[comp["relevante"]]
            comp_ignorado = comp[~comp["relevante"]]
            st.markdown(f"*Variações relevantes (volume atual ≥ {volume_minimo}):*")
            st.dataframe(comp_relevante, hide_index=True, use_container_width=True)
            with st.expander(f"Ver também as {len(comp_ignorado)} variações abaixo do volume mínimo (informativas, não são alerta)"):
                st.dataframe(comp_ignorado, hide_index=True, use_container_width=True)
