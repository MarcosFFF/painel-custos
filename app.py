import streamlit as st
import pandas as pd
import os
from datetime import date, datetime
from supabase import create_client, Client
import plotly.express as px
from projecao_sinistro import projetar_sinistro_mes_atual, projetar_dias_restantes
from severidade import (
    carregar_base_severidade, aplicar_filtros, evolucao_mensal,
    ranking_severidade, identificar_ofensores, calcular_desvios, montar_watchlist,
    comparacao_mensal,
)
# ============================================================
# Painel de Gestão de Sinistro — versão Streamlit
# ============================================================
# ---------- logo ----------
LOGO_PATH = None
for ext in ("png", "jpg", "jpeg", "svg", "webp"):
    candidato = f"logo_pbi.{ext}"
    if os.path.exists(candidato):
        LOGO_PATH = candidato
        break
st.set_page_config(page_title="Gestão de Sinistro - Odonto", page_icon=(LOGO_PATH or "📊"), layout="wide")
st.markdown("""
<style>
button[kind="primary"] {
    background-color: #87CEEB !important;
    border-color: #87CEEB !important;
    color: #0d2b3e !important;
}
button[kind="primary"]:hover,
button[kind="primary"]:focus,
button[kind="primary"]:active {
    background-color: #6bb8dd !important;
    border-color: #6bb8dd !important;
    color: #0d2b3e !important;
}
.block-container { padding-top: 3rem !important; padding-bottom: 1.5rem !important; }
html, body { font-size: 14px !important; }
h1 { font-size: 1.6rem !important; }
h2 { font-size: 1.3rem !important; }
h3 { font-size: 1.1rem !important; }
[data-testid="stMetricValue"] { font-size: 1.3rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.78rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }
[data-testid="stCaptionContainer"] { font-size: 0.75rem !important; }
/* Tabelas: fonte menor */
div[data-testid="stDataFrame"] * { font-size: 0.72rem !important; }
/* Tabelas: centralizar colunas numéricas */
div[data-testid="stDataFrame"] [data-testid="stTableCellText"] {
    text-align: center !important;
}
div[data-testid="stDataFrame"] [data-testid="stTableRowHeaderCell"] {
    text-align: left !important;
}
/* espaçamento mais compacto */
div[data-testid="stVerticalBlock"] { gap: 0.35rem !important; }
hr { margin: 0.4rem 0 !important; }
div[data-testid="stMetric"] { padding: 0.15rem 0 !important; }
div.element-container { margin-bottom: 0.1rem !important; }
/* Fonte menor nos filtros da aba Severidade */
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stWidgetLabel"] p {
    font-size: 0.7rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="select"] span,
div[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="select"] li {
    font-size: 0.72rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="tag"] span {
    font-size: 0.68rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="slider"] span,
div[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="slider"] div {
    font-size: 0.72rem !important;
}
</style>
""", unsafe_allow_html=True)
MESES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho",
         "Agosto","Setembro","Outubro","Novembro","Dezembro"]
MESES_ABREV = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
DOW_NOMES = ["seg","ter","qua","qui","sex","sáb","dom"]
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
            st.title("Painel de Gestão de Sinistro - Odonto")
    else:
        st.title("📊 Painel de Gestão de Sinistro - Odonto")
# ---------- funções de calendário ----------
def dias_no_mes(y, m):
    if m == 12:
        return (date(y + 1, 1, 1) - date(y, 12, 1)).days
    return (date(y, m + 1, 1) - date(y, m, 1)).days
def eh_fim_de_semana(y, m, d):
    return date(y, m, d).weekday() >= 5
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
def fmt_int(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{int(v):,}".replace(",", ".")
def fmt_float2(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = f"{v:,.2f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")
def label_mes(key):
    y, m = key.split("-")
    return f"{MESES_ABREV[int(m) - 1]}/{y}"
def mes_key(y, m):
    return f"{y:04d}-{m:02d}"
def date_key(y, m, d):
    return f"{y:04d}-{m:02d}-{d:02d}"
def valor_valido(v):
    return v is not None and not (isinstance(v, float) and pd.isna(v))
# ---------- autenticação ----------
def buscar_nome_usuario(email):
    try:
        res = supabase.table("perfis").select("nome").eq("email", email).maybe_single().execute()
        return res.data["nome"] if res.data else None
    except Exception:
        return None
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
# ---------- cálculos ----------
def entradas_do_mes(y, m, total):
    return {
        d: st.session_state.lancamentos[date_key(y, m, d)]
        for d in range(1, total + 1)
        if date_key(y, m, d) in st.session_state.lancamentos
    }
def acumulado_de(entradas):
    return sum(entradas.values())
def acumulado_ate_dia(y, m, dia_limite):
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
        st.title("Painel Gestão de Sinistro - Odonto")
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
    if st.button("🕵️ Severidade", use_container_width=True,
                 type="primary" if st.session_state.pagina == "severidade" else "secondary"):
        st.session_state.pagina = "severidade"
        st.rerun()
st.divider()
# ============================================================
# PÁGINA: PROJEÇÃO
# ============================================================
if st.session_state.pagina == "projecao":
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
            nota = ""
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
        st.warning("O % de variação do 'Valor projetado' não aparece porque a projeção do mês atual voltou vazia.")
    st.caption("Variação % em relação ao mês/ano corrente — vermelho = aumento, verde = redução.")
    st.divider()
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
                st.caption("Distribuído conforme o padrão de cada dia da semana dentro de cada semana do mês.")
            else:
                st.caption("Sem dias restantes para projetar, ou dados insuficientes.")
    st.divider()
    with st.expander("📊 Histórico mensal · Projetado × Real"):
        linhas_mensal = []
        mes_corrente_label = None
        opcoes_edicao = []
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
            st.caption(f"{mes_corrente_label} é o mês corrente — o Real dele é calculado automaticamente.")
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
        st.subheader("🕵️ Severidade")
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
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Procedimentos", fmt_int(df_filtrado["qtd_procedimentos"].sum()))
    m2.metric("Uso total", fmt_int(df_filtrado["soma_uso"].sum()))
    _uso_total = df_filtrado["soma_uso"].sum()
    _qtd_total = df_filtrado["qtd_procedimentos"].sum()
    _usuarios_total = df_filtrado["qtd_usuarios"].sum()
    m3.metric("Uso por procedimento", fmt_float2(_uso_total / _qtd_total) if _qtd_total else "—")
    m4.metric("Uso por vida", fmt_float2(_uso_total / _usuarios_total) if _usuarios_total else "—")
    st.divider()
    tab_rank, tab_evolucao, tab_watch, tab_ofensores = st.tabs(
        ["Ranking de Severidade", "Evolução mensal", "Atenção", "Ofensores"]
    )
    # ---------- RANKING DE SEVERIDADE (ISR — só gráficos, sem tabelas) ----------
    JANELA_5_BARRAS = 300  # altura fixa (px) que mostra ~5 barras; o resto rola dentro do quadro
    def _grafico_severidade(df_rank, coluna, titulo, altura=None, janela=None):
        df_plot = df_rank.sort_values("indice_severidade", ascending=True).reset_index(drop=True)
        if janela:
            # altura total cresce com a quantidade de itens (barra do mesmo tamanho sempre),
            # o quadro em volta é que fica fixo em `janela` e ganha rolagem quando sobra.
            altura_total = max(janela, 90 + len(df_plot) * 40)
        else:
            altura_total = altura or max(350, len(df_plot) * 35)
        media_grupo = df_plot["indice_severidade"].mean()
        fig = px.bar(
            df_plot, x="indice_severidade", y=coluna, orientation="h",
            custom_data=[coluna, "indice_severidade", "uso_por_procedimento", "uso_por_vida"],
            title=titulo,
            color="indice_severidade",
            color_continuous_scale=["#2ecc71", "#f1c40f", "#e74c3c"],
            color_continuous_midpoint=media_grupo,
        )
        fig.update_traces(
            texttemplate="%{x:,.2f}",
            textposition="outside",
            textfont=dict(size=10),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "ISR: %{customdata[1]:,.2f}<br>"
                "Uso por procedimento: %{customdata[2]:.2f}<br>"
                "Uso por vida: %{customdata[3]:.2f}"
                "<extra></extra>"
            ),
            cliponaxis=False,
        )
        fig.update_layout(
            height=altura_total,
            margin=dict(l=10, r=60, t=40, b=10),
            yaxis_type="category",
            coloraxis_showscale=False,
        )
        fig.add_vline(x=media_grupo, line_dash="dash", line_color="gray")
        fig.update_yaxes(tickfont=dict(size=10))
        if janela:
            with st.container(height=janela):
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.plotly_chart(fig, use_container_width=True)
    with tab_rank:
        st.caption(
            "O **Índice de Severidade Relativa (ISR)** cruza os três parâmetros de uso: "
            "**ISR = quantidade de uso ÷ (vidas × procedimentos) × 100.000** — uma taxa de uso "
            "concentrado por 100 mil vidas/procedimentos. Quanto maior, mais uso concentrado em "
            "poucas vidas e poucos procedimentos (mais severo); quanto menor, mais distribuído. "
            "A linha tracejada marca a média do próprio grupo exibido em cada gráfico. "
            "Não considera valores em R$."
        )
        rc1, rc2 = st.columns(2)
        with rc1:
            _grafico_severidade(ranking_severidade(df_filtrado, "ESPECIALIDADE", top_n=40), "ESPECIALIDADE", "Por especialidade", janela=JANELA_5_BARRAS)
            _grafico_severidade(ranking_severidade(df_filtrado, "UF", top_n=30), "UF", "Por UF", janela=JANELA_5_BARRAS)
        with rc2:
            _grafico_severidade(ranking_severidade(df_filtrado, "NOME_PROCEDIMENTO", top_n=50), "NOME_PROCEDIMENTO", "Por procedimento", janela=JANELA_5_BARRAS)
            _grafico_severidade(ranking_severidade(df_filtrado, "REGIAO"), "REGIAO", "Por região", janela=JANELA_5_BARRAS)
        st.divider()
        st.markdown("#### Severidade por outras dimensões")
        dims = {
            "Região": "REGIAO", "Cidade": "CIDADE_PRESTADOR", "Prestador (código)": "CD_PRESTADOR",
            "Procedimento": "NOME_PROCEDIMENTO", "Cluster": "CLUSTER",
        }
        dim_escolhida = st.selectbox("Dimensão", list(dims.keys()))
        rank_sev = ranking_severidade(df_filtrado, dims[dim_escolhida])
        if not rank_sev.empty:
            _grafico_severidade(rank_sev, dims[dim_escolhida], f"Severidade por {dim_escolhida}", altura=450)
        else:
            st.info("Sem dados para a dimensão selecionada.")
    with tab_evolucao:
        evolucao = evolucao_mensal(df_filtrado)
        fig_uso = px.line(
            evolucao, x="MES", y=["uso_por_procedimento", "uso_por_vida"],
            markers=True, title="Uso - Qtde e Média de uso",
        )
        _nomes_series = {"uso_por_procedimento": "Qtde", "uso_por_vida": "Média de uso"}
        fig_uso.for_each_trace(lambda t: t.update(name=_nomes_series.get(t.name, t.name), legendgroup=_nomes_series.get(t.name, t.name)))
        fig_uso.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10), legend_title_text="")
        st.plotly_chart(fig_uso, use_container_width=True)
        fig_isr = px.line(
            evolucao, x="MES", y="indice_severidade", markers=True, text="indice_severidade", title="ISR por mês",
        )
        fig_isr.update_traces(texttemplate="%{text:,.2f}", textposition="top center")
        fig_isr.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="ISR")
        st.plotly_chart(fig_isr, use_container_width=True)
        fig_uso_total = px.line(evolucao, x="MES", y="quantidade_uso", markers=True, text="quantidade_uso", title="Uso total por mês")
        fig_uso_total.update_traces(texttemplate="%{text:,.0f}", textposition="top center")
        fig_uso_total.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_uso_total, use_container_width=True)
    # ---------- ATENÇÃO (baseada apenas em uso e volume) ----------
    with tab_watch:
        st.markdown("#### Prestadores que merecem atenção")
        watchlist = montar_watchlist(df_filtrado)
        if not watchlist.empty:
            # Preparar DataFrame para o gráfico — garantir tipos corretos
            wl_plot = watchlist.copy()
            for col in ["NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER"]:
                if col not in wl_plot.columns:
                    wl_plot[col] = "—"
                wl_plot[col] = wl_plot[col].fillna("—").astype(str)
            fig_watch = px.bar(
                wl_plot.sort_values("pontuacao", ascending=True), x="pontuacao",
                y="NOME_PRESTADOR", orientation="h",
                text="pontuacao", title="Prestadores que merecem atenção",
                custom_data=["CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER"],
            )
            fig_watch.update_traces(
                texttemplate="%{text:.0f}",
                textposition="outside",
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "CPF/CNPJ: %{customdata[0]}<br>"
                    "Pontuação: %{x:.0f}<br>"
                    "UF: %{customdata[1]}<br>"
                    "Cidade: %{customdata[2]}<br>"
                    "Cluster: %{customdata[3]}"
                    "<extra></extra>"
                ),
            )
            fig_watch.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10), yaxis_type="category")
            st.plotly_chart(fig_watch, use_container_width=True)
            # Tabela com info do prestador (sem o código, com nome)
            exib_watch = watchlist.drop(columns=["CD_PRESTADOR"], errors="ignore").copy()
            exib_watch["qtd_procedimentos"] = exib_watch["qtd_procedimentos"].map(fmt_int)
            exib_watch["qtd_usuarios"] = exib_watch["qtd_usuarios"].map(fmt_int)
            exib_watch["quantidade_uso"] = exib_watch["quantidade_uso"].map(fmt_int)
            exib_watch["uso_por_procedimento"] = exib_watch["uso_por_procedimento"].map(fmt_float2)
            exib_watch["uso_por_vida"] = exib_watch["uso_por_vida"].map(fmt_float2)
            exib_watch["indice_severidade"] = exib_watch["indice_severidade"].map(fmt_float2)
            exib_watch["tendencia_pct"] = exib_watch["tendencia_pct"].map(lambda v: f"{v:+.1f}%")
            exib_watch["pontuacao"] = exib_watch["pontuacao"].map(lambda v: f"{v:.0f}")
            st.dataframe(exib_watch, hide_index=True, use_container_width=True)
        else:
            st.info("Sem dados para montar a watchlist.")
    # ---------- OFENSORES (baseado só em volume e uso) ----------
    with tab_ofensores:
        st.markdown("#### 🚨 Prestadores ofensores")
        st.caption(
            "Um prestador é marcado como **ofensor** quando atende **≥ 2 de 3 critérios** no top 5% "
            "(percentil 95). Abaixo, a explicação de cada coluna:"
        )
        with st.expander("📖 O que significa cada alerta?", expanded=True):
            st.markdown(
                "- 🔴 **alerta_volume** é acionado quando a **quantidade de procedimentos** "
                "está no **top 5% maior**. Indica volume anormalmente alto de solicitações."
                "\n"
                "- 🔴 **alerta_uso_procedimento** é acionado quando o **uso por procedimento** "
                "(quantidade de uso ÷ procedimentos) está no **top 5% mais alto**. "
                "Indica intensidade de uso elevada por procedimento."
                "\n"
                "- 🔴 **alerta_uso_vida** é acionado quando o **uso por vida** "
                "(quantidade de uso ÷ vidas/usuários distintos) está no **top 5% mais alto**. "
                "Indica intensidade de uso elevada por usuário atendido."
                "\n"
                "- 📊 **criterios_atingidos** = quantos dos 3 alertas acima foram acionados (0 a 3)."
                "\n"
                "- 🚨 **relevante** é acionado quando **criterios_atingidos ≥ 2** — "
                "é o flag que marca o prestador como ofensor de fato."
                "\n"
                "- 📝 **justificativa** = texto explicando **exatamente quais critérios** "
                "foram acionados e quais os valores/limiares correspondentes."
            )
        ofensores = identificar_ofensores(df_filtrado)
        if not ofensores.empty:
            # Formatar tabela para exibição — já vem ordenada do mais para o menos severo (ISR)
            exib_of = ofensores.copy()
            exib_of["qtd_procedimentos"] = exib_of["qtd_procedimentos"].map(fmt_int)
            exib_of["qtd_usuarios"] = exib_of["qtd_usuarios"].map(fmt_int)
            exib_of["quantidade_uso"] = exib_of["quantidade_uso"].map(fmt_int)
            exib_of["uso_por_procedimento"] = exib_of["uso_por_procedimento"].map(fmt_float2)
            exib_of["uso_por_vida"] = exib_of["uso_por_vida"].map(fmt_float2)
            exib_of["indice_severidade"] = exib_of["indice_severidade"].map(fmt_float2)
            # Flags com cores
            exib_of["alerta_volume"] = exib_of["alerta_volume"].map(lambda b: "🔴 Sim" if b else "✅ Não")
            exib_of["alerta_uso_procedimento"] = exib_of["alerta_uso_procedimento"].map(lambda b: "🔴 Sim" if b else "✅ Não")
            exib_of["alerta_uso_vida"] = exib_of["alerta_uso_vida"].map(lambda b: "🔴 Sim" if b else "✅ Não")
            exib_of["criterios_atingidos"] = exib_of["criterios_atingidos"].map(lambda v: f"{v}/3")
            exib_of["relevante"] = exib_of["relevante"].map(lambda b: "🚨 OFENSOR" if b else "—")
            st.dataframe(exib_of, hide_index=True, use_container_width=True)
            # Destaque para ofensores relevantes com justificativa — retrátil e pesquisável
            relevantes = ofensores[ofensores["relevante"]].copy()
            if not relevantes.empty:
                st.divider()
                st.markdown("#### 📝 Justificativa dos ofensores")
                busca_ofensor = st.text_input(
                    "🔎 Buscar prestador (nome, código, CPF/CNPJ ou especialidade)", key="busca_ofensor"
                )
                if busca_ofensor.strip():
                    termo = busca_ofensor.strip().upper()
                    def _bate_busca(row):
                        campos = [
                            str(row.get("CD_PRESTADOR", "")), str(row.get("NOME_PRESTADOR", "")),
                            str(row.get("CNPJ_CPF_PRESTADOR", "")), str(row.get("ESPECIALIDADE", "")),
                        ]
                        return any(termo in campo.upper() for campo in campos)
                    relevantes_filtrados = relevantes[relevantes.apply(_bate_busca, axis=1)]
                else:
                    relevantes_filtrados = relevantes
                st.caption(f"{len(relevantes_filtrados)} de {len(relevantes)} ofensores exibidos.")
                for _, row in relevantes_filtrados.iterrows():
                    nome_prestador = row.get("NOME_PRESTADOR") or "—"
                    cnpj_prestador = row.get("CNPJ_CPF_PRESTADOR") or "—"
                    titulo_exp = f"Prestador {int(row['CD_PRESTADOR'])} — {nome_prestador} · ISR {row['indice_severidade']:.2f}"
                    with st.expander(titulo_exp):
                        st.markdown(
                            f"CPF/CNPJ: {cnpj_prestador} — {row['UF']} · {row['CIDADE']} · Cluster: {row['CLUSTER']}"
                        )
                        st.markdown(f"> {row['justificativa']}")
                        st.caption(
                            f"Especialidade principal: {row['ESPECIALIDADE']} · Procedimentos: {int(row['qtd_procedimentos'])} · "
                            f"Uso por procedimento: {fmt_float2(row['uso_por_procedimento'])} · Uso por vida: {fmt_float2(row['uso_por_vida'])}"
                        )
        else:
            st.info("Nenhum ofensor encontrado com os filtros atuais.")
        st.divider()
        st.markdown("**Desvios** (prestador vs. média da própria especialidade)")
        desvios = calcular_desvios(df_filtrado)
        if not desvios.empty:
            exib_desv = desvios.copy()
            exib_desv["qtd_procedimentos"] = exib_desv["qtd_procedimentos"].map(fmt_int)
            exib_desv["uso_por_procedimento"] = exib_desv["uso_por_procedimento"].map(fmt_float2)
            exib_desv["uso_por_procedimento_esp"] = exib_desv["uso_por_procedimento_esp"].map(fmt_float2)
            exib_desv["desvio_uso_procedimento_pct"] = exib_desv["desvio_uso_procedimento_pct"].map(lambda v: f"{v:+.1f}%")
            exib_desv["uso_por_vida"] = exib_desv["uso_por_vida"].map(fmt_float2)
            exib_desv["uso_por_vida_esp"] = exib_desv["uso_por_vida_esp"].map(fmt_float2)
            exib_desv["desvio_uso_vida_pct"] = exib_desv["desvio_uso_vida_pct"].map(lambda v: f"{v:+.1f}%")
            st.dataframe(exib_desv, hide_index=True, use_container_width=True)
        else:
            st.info("Sem dados para calcular desvios.")
        st.divider()
        st.markdown("**Comparação com o mês anterior** (respeitando o volume mínimo)")
        comp, msg_comp = comparacao_mensal(df_filtrado, "NOME_PROCEDIMENTO", volume_minimo=volume_minimo)
        st.caption(msg_comp)
        if not comp.empty:
            comp_relevante = comp[comp["relevante"]].drop(columns=["relevante"])
            comp_ignorado = comp[~comp["relevante"]].drop(columns=["relevante"])
            st.markdown(f"*Variações relevantes (volume atual ≥ {volume_minimo}):*")
            st.dataframe(comp_relevante, hide_index=True, use_container_width=True)
            with st.expander(f"Ver também as {len(comp_ignorado)} variações abaixo do volume mínimo"):
                st.dataframe(comp_ignorado, hide_index=True, use_container_width=True)
