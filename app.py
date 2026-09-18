import streamlit as st
import pandas as pd
import html
import os
import glob
import calendar
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, datetime
from supabase import create_client, Client
import plotly.express as px
import plotly.graph_objects as go
from projecao_sinistro import projetar_sinistro_mes_atual, projetar_dias_restantes, eh_dia_util
try:
    from severidade import (
        carregar_base_severidade, aplicar_filtros, evolucao_mensal,
        ranking_severidade, identificar_ofensores, calcular_desvios, montar_watchlist,
        comparacao_mensal, resumo_comparativo, alertas_prestador_procedimento,
        identificar_desvios_solicitacao, calcular_media_nacional, vidas_por,
        _casar_colunas, _corrigir_mojibake,
    )
except Exception as _erro_import_severidade:
    # O Streamlit Cloud redige a mensagem de erro padrão — mostramos o traceback
    # completo aqui pra dar pra diagnosticar sem precisar entrar nos logs.
    st.error("Erro ao importar severidade.py — traceback completo abaixo:")
    st.exception(_erro_import_severidade)
    st.stop()
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
/* Tabelas: fonte bem menor, pra caber sem barra de rolagem lateral */
div[data-testid="stDataFrame"] * { font-size: 0.6rem !important; }
/* Tabelas: colunas mais estreitas (menos espaço em branco por célula) */
div[data-testid="stDataFrame"] [data-testid="stTableCellText"] {
    text-align: center !important;
    padding: 0.1rem 0.25rem !important;
    white-space: nowrap !important;
}
div[data-testid="stDataFrame"] [data-testid="stTableRowHeaderCell"] {
    text-align: left !important;
    padding: 0.1rem 0.25rem !important;
}
div[data-testid="stDataFrame"] [data-testid="stHeaderCell"] {
    padding: 0.1rem 0.25rem !important;
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
/* Abas (st.tabs): visual de botão, com o mesmo azul dos botões primários —
   substitui o vermelho/laranja padrão do Streamlit na aba selecionada */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 4px !important;
}
[data-testid="stTabs"] [data-testid="stTab"] {
    background-color: #eef6fb !important;
    border: 1px solid #d6e8f2 !important;
    border-bottom: none !important;
    border-radius: 8px 8px 0 0 !important;
    padding: 0.4rem 0.9rem !important;
}
[data-testid="stTabs"] [data-testid="stTab"] p {
    color: #0d2b3e !important;
}
[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {
    background-color: #87CEEB !important;
    border-color: #87CEEB !important;
}
[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] p {
    color: #0d2b3e !important;
    font-weight: 600 !important;
}
[data-testid="stTabs"] .react-aria-SelectionIndicator {
    background-color: #87CEEB !important;
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
    # "Dias úteis" desconta fim de semana E feriado nacional (fixo ou móvel) — não é mais
    # só "total - fins de semana", porque um feriado em dia de semana (ex.: 07/set) também
    # não conta como dia útil.
    du = sum(1 for d in range(1, total + 1) if eh_dia_util(date(y, m, d)))
    return total, du, dn
def fmt_brl(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
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
def fmt_fase(v):
    # FASE não tem mais uma referência fixa tipo "1,00 = média" — os valores variam bem
    # mais em escala entre grupos (de 0,0001 a vários inteiros), então usa mais casas
    # decimais que o fmt_float2 pra não arredondar grupos pequenos pra "0,00".
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = f"{v:,.4f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")
@st.cache_data(show_spinner=False)
def _carregar_crosswalk_cidade_cluster_temp(pasta="."):
    """
    Cidade -> UF -> Cluster para TODOS os municípios do Brasil (não só os que já têm
    prestador credenciado) — lido direto do mesmo arquivo "cluster*.xlsx" que
    severidade.py já usa pra montar a coluna CLUSTER da base operacional (mesmo glob,
    mesma pasta). Lido aqui de novo, à parte — não mexe em severidade.py — só pra ter
    cidade/UF/cluster mesmo de município que ainda não tem prestador nenhum, o que a
    base operacional (agregado/df_filtrado) não teria como saber sozinha.
    Devolve DataFrame vazio (colunas CIDADE/UF/CLUSTER) se o arquivo não for encontrado
    ou não tiver as colunas esperadas — quem usa trata esse caso com um aviso na tela.
    """
    candidatos = glob.glob(os.path.join(pasta, "cluster*.xlsx"))
    if not candidatos:
        return pd.DataFrame(columns=["CIDADE", "UF", "CLUSTER"])
    try:
        bruto = pd.read_excel(candidatos[0], sheet_name=0)
    except Exception:
        return pd.DataFrame(columns=["CIDADE", "UF", "CLUSTER"])
    mapa = _casar_colunas(bruto.columns, ["UF_MUN", "UF", "NOME DO MUNICÍPIO", "CLUSTER"])
    faltando = [c for c in ("UF", "NOME DO MUNICÍPIO", "CLUSTER") if c not in mapa]
    if faltando:
        return pd.DataFrame(columns=["CIDADE", "UF", "CLUSTER"])
    cw = bruto[[mapa["NOME DO MUNICÍPIO"], mapa["UF"], mapa["CLUSTER"]]].copy()
    cw.columns = ["CIDADE", "UF", "CLUSTER"]
    cw["CIDADE"] = cw["CIDADE"].apply(_corrigir_mojibake)
    cw["CIDADE"] = cw["CIDADE"].astype(str).str.strip()
    cw["UF"] = cw["UF"].astype(str).str.strip().str.upper()
    cw["CLUSTER"] = cw["CLUSTER"].astype(str).str.strip()
    cw = cw.dropna(subset=["CIDADE", "UF"]).drop_duplicates(subset=["CIDADE", "UF"])
    return cw.reset_index(drop=True)
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
def gravar_projetado_mensal(key, valor):
    """Insere/atualiza o Projetado (oficial) de um mês — funciona pra qualquer mês, inclusive
    o mês corrente (sobrepõe a fórmula de projeção) e meses que ainda não têm nenhuma linha
    no histórico (cria a linha, com Real nulo até ser informado). Não mexe no Real."""
    atual = st.session_state.historico_mensal.get(key, {"projetado": None, "real": None})
    try:
        supabase.table("historico_mensal").upsert(
            {"mes_ano": key, "projetado": float(valor), "real": atual["real"]}
        ).execute()
        st.session_state.historico_mensal[key] = {"projetado": float(valor), "real": atual["real"]}
        return True, ""
    except Exception as e:
        return False, str(e)
def limpar_projetado_mensal(key):
    """Remove o Projetado (oficial) de um mês — volta a usar a fórmula de projeção automática
    pra esse mês. Não mexe no Real."""
    atual = st.session_state.historico_mensal.get(key, {"projetado": None, "real": None})
    try:
        supabase.table("historico_mensal").upsert(
            {"mes_ano": key, "projetado": None, "real": atual["real"]}
        ).execute()
        st.session_state.historico_mensal[key] = {"projetado": None, "real": atual["real"]}
        return True, ""
    except Exception as e:
        return False, str(e)
def enviar_email_projecao(view_year, view_month, label_projetado, projecao, acumulado,
                           decorridos, du_total, dias_lancados, total_dias, nota_projecao,
                           variacoes_projetado):
    try:
        remetente = st.secrets["EMAIL_REMETENTE"]
        senha = st.secrets["EMAIL_SENHA_APP"]
        destinatarios = [e.strip() for e in st.secrets["EMAIL_DESTINATARIO"].split(",") if e.strip()]
        smtp_host = st.secrets.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("EMAIL_SMTP_PORT", 587))
    except KeyError as e:
        return False, f"Faltou configurar o segredo {e} em Settings → Secrets do Streamlit Cloud."
    if not destinatarios:
        return False, "EMAIL_DESTINATARIO está vazio nos Secrets."
    titulo_mes = label_mes(mes_key(view_year, view_month))
    linhas = [
        f"<strong>Projeção de Sinistro — {titulo_mes}</strong>",
        "",
        f"{label_projetado}: {fmt_brl(projecao)}",
    ]
    for label_periodo, delta_pct, valor_ref in (variacoes_projetado or []):
        if delta_pct is None or valor_ref is None:
            continue
        direcao = "maior" if delta_pct >= 0 else "menor"
        linhas.append(f"{abs(delta_pct):.1f}% {direcao} que {label_periodo} - {fmt_brl(valor_ref)}")
    linhas.append(f"Valor acumulado: {fmt_brl(acumulado)}")
    linhas.append(f"Dias lançados: {dias_lancados} de {total_dias}")
    linhas.append(f"Dias úteis decorridos / total: {decorridos} / {du_total}")
    if nota_projecao:
        linhas.append(f"Obs.: {nota_projecao}")
    corpo_html = "<br>\n".join(linhas)
    corpo_html = (
        '<div style="font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#1a1a1a;">'
        f"{corpo_html}</div>"
    )
    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = f"Projeção de Sinistro - {titulo_mes}"
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as servidor:
            servidor.starttls()
            servidor.login(remetente, senha)
            servidor.sendmail(remetente, destinatarios, msg.as_string())
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
    return sum(1 for d, v in entradas.items() if eh_dia_util(date(y, m, d)))
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
    c4, c5, c6 = st.columns(3)
    with c4:
        if st.button("Ir para o mês atual", use_container_width=True, disabled=eh_mes_atual_nav):
            st.session_state.view_year, st.session_state.view_month = ANO_HOJE, MES_HOJE
            st.rerun()
    with c5:
        if st.button("🔄 Atualizar dados", use_container_width=True):
            carregar_dados()
            st.rerun()
    with c6:
        if st.button("📧 Enviar e-mail", use_container_width=True):
            st.session_state["_enviar_email_pendente"] = True
    view_year, view_month = st.session_state.view_year, st.session_state.view_month
    total, du_total, dn_total = calendario(view_year, view_month)
    entradas = entradas_do_mes(view_year, view_month, total)
    acumulado = acumulado_de(entradas)
    decorridos = dias_uteis_decorridos_de(view_year, view_month, total, entradas)
    mes_key_atual = mes_key(view_year, view_month)
    eh_mes_atual = (view_year == ANO_HOJE and view_month == MES_HOJE)
    dado_mensal_do_mes_visto = st.session_state.historico_mensal.get(mes_key_atual)
    tem_oficial = dado_mensal_do_mes_visto and dado_mensal_do_mes_visto.get("projetado") is not None
    if tem_oficial:
        # "Projetado oficial" foi cadastrado manualmente pra esse mês — isso sobrepõe a
        # fórmula. Cadastrar o "Real" (usado só na tabela de Histórico mensal) NÃO entra
        # aqui e não afeta esse valor.
        projecao = dado_mensal_do_mes_visto["projetado"]
        label_projetado = "Valor projetado (oficial)"
        nota = f"Projetado oficial informado para {label_mes(mes_key_atual)} (não é recalculado pela soma diária)."
    else:
        # Sem oficial cadastrado — a fórmula de projeção continua valendo mesmo depois que
        # o mês vira/fecha (não trava mais em "só enquanto for o mês corrente do calendário").
        # Pro mês corrente, o corte é o dia de hoje; pra qualquer outro mês (já encerrado ou
        # ainda não iniciado), o corte é o último dia do próprio mês visualizado — a função
        # já busca sozinha o último dia com lançamento real dentro desse limite.
        dia_corte_calc = DIA_HOJE if eh_mes_atual else total
        resultado_sinistro = projetar_sinistro_mes_atual(
            st.session_state.lancamentos,
            st.session_state.historico_mensal,
            view_year, view_month, dia_corte_calc,
            n_meses=2, metodo="razao_soma",
        )
        projecao = resultado_sinistro["sinistro_projetado"]
        label_projetado = "Valor projetado (Sinistro)"
        if resultado_sinistro["projecao_solicitado"] is not None and resultado_sinistro["razao_media_historica"] is not None:
            nota = ""
        else:
            nota = "Dados insuficientes (dias úteis decorridos ou meses fechados com Real) para calcular a projeção do Sinistro."
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
    st.caption("Dias úteis descontam finais de semana e feriados nacionais (fixos e móveis).")
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
    if st.session_state.get("_enviar_email_pendente"):
        st.session_state["_enviar_email_pendente"] = False
        with st.spinner("Enviando e-mail..."):
            variacoes_projetado = [
                (f"{MESES[mes_ant_mes - 1]}/{ano_ant_mes}", delta_proj, proj_mes_anterior),
                (f"{MESES[view_month - 1]} de {view_year - 1}", delta_proj_aa, proj_mesmo_mes_ano_anterior),
            ]
            ok_email, erro_email = enviar_email_projecao(
                view_year, view_month, label_projetado, projecao, acumulado,
                decorridos, du_total, len(entradas), total, nota, variacoes_projetado,
            )
        if ok_email:
            st.success("E-mail enviado com sucesso!")
        else:
            st.error(f"Erro ao enviar e-mail: {erro_email}")
    st.divider()
    st.subheader("Lançamentos do mês")
    linhas = []
    for d in range(1, total + 1):
        finde = eh_fim_de_semana(view_year, view_month, d)
        # Feriado nacional que caiu em dia de semana (não conta como fim de semana, mas
        # também não é dia útil) — sinalizado à parte pra ficar visível na tabela.
        feriado = (not finde) and (not eh_dia_util(date(view_year, view_month, d)))
        wd = DOW_NOMES[date(view_year, view_month, d).weekday()]
        is_hoje = eh_mes_atual and d == DIA_HOJE
        rotulo = (
            f"{wd}{' · fim de semana' if finde else ''}{' · feriado' if feriado else ''}"
            f"{' · hoje' if is_hoje else ''}"
        )
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
        for k in sorted(st.session_state.historico_mensal.keys(), reverse=True):
            dado = st.session_state.historico_mensal[k]
            eh_atual = k >= mes_key(ANO_HOJE, MES_HOJE)
            if eh_atual:
                mes_corrente_label = label_mes(k)
            linhas_mensal.append({
                "Mês": label_mes(k),
                "Projetado": "mês corrente" if eh_atual else fmt_brl(dado["projetado"]),
                "Real": "mês corrente" if eh_atual else fmt_brl(dado["real"]),
            })
        df_mensal_exibir = pd.DataFrame(linhas_mensal)
        if mes_corrente_label:
            st.caption(f"{mes_corrente_label} é o mês corrente — o Real dele é calculado automaticamente.")
        st.dataframe(df_mensal_exibir, hide_index=True, use_container_width=True)
        if is_admin:
            st.markdown("**✏️ Inserir/corrigir Projetado e Real de um mês**")
            st.caption(
                "Projetado e Real são salvos de forma independente — salvar um nunca altera o outro."
            )
            # Lista de meses pra escolher: os que já têm linha no histórico, unidos com uma
            # janela de 12 meses antes/depois do mês atual — assim dá pra inserir um mês que
            # ainda não tem nenhuma linha no banco (ex.: agosto recém-fechado, ou até o mês
            # corrente, pra sobrepor a fórmula de projeção com um Projetado oficial).
            meses_disponiveis = set(st.session_state.historico_mensal.keys())
            for delta in range(-12, 13):
                total_meses = (MES_HOJE - 1) + delta
                y = ANO_HOJE + total_meses // 12
                m = total_meses % 12 + 1
                meses_disponiveis.add(mes_key(y, m))
            labels_edicao = sorted(meses_disponiveis, reverse=True)
            escolha = st.selectbox(
                "Mês", labels_edicao, format_func=label_mes, key="select_mes_editar"
            )
            eh_mes_corrente_edicao = escolha >= mes_key(ANO_HOJE, MES_HOJE)
            dado_escolhido = st.session_state.historico_mensal.get(escolha, {"projetado": None, "real": None})
            col_proj, col_real = st.columns(2)
            with col_proj:
                st.markdown(f"Projetado (oficial) — {label_mes(escolha)}")
                projetado_atual = dado_escolhido["projetado"]
                novo_projetado = st.number_input(
                    "Valor projetado",
                    value=float(projetado_atual) if projetado_atual is not None else 0.0,
                    step=0.01,
                    format="%.2f",
                    key=f"input_projetado_{escolha}",
                    label_visibility="collapsed",
                )
                sub_col1, sub_col2 = st.columns(2)
                with sub_col1:
                    if st.button("Salvar Projetado", key=f"salvar_projetado_{escolha}"):
                        ok, erro = gravar_projetado_mensal(escolha, novo_projetado)
                        if ok:
                            st.success(f"Projetado de {label_mes(escolha)} salvo: {fmt_brl(novo_projetado)}.")
                            st.rerun()
                        else:
                            st.error(f"Erro ao salvar: {erro}")
                with sub_col2:
                    if projetado_atual is not None:
                        if st.button("Remover override", key=f"limpar_projetado_{escolha}"):
                            ok, erro = limpar_projetado_mensal(escolha)
                            if ok:
                                st.success(f"Projetado oficial de {label_mes(escolha)} removido — volta a usar a fórmula.")
                                st.rerun()
                            else:
                                st.error(f"Erro ao remover: {erro}")
            with col_real:
                st.markdown(f"Real — {label_mes(escolha)}")
                if eh_mes_corrente_edicao:
                    st.caption("Não editável pro mês corrente — vem dos lançamentos diários.")
                else:
                    real_atual = dado_escolhido["real"]
                    novo_real = st.number_input(
                        "Valor real",
                        value=float(real_atual) if real_atual is not None else 0.0,
                        step=0.01,
                        format="%.2f",
                        key=f"input_real_{escolha}",
                        label_visibility="collapsed",
                    )
                    if st.button("Salvar Real", key=f"salvar_real_{escolha}"):
                        ok, erro = gravar_real_mensal(escolha, novo_real)
                        if ok:
                            st.success(f"Real de {label_mes(escolha)} salvo: {fmt_brl(novo_real)}.")
                            st.rerun()
                        else:
                            st.error(f"Erro ao salvar: {erro}")
# ============================================================
# PÁGINA: SEVERIDADE
# ============================================================
elif st.session_state.pagina == "severidade":
    # Abas oficiais antigas (Ranking/Evolução mensal/Ofensores/Desvios de Solicitações) e o
    # bloco de Informações Técnicas que as explica ficam ocultos (não apagados) — troque pra
    # True pra reexibir os dois juntos.
    MOSTRAR_ABAS_OFICIAIS_EXTRAS = False
    # Aba "Coeficiente de Severidade" (cobre TODOS os procedimentos, sem a lista fixa de 13
    # códigos) fica oculta, não apagada — troque pra True pra reexibi-la. Com ela oculta, a
    # aba "🧪 Temp: procedimentos selecionados" (Temporária) passa a ser a primeira e ganha
    # os filtros de Mês/Plano/Especialidade que antes só apareciam na Coeficiente de
    # Severidade (ver MOSTRAR_FILTROS_TOPO logo abaixo).
    MOSTRAR_ABA_CS_TEMP = False
    # Quadro "Filtros" do topo da página (Mês/Região/Plano/UF/Especialidade/Cluster/Cidade +
    # volume mínimo) fica oculto — Mês/Plano/Especialidade continuam funcionando do mesmo
    # jeito (mesmo efeito sobre df_filtrado/usuarios_filtrado), só que os campos aparecem
    # agora dentro da aba "🧪 Temp: procedimentos selecionados" (Temporária); Região/UF/
    # Cluster/Cidade da página ficam sem filtro próprio (já têm equivalente dentro das abas
    # de Coeficiente de Severidade/Temporária) e o volume mínimo volta pro padrão antigo
    # (30). Troque pra True pra restaurar o quadro original (os 7 campos + slider) do jeito
    # que era.
    MOSTRAR_FILTROS_TOPO = False
    # Grade "por procedimento" (Qtde proced/Qtd vidas/Soma de uso/Uso.../Cálculo do FASE/FASE/
    # Cálculo do QP/QP/Cálculo do CS/CS/CS Geral/CS da Cidade), que aparece logo antes do bloco
    # "Onde estão as severidades" — fica oculta por padrão, mas volta a aparecer sozinha assim
    # que um prestador específico é selecionado no filtro da aba (ver _mostrar_grade_cs_temp
    # logo antes da chamada que desenha a grade). Deixe True aqui pra forçar ela sempre visível,
    # mesmo sem prestador selecionado.
    MOSTRAR_GRADE_CS_PROCEDIMENTO_TEMP = False
    col_titulo_sev, col_atualizar_sev = st.columns([5, 1])
    with col_titulo_sev:
        st.subheader("🕵️ Severidade")
    with col_atualizar_sev:
        if st.button("🔄 Recarregar", use_container_width=True):
            carregar_base_severidade.clear()
            st.rerun()
    if MOSTRAR_ABAS_OFICIAIS_EXTRAS:
        with st.expander("ℹ️ Informações Técnicas - Aba Severidade"):
            st.markdown(
                "A aba Severidade mede padrão de utilização — não custo.\n\n"
                "**Objetivo:** identificar onde a utilização foge do esperado (especialidade, região, "
                "procedimento ou prestador).\n\n"
                "**A pergunta que a aba responde:** Esse grupo está usando mais do que deveria, e isso é "
                "relevante em volume ou é ruído estatístico de uma amostra pequena?\n\n"
                "---\n\n"
                "**FASE (Fator de Severidade):** é o produto de três componentes, calculado para qualquer "
                "grupo (uma especialidade, uma UF, um procedimento, um prestador...):\n\n"
                "**FASE = Frequência × Intensidade × Peso do grupo**\n\n"
                "- **Frequência:** Procedimentos ÷ Vidas *(quantos procedimentos por paciente distinto)*\n"
                "- **Intensidade:** Procedimentos ÷ Uso *(quantos procedimentos reais acontecem para cada "
                "unidade de 'uso' (peso do procedimento) consumida)*\n"
                "- **Peso do grupo:** (Procedimentos do grupo ÷ Procedimentos totais) × 100 *(relevância do "
                "grupo dentro da base — filtra ruído de amostra pequena)*\n\n"
                "FASE só faz sentido em ranking comparativo: quanto maior, mais severo em relação aos outros "
                "grupos do mesmo filtro (um grupo minúsculo não aparece como severo só por ter uma métrica "
                "bruta alta).\n\n"
                "Um procedimento caro não é, por si só, sinal de má utilização — e um procedimento barato "
                "usado em excesso pode ser um problema maior.\n\n"
                "---\n\n"
                "A lista de prestadores exibida respeita os filtros ativos (UF, especialidade, cidade). Isso "
                "evita comparar um prestador com uma \"média\" que já foi recortada artificialmente pelo "
                "filtro.\n\n"
                "Todas as comparações mês a mês (comparação mensal, resumo, alerta de qtde+valor) usam o "
                "mesmo período do mês nos dois lados: se o mês mais recente só tem dados até o dia 07, o mês "
                "anterior entra na conta também só até o dia 07 — para não comparar um mês fechado inteiro "
                "com um mês ainda em andamento.\n\n"
                "---\n\n"
                "**Volume mínimo de procedimentos para considerar uma variação relevante.**\n\n"
                "Padrão: 30\n"
                "Evita que um grupo com pouquíssimos procedimentos apareça com uma variação % gigante.\n"
                "Ele afeta especificamente dois pontos do painel:\n\n"
                "- **Aba Ofensores**\n"
                "- **Aba Resumo**\n\n"
                "**Não** afeta o Ranking de Severidade (FASE)\n\n"
                "Se colocar 1: Risco: ruído estatístico.\n"
                "**Com 30 (padrão):** um equilíbrio — filtra o ruído de grupos muito pequenos, mas ainda "
                "inclui volume moderado.\n"
                "**Com 100:** Fica mais rigoroso. Reduz falso positivo, mas pode esconder um "
                "desvio real que ainda está com volume moderado.\n"
                "**Com 200:** Bem restritivo — só os maiores grupos aparecem. Bom para focar nos "
                "pode deixar passar despercebido um grupo médio que está crescendo rápido mas ainda não bateu esse "
                "patamar de volume."
            )
    agregado, base_usuarios, aviso_carga = carregar_base_severidade(".")
    if agregado is None:
        st.error(f"Não consegui carregar os dados de severidade: {aviso_carga}")
        st.stop()
    if aviso_carga:
        st.warning(aviso_carga)
    # ---------- filtros ----------
    # Opções sempre calculadas (servem tanto pro quadro original, se reativado, quanto pros
    # campos de Mês/Plano/Especialidade agora dentro da aba Coeficiente de Severidade).
    opcoes_mes_temp = sorted(agregado["MES"].dropna().unique(), reverse=True)
    opcoes_plano_temp = sorted(agregado["NR_PLANO"].dropna().unique())
    opcoes_especialidade_temp = sorted(agregado["ESPECIALIDADE"].dropna().unique())
    # Lidos direto do session_state (e não via widget) porque os campos de Mês/Plano/
    # Especialidade agora só são desenhados (st.multiselect) lá dentro da aba, depois de
    # df_filtrado já ter sido montado aqui — o Streamlit sincroniza o session_state com a
    # última interação do usuário antes do script rodar de novo, então ler pela key já pega
    # o valor atual mesmo antes do widget em si aparecer no código.
    f_mes = st.session_state.get("temp_filtro_mes", [])
    f_plano = st.session_state.get("temp_filtro_plano", [])
    f_especialidade = st.session_state.get("temp_filtro_especialidade", [])
    # Região/UF/Cluster/Cidade da página ficam sem filtro próprio aqui — já têm equivalente
    # dentro da aba Coeficiente de Severidade, que filtra em cima do resultado destes.
    f_regiao, f_uf, f_cluster, f_cidade = [], [], [], []
    volume_minimo = 30
    if MOSTRAR_FILTROS_TOPO:
        with st.container(border=True):
            st.markdown("**Filtros**")
            fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns(7)
            with fc1:
                f_mes = st.multiselect("Mês", options=opcoes_mes_temp)
            with fc2:
                f_regiao = st.multiselect("Região", options=sorted(agregado["REGIAO"].dropna().unique()))
            with fc3:
                f_plano = st.multiselect("Plano", options=opcoes_plano_temp)
            with fc4:
                f_uf = st.multiselect("UF", options=sorted(agregado["UF"].dropna().unique()))
            with fc5:
                f_especialidade = st.multiselect("Especialidade", options=opcoes_especialidade_temp)
            with fc6:
                f_cluster = st.multiselect("Cluster", options=sorted(agregado["CLUSTER"].dropna().unique()))
            with fc7:
                # Cidade filtrada pela(s) UF(s) selecionada(s) acima — sem UF selecionada, mostra
                # todas as cidades. O campo já vem com busca por digitação (padrão do multiselect).
                opcoes_cidade = sorted(
                    (agregado[agregado["UF"].isin(f_uf)] if f_uf else agregado)["CIDADE_PRESTADOR"].dropna().unique()
                )
                if "f_cidade" in st.session_state:
                    st.session_state["f_cidade"] = [c for c in st.session_state["f_cidade"] if c in opcoes_cidade]
                f_cidade = st.multiselect("Cidade", options=opcoes_cidade, key="f_cidade")
            volume_minimo = st.slider(
                "Volume mínimo de procedimentos para considerar uma variação relevante",
                min_value=1, max_value=200, value=30,
            )
    df_filtrado = aplicar_filtros(
        agregado,
        meses=f_mes or None, ufs=f_uf or None, regioes=f_regiao or None,
        especialidades=f_especialidade or None, planos=f_plano or None, clusters=f_cluster or None,
        cidades=f_cidade or None,
    )
    usuarios_filtrado = aplicar_filtros(
        base_usuarios,
        meses=f_mes or None, ufs=f_uf or None, regioes=f_regiao or None,
        especialidades=f_especialidade or None, planos=f_plano or None, clusters=f_cluster or None,
        cidades=f_cidade or None,
    )
    # ---------- período do mês (dia a dia) ----------
    # Filtro de página, vale pra todas as abas (afeta df_filtrado/usuarios_filtrado antes de
    # qualquer aba ler eles) — "Mês completo" não corta nada por dia; "Escolher dias" recorta
    # pelo dia do mês (coluna DIA), útil pra comparar um pedaço específico de um mês em
    # andamento sem esperar ele fechar.
    col_periodo_modo_temp, col_periodo_dias_temp = st.columns([1, 2])
    with col_periodo_modo_temp:
        modo_periodo_temp = st.radio(
            "Período do mês", ["Mês completo", "Escolher dias"],
            horizontal=True, key="periodo_modo_temp",
        )
    if modo_periodo_temp == "Escolher dias":
        with col_periodo_dias_temp:
            dia_ini_temp, dia_fim_temp = st.slider(
                "Intervalo de dias (dia tal ao dia tal)",
                min_value=1, max_value=31, value=(1, 31), key="periodo_dias_temp",
            )
        if "DIA" in df_filtrado.columns:
            df_filtrado = df_filtrado[
                (df_filtrado["DIA"] >= dia_ini_temp) & (df_filtrado["DIA"] <= dia_fim_temp)
            ]
        if "DIA" in usuarios_filtrado.columns:
            usuarios_filtrado = usuarios_filtrado[
                (usuarios_filtrado["DIA"] >= dia_ini_temp) & (usuarios_filtrado["DIA"] <= dia_fim_temp)
            ]
    if df_filtrado.empty:
        st.info("Nenhum dado para esses filtros.")
        st.stop()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Procedimentos", fmt_int(df_filtrado["qtd_procedimentos"].sum()))
    m2.metric("Uso total", fmt_int(df_filtrado["soma_uso"].sum()))
    _uso_total = df_filtrado["soma_uso"].sum()
    _qtd_total = df_filtrado["qtd_procedimentos"].sum()
    _usuarios_total = usuarios_filtrado["CD_USUARIO"].nunique()
    m3.metric("Qtde de vidas", fmt_int(_usuarios_total))
    m4.metric("Uso por procedimento", fmt_float2(_uso_total / _qtd_total) if _qtd_total else "—")
    m5.metric("Uso por vida", fmt_float2(_uso_total / _usuarios_total) if _usuarios_total else "—")
    st.divider()
    # Sequência das abas: Temporária, Resumo, Projeção, SMILE DENTAL — "Coeficiente de
    # Severidade" fica fora da lista (oculta) a menos que MOSTRAR_ABA_CS_TEMP seja religado.
    _labels_abas_temp = [
        "🧪 Temp: procedimentos selecionados", "Resumo", "📍 Projeção de Credenciamento",
        "🔎 SMILE DENTAL",
    ]
    if MOSTRAR_ABA_CS_TEMP:
        _labels_abas_temp.append("Coeficiente de Severidade")
    if MOSTRAR_ABAS_OFICIAIS_EXTRAS:
        _labels_abas_temp += ["Ranking de Severidade", "Evolução mensal", "Ofensores", "Desvios de Solicitações"]
    _abas_criadas_temp = st.tabs(_labels_abas_temp)
    tab_temp_legado, tab_resumo, tab_credenciamento, tab_smile_temp = (
        _abas_criadas_temp[0], _abas_criadas_temp[1], _abas_criadas_temp[2], _abas_criadas_temp[3]
    )
    _prox_idx_aba_temp = 4
    if MOSTRAR_ABA_CS_TEMP:
        tab_temp = _abas_criadas_temp[_prox_idx_aba_temp]
        _prox_idx_aba_temp += 1
    if MOSTRAR_ABAS_OFICIAIS_EXTRAS:
        tab_rank, tab_evolucao, tab_ofensores, tab_desvios = (
            _abas_criadas_temp[_prox_idx_aba_temp], _abas_criadas_temp[_prox_idx_aba_temp + 1],
            _abas_criadas_temp[_prox_idx_aba_temp + 2], _abas_criadas_temp[_prox_idx_aba_temp + 3],
        )
    # Lista de códigos original da aba temporária, de antes dela ter virado "Coeficiente de
    # Severidade" (que hoje cobre todos os procedimentos) — volta como uma aba própria, sem
    # tirar a de todos os procedimentos, com a mesma lista fixa de 13 códigos de origem.
    CODIGOS_TEMP_LEGADO = [
        9040, 110, 2035, 5314, 4500, 1064, 4425,
        330, 550, 3015, 2025, 9010, 9030,
    ]
    # Nome do prestador que a aba "🔎 SMILE DENTAL" trava por padrão no filtro Prestador —
    # investigação pontual de volume/CS estranho nos procedimentos 550/110/100/510 dessa
    # clínica. Comparado por substring (maiúsculas, sem espaço nas pontas) contra as opções
    # de prestador dos filtros atuais, então tolera pequenas diferenças de acentuação/sufixo.
    NOME_PRESTADOR_SMILE_TEMP = "SMILE DENTAL CLINICA ODONTOLOGICA LTDA ME"
    # (tab_obj, título exibido, lista de códigos que restringe a aba — None = todos os
    # procedimentos, sufixo pra deixar as keys dos widgets únicas por aba, nome do prestador
    # travado por padrão no filtro Prestador dessa aba — None = sem trava, nenhum, mostra as
    # colunas Cálculo do QP/QP — True mostra, False esconde) — o corpo da aba (logo abaixo)
    # roda uma vez por item desta lista, reaproveitando o mesmo código pra todas.
    _config_abas_cs_temp = [
        (tab_temp_legado, "🧪 Temp: procedimentos selecionados", CODIGOS_TEMP_LEGADO, "_legado", None, True),
        (tab_smile_temp, "🔎 SMILE DENTAL", None, "_smile", NOME_PRESTADOR_SMILE_TEMP, False),
    ]
    if MOSTRAR_ABA_CS_TEMP:
        _config_abas_cs_temp.append((tab_temp, "Coeficiente de Severidade", None, "", None, True))
    if MOSTRAR_ABAS_OFICIAIS_EXTRAS:
        # ---------- RANKING DE SEVERIDADE (FASE — só gráficos, sem tabelas) ----------
        JANELA_5_BARRAS = 300  # altura fixa (px) que mostra ~5 barras; o resto rola dentro do quadro
        def _grafico_severidade(df_rank, coluna, titulo, altura=None, janela=None):
            df_plot = df_rank.sort_values("fase", ascending=True).reset_index(drop=True)
            if janela:
                # altura total cresce com a quantidade de itens (barra do mesmo tamanho sempre),
                # o quadro em volta é que fica fixo em `janela` e ganha rolagem quando sobra.
                altura_total = max(janela, 90 + len(df_plot) * 40)
            else:
                altura_total = altura or max(350, len(df_plot) * 35)
            fig = px.bar(
                df_plot, x="fase", y=coluna, orientation="h",
                custom_data=[coluna, "fase", "uso_por_procedimento", "uso_por_vida", "qtd_usuarios"],
                title=titulo,
                color="fase",
                color_continuous_scale=["#2ecc71", "#f1c40f", "#e74c3c"],
            )
            fig.update_traces(
                texttemplate="%{x:,.4f}",
                textposition="outside",
                textfont=dict(size=10),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "FASE: %{customdata[1]:,.4f}<br>"
                    "Uso por procedimento: %{customdata[2]:.2f}<br>"
                    "Uso por vida: %{customdata[3]:.2f}<br>"
                    "Qtde de vidas: %{customdata[4]:,.0f}"
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
            fig.update_yaxes(tickfont=dict(size=10))
            if janela:
                with st.container(height=janela):
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.plotly_chart(fig, use_container_width=True)
        with tab_rank:
            st.info(
                "O **FASE (Fator de Severidade)** é o produto de três indicadores do grupo "
                "(especialidade, UF, procedimento, região ou prestador):\n\n"
                "- **Frequência** = procedimentos ÷ vidas\n"
                "- **Intensidade** = procedimentos ÷ uso\n"
                "- **Peso do grupo** = (procedimentos do grupo ÷ procedimentos totais da base) × 100\n\n"
                "**FASE = Frequência × Intensidade × Peso do grupo**\n\n"
                "Não existe um valor fixo de referência (não é mais '1,00 = média') — o número só "
                "faz sentido comparando um grupo com o outro no mesmo ranking: quanto maior o FASE, "
                "mais severo. Grupos de volume muito baixo têm o Peso do grupo pequeno, o que já os "
                "afasta do topo do ranking mesmo que a frequência/intensidade bruta deles seja alta. "
                "Não considera valores em R$."
            )
            rc1, rc2 = st.columns(2)
            with rc1:
                _grafico_severidade(ranking_severidade(df_filtrado, "ESPECIALIDADE", top_n=40, usuarios=usuarios_filtrado), "ESPECIALIDADE", "Por especialidade", janela=JANELA_5_BARRAS)
                _grafico_severidade(ranking_severidade(df_filtrado, "UF", top_n=30, usuarios=usuarios_filtrado), "UF", "Por UF", janela=JANELA_5_BARRAS)
            with rc2:
                _grafico_severidade(ranking_severidade(df_filtrado, "NOME_PROCEDIMENTO", top_n=50, usuarios=usuarios_filtrado), "NOME_PROCEDIMENTO", "Por procedimento", janela=JANELA_5_BARRAS)
                _grafico_severidade(ranking_severidade(df_filtrado, "REGIAO", usuarios=usuarios_filtrado), "REGIAO", "Por região", janela=JANELA_5_BARRAS)
            st.divider()
            st.markdown("#### Severidade por outras dimensões")
            dims = {
                "Região": "REGIAO", "Cidade": "CIDADE_PRESTADOR", "Prestador (código)": "CD_PRESTADOR",
                "Procedimento": "NOME_PROCEDIMENTO", "Cluster": "CLUSTER",
            }
            dim_escolhida = st.selectbox("Dimensão", list(dims.keys()))
            rank_sev = ranking_severidade(df_filtrado, dims[dim_escolhida], usuarios=usuarios_filtrado)
            if not rank_sev.empty:
                _grafico_severidade(rank_sev, dims[dim_escolhida], f"Severidade por {dim_escolhida}", altura=450)
            else:
                st.info("Sem dados para a dimensão selecionada.")
        with tab_evolucao:
            evolucao = evolucao_mensal(df_filtrado, usuarios_filtrado)
            # Dois gráficos lado a lado: à esquerda, uso por procedimento e uso por vida
            # (mesma escala, dá pra comparar as duas linhas juntas); à direita, procedimento
            # por vida (frequência) sozinho — a escala dele é bem menor (perto de 1) e ficaria
            # achatado se dividisse o mesmo eixo com as métricas de uso.
            col_uso, col_proc_vida = st.columns(2)
            with col_uso:
                fig_uso = go.Figure()
                fig_uso.add_trace(
                    go.Scatter(x=evolucao["MES"], y=evolucao["uso_por_procedimento"], mode="lines+markers",
                               name="Uso por procedimento", line=dict(color="#1f6fb2"))
                )
                fig_uso.add_trace(
                    go.Scatter(x=evolucao["MES"], y=evolucao["uso_por_vida"], mode="lines+markers",
                               name="Uso por vida", line=dict(color="#87CEEB"))
                )
                fig_uso.update_layout(
                    title="Uso por procedimento e uso por vida",
                    height=350, margin=dict(l=10, r=10, t=40, b=10), legend_title_text="",
                    yaxis_title="Uso",
                )
                st.plotly_chart(fig_uso, use_container_width=True)
            with col_proc_vida:
                fig_proc_vida = px.line(
                    evolucao, x="MES", y="procedimento_por_vida", markers=True, text="procedimento_por_vida",
                    title="Procedimento por vida",
                )
                fig_proc_vida.update_traces(
                    texttemplate="%{text:,.3f}", textposition="top center",
                    line=dict(color="#e07b39"),
                )
                fig_proc_vida.update_layout(
                    height=350, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="Procedimento por vida",
                )
                st.plotly_chart(fig_proc_vida, use_container_width=True)
            fig_isr = px.line(
                evolucao, x="MES", y="fase", markers=True, text="fase", title="FASE por mês",
            )
            fig_isr.update_traces(texttemplate="%{text:,.4f}", textposition="top center")
            fig_isr.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="FASE")
            st.plotly_chart(fig_isr, use_container_width=True)
            fig_uso_total = px.line(evolucao, x="MES", y="quantidade_uso", markers=True, text="quantidade_uso", title="Uso total por mês")
            fig_uso_total.update_traces(texttemplate="%{text:,.0f}", textposition="top center")
            fig_uso_total.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_uso_total, use_container_width=True)
        # ---------- OFENSORES (baseado só em volume e uso) ----------
        with tab_ofensores:
            st.markdown("#### 🚨 Prestadores ofensores")
            st.caption(
                "Calculado por **prestador + especialidade** (não mistura as especialidades de um "
                "mesmo prestador numa conta só). Um prestador+especialidade é marcado como **ofensor** "
                "quando bate em **≥ 2 de 3 critérios**, todos no top 5% (percentil 95) da base filtrada: "
                "volume de procedimentos, uso por procedimento e uso por vida."
            )
            with st.expander("📖 Como ler as colunas criterios_atingidos, relevante e justificativa"):
                st.markdown(
                    "- 📊 **criterios_atingidos** = quantos dos 3 critérios acima foram batidos (0 a 3)."
                    "\n"
                    "- 🚨 **relevante** é marcado quando **criterios_atingidos ≥ 2** — "
                    "é o flag que marca o prestador+especialidade como ofensor de fato."
                    "\n"
                    "- 📝 **justificativa** = texto explicando **exatamente quais critérios** "
                    "foram acionados e quais os valores/limiares correspondentes."
                )
            ofensores = identificar_ofensores(df_filtrado, usuarios=usuarios_filtrado)
            if not ofensores.empty:
                # Formatar tabela para exibição — já vem ordenada do mais para o menos severo (FASE)
                exib_of = ofensores.copy()
                exib_of["qtd_procedimentos"] = exib_of["qtd_procedimentos"].map(fmt_int)
                exib_of["qtd_usuarios"] = exib_of["qtd_usuarios"].map(fmt_int)
                exib_of["quantidade_uso"] = exib_of["quantidade_uso"].map(fmt_int)
                exib_of["uso_por_procedimento"] = exib_of["uso_por_procedimento"].map(fmt_float2)
                exib_of["uso_por_vida"] = exib_of["uso_por_vida"].map(fmt_float2)
                exib_of["fase"] = exib_of["fase"].map(fmt_fase)
                exib_of["criterios_atingidos"] = exib_of["criterios_atingidos"].map(lambda v: f"{v}/3")
                exib_of["relevante"] = exib_of["relevante"].map(lambda b: "🚨 OFENSOR" if b else "—")
                exib_of = exib_of.drop(columns=["alerta_volume", "alerta_uso_procedimento", "alerta_uso_vida"], errors="ignore")
                # Nomes de coluna mais curtos, só nessa grade, pra ficar mais fácil de visualizar
                exib_of = exib_of.rename(columns={
                    "qtd_procedimentos": "qtd_proced",
                    "qtd_usuarios": "qtd_usu",
                    "quantidade_uso": "qtde_USO",
                    "uso_por_procedimento": "USO/proced",
                    "uso_por_vida": "USO/vidas",
                    "fase": "FASE",
                })
                st.dataframe(exib_of, hide_index=True, use_container_width=True)
                # Destaque para ofensores relevantes com justificativa — retrátil e pesquisável
                relevantes = ofensores[ofensores["relevante"]].copy()
                if not relevantes.empty:
                    st.divider()
                    # A lista inteira fica retrátil (expander). Streamlit não permite expander
                    # dentro de expander, então cada ofensor vira um container com borda em vez
                    # de um expander individual.
                    with st.expander(f"📝 Justificativa dos ofensores ({len(relevantes)})", expanded=False):
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
                            titulo_exp = f"Prestador {int(row['CD_PRESTADOR'])} — {nome_prestador} · FASE {row['fase']:.4f}"
                            with st.container(border=True):
                                st.markdown(f"**{titulo_exp}**")
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
            desvios = calcular_desvios(df_filtrado, usuarios=usuarios_filtrado)
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
            comp, msg_comp = comparacao_mensal(df_filtrado, "NOME_PROCEDIMENTO", volume_minimo=volume_minimo, usuarios=usuarios_filtrado)
            st.caption(msg_comp)
            if not comp.empty:
                comp_relevante = comp[comp["relevante"]].drop(columns=["relevante"])
                comp_ignorado = comp[~comp["relevante"]].drop(columns=["relevante"])
                st.markdown(f"*Variações relevantes (volume atual ≥ {volume_minimo}):*")
                st.dataframe(comp_relevante, hide_index=True, use_container_width=True)
                with st.expander(f"Ver também as {len(comp_ignorado)} variações abaixo do volume mínimo"):
                    st.dataframe(comp_ignorado, hide_index=True, use_container_width=True)
            st.divider()
            st.markdown("#### 🎯 Prestadores que merecem atenção")
            watchlist = montar_watchlist(df_filtrado, usuarios=usuarios_filtrado)
            if not watchlist.empty:
                # Preparar DataFrame para o gráfico — garantir tipos corretos
                wl_plot = watchlist.copy()
                for col in ["NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER"]:
                    if col not in wl_plot.columns:
                        wl_plot[col] = "—"
                    wl_plot[col] = wl_plot[col].fillna("—").astype(str)
                # Rótulo do eixo Y — dois prestadores (CD_PRESTADOR diferentes, ex.: unidades/CNPJs
                # distintos da mesma rede) podem ter o mesmo NOME_PRESTADOR. Usar só o nome faria o
                # Plotly empilhar as barras deles na mesma categoria (barra mais comprida que
                # qualquer um dos dois valores individuais). Desambigua com o CNPJ/CPF só quando
                # o nome se repete.
                wl_plot["rotulo_grafico"] = wl_plot["NOME_PRESTADOR"]
                duplicados = wl_plot["NOME_PRESTADOR"].duplicated(keep=False)
                if duplicados.any():
                    wl_plot.loc[duplicados, "rotulo_grafico"] = (
                        wl_plot.loc[duplicados, "NOME_PRESTADOR"]
                        + " (CNPJ/CPF " + wl_plot.loc[duplicados, "CNPJ_CPF_PRESTADOR"] + ")"
                    )
                fig_watch = px.bar(
                    wl_plot.sort_values("fase", ascending=True), x="fase",
                    y="rotulo_grafico", orientation="h",
                    text="fase", title="Prestadores que merecem atenção",
                    custom_data=["CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER"],
                )
                fig_watch.update_traces(
                    texttemplate="%{text:,.4f}",
                    textposition="outside",
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "FASE: %{x:,.4f}<br>"
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
                exib_watch["fase"] = exib_watch["fase"].map(fmt_fase)
                exib_watch["evolucao_pct"] = exib_watch["evolucao_pct"].map(lambda v: f"{v:+.1f}%")
                # Nomes de coluna mais curtos, só nessa grade, pra ficar mais fácil de visualizar
                exib_watch = exib_watch.rename(columns={
                    "qtd_procedimentos": "qtd_proced",
                    "qtd_usuarios": "qtd_usu",
                    "quantidade_uso": "qtde_USO",
                    "uso_por_procedimento": "USO/proced",
                    "uso_por_vida": "USO/vidas",
                    "fase": "FASE",
                    "evolucao_pct": "Evolução",
                })
                st.dataframe(exib_watch, hide_index=True, use_container_width=True)
            else:
                st.info("Sem dados para montar a watchlist.")
        # ---------- DESVIOS DE SOLICITAÇÕES (qtde do prestador vs. média nacional) ----------
        with tab_desvios:
            st.markdown("#### 📐 Desvios de Solicitações")
            st.caption(
                "Compara a quantidade de solicitações de cada prestador, por procedimento e por mês, "
                "com a média nacional de solicitações por prestador para aquele mesmo procedimento "
                "naquele mesmo mês (soma nacional ÷ nº de prestadores que fizeram o procedimento)."
            )
            with st.expander("📖 Critérios considerados", expanded=True):
                st.markdown(
                    "Um prestador só entra na lista quando **as duas condições** abaixo são verdadeiras "
                    "ao mesmo tempo:\n"
                    "- **Volume**: mais de **30 procedimentos no mês**, para aquele procedimento específico.\n"
                    "- **Desvio**: quantidade **pelo menos 50% acima** da média nacional de solicitações "
                    "por prestador para aquele procedimento, naquele mês.\n\n"
                    "**Exemplo:** 1.000 solicitações de um procedimento, feitas por 100 prestadores "
                    "diferentes → média nacional = 10 por prestador. Um prestador que solicitou 250 "
                    "está bem acima da média — entra na lista.\n\n"
                    "A média nacional é sempre calculada sobre a base nacional completa (sem os filtros "
                    "da tela) — só a lista de prestadores respeita os filtros ativos (UF, especialidade, "
                    "cidade etc.), pra facilitar a exploração."
                )
            opcoes_procedimento_desvio = sorted(df_filtrado["NOME_PROCEDIMENTO"].dropna().unique())
            procedimento_desvio = st.selectbox(
                "Procedimento",
                options=["(Todos os procedimentos)"] + opcoes_procedimento_desvio,
                key="desvio_procedimento",
            )
            filtro_procedimento_desvio = None if procedimento_desvio == "(Todos os procedimentos)" else procedimento_desvio
            desvios_sol, msg_desvios_sol = identificar_desvios_solicitacao(
                df_filtrado, agregado_nacional=agregado, procedimento=filtro_procedimento_desvio
            )
            if desvios_sol.empty:
                st.info(msg_desvios_sol)
            else:
                st.caption(f"{len(desvios_sol)} prestador(es) com desvio de solicitações identificados.")
                exib_desv_sol = desvios_sol.copy()
                exib_desv_sol["MES"] = exib_desv_sol["MES"].map(label_mes)
                for c in ["NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER"]:
                    if c not in exib_desv_sol.columns:
                        exib_desv_sol[c] = "—"
                    exib_desv_sol[c] = exib_desv_sol[c].fillna("—")
                exib_desv_sol["qtd_procedimentos"] = exib_desv_sol["qtd_procedimentos"].map(fmt_int)
                exib_desv_sol["media_nacional"] = exib_desv_sol["media_nacional"].map(fmt_float2)
                exib_desv_sol["desvio_pct"] = exib_desv_sol["desvio_pct"].map(lambda v: f"+{v:.1f}%")
                colunas_ordem = [
                    "MES", "NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER",
                    "ESPECIALIDADE", "NOME_PROCEDIMENTO", "media_nacional", "qtd_procedimentos", "desvio_pct",
                ]
                colunas_ordem = [c for c in colunas_ordem if c in exib_desv_sol.columns]
                exib_desv_sol = exib_desv_sol[colunas_ordem].rename(columns={
                    "MES": "Mês", "NOME_PRESTADOR": "Prestador", "CNPJ_CPF_PRESTADOR": "CPF/CNPJ",
                    "ESPECIALIDADE": "Especialidade", "NOME_PROCEDIMENTO": "Procedimento",
                    "media_nacional": "Média nacional", "qtd_procedimentos": "Qtde do prestador",
                    "desvio_pct": "Desvio",
                })
                st.dataframe(exib_desv_sol, hide_index=True, use_container_width=True)
    # ---------- RESUMO (mês vs. mês anterior, por variação % de uso) ----------
    with tab_resumo:
        st.markdown("#### 📌 Resumo do mês vs. mês anterior")
        st.caption(
            "Compara o último mês com o anterior pela **variação % de uso** (não em números "
            "absolutos). Clique num item abaixo para expandir e ver o que causou o aumento. "
            f"Só entram grupos com volume ≥ {volume_minimo} procedimentos em ambos os meses "
            "(ajustável no filtro acima)."
        )
        resumo, msg_resumo = resumo_comparativo(df_filtrado, volume_minimo=volume_minimo, usuarios=usuarios_filtrado)
        if resumo is None:
            st.info(msg_resumo)
        else:
            st.caption(msg_resumo)

            def _fmt_pct(v):
                return f"{v:+.1f}%" if pd.notna(v) else "—"

            def _linha_resumo(row):
                """Grade de 1 linha com o resumo (uso e vidas) do item expandido — especialidade ou UF."""
                dados = {
                    "Soma uso atual": [fmt_int(row.get("soma_uso_atual"))],
                    "Soma uso anterior": [fmt_int(row.get("soma_uso_anterior"))],
                    "Variação uso": [_fmt_pct(row.get("variacao_pct"))],
                    "Qtde de vidas atual": [fmt_int(row.get("qtd_usuarios_atual"))],
                    "Qtde de vidas anterior": [fmt_int(row.get("qtd_usuarios_anterior"))],
                    "Variação de vidas": [_fmt_pct(row.get("variacao_vidas_pct"))],
                }
                st.dataframe(pd.DataFrame(dados), hide_index=True, use_container_width=True)

            def _tabela_detalhe(det, coluna_chave, label_chave, extra_cols=None):
                """
                Grade de detalhe (procedimentos dentro de uma especialidade, cidades dentro
                de uma UF etc.). extra_cols: lista de (coluna, rótulo) inseridas logo após
                a coluna-chave (ex.: Cluster ao lado de Cidade).
                """
                if det is None or det.empty:
                    return
                colunas_ordem = [coluna_chave]
                renome = {coluna_chave: label_chave}
                if extra_cols:
                    for col, label in extra_cols:
                        colunas_ordem.append(col)
                        renome[col] = label
                colunas_ordem += [
                    "soma_uso_atual", "soma_uso_anterior", "variacao_pct",
                    "qtd_usuarios_atual", "qtd_usuarios_anterior", "variacao_vidas_pct",
                ]
                renome.update({
                    "soma_uso_atual": "Soma uso atual",
                    "soma_uso_anterior": "Soma uso anterior",
                    "variacao_pct": "Variação uso",
                    "qtd_usuarios_atual": "Qtde de vidas atual",
                    "qtd_usuarios_anterior": "Qtde de vidas anterior",
                    "variacao_vidas_pct": "Variação de vidas",
                })
                colunas_ordem = [c for c in colunas_ordem if c in det.columns]
                det_show = det[colunas_ordem].copy()
                det_show["variacao_pct"] = det_show["variacao_pct"].map(_fmt_pct)
                if "variacao_vidas_pct" in det_show.columns:
                    det_show["variacao_vidas_pct"] = det_show["variacao_vidas_pct"].map(_fmt_pct)
                for c in ["soma_uso_atual", "soma_uso_anterior", "qtd_usuarios_atual", "qtd_usuarios_anterior"]:
                    if c in det_show.columns:
                        det_show[c] = det_show[c].map(fmt_int)
                det_show = det_show.rename(columns=renome)
                st.dataframe(det_show, hide_index=True, use_container_width=True)

            # Repetido perto de cada lista (não só no topo da aba) e usado pro aviso de item
            # negativo: essas listas são sempre "top N por variação" — se não existirem N grupos
            # realmente subindo, a lista completa a cota com quem caiu menos, ainda assim rotulado
            # "maior aumento". O sinal (+/-) de cada variação mostra a diferença.
            _aviso_periodo_resumo = (
                "📅 Comparação sempre no mesmo período em ambos os meses (detalhe completo no "
                "topo desta aba)."
            )

            def _rotulo_variacao(v):
                if pd.isna(v):
                    return "Variação de uso: —"
                aviso = "⚠️ caiu, não subiu — " if v < 0 else ""
                return f"{aviso}Variação de uso: {v:+.1f}%"

            # ---------- Especialidades ----------
            especialidades = resumo["especialidades"]
            if especialidades.empty:
                st.markdown("##### 5 especialidades com maior aumento")
                st.info("Nenhuma especialidade com volume suficiente nos dois meses para comparar.")
            else:
                st.caption(_aviso_periodo_resumo)
                if (especialidades["variacao_pct"] < 0).any():
                    st.warning(
                        "Nem todas as 5 abaixo tiveram alta de verdade — como faltaram "
                        "especialidades subindo o suficiente pra completar a lista, ela trouxe "
                        "também quem caiu menos (marcado com ⚠️ abaixo)."
                    )
                with st.expander("5 especialidades com maior aumento", expanded=False):
                    for _, row in especialidades.iterrows():
                        titulo = f"{row['ESPECIALIDADE']} · {_rotulo_variacao(row['variacao_pct'])}"
                        with st.container(border=True):
                            st.markdown(f"**{titulo}**")
                            _linha_resumo(row)
                            det = resumo["detalhes_especialidade"].get(row["ESPECIALIDADE"])
                            if det is not None and not det.empty:
                                st.markdown("**Procedimentos que causaram o aumento:**")
                                _tabela_detalhe(det, "NOME_PROCEDIMENTO", "Procedimento")
        st.divider()
        if resumo is not None:
            # ---------- UFs ----------
            ufs = resumo["ufs"]
            if ufs.empty:
                st.markdown("##### 10 UFs com maior aumento")
                st.info("Nenhuma UF com volume suficiente nos dois meses para comparar.")
            else:
                st.caption(_aviso_periodo_resumo)
                if (ufs["variacao_pct"] < 0).any():
                    st.warning(
                        "Nem todas as 10 abaixo tiveram alta de verdade — como faltaram UFs "
                        "subindo o suficiente pra completar a lista, ela trouxe também quem caiu "
                        "menos (marcado com ⚠️ abaixo)."
                    )
                with st.expander("10 UFs com maior aumento", expanded=False):
                    for _, row in ufs.iterrows():
                        titulo = f"{row['UF']} · {_rotulo_variacao(row['variacao_pct'])}"
                        with st.container(border=True):
                            st.markdown(f"**{titulo}**")
                            _linha_resumo(row)
                            det = resumo["detalhes_uf"].get(row["UF"])
                            if det is not None and not det.empty:
                                st.markdown("**Cidades (com cluster) que causaram o aumento:**")
                                _tabela_detalhe(det, "CIDADE_PRESTADOR", "Cidade", extra_cols=[("CLUSTER", "Cluster")])
        st.divider()
        if resumo is not None:
            # ---------- Prestadores ----------
            prestadores = resumo["prestadores"]
            if prestadores.empty:
                st.markdown("##### 20 prestadores com maior aumento")
                st.info("Nenhum prestador com volume suficiente nos dois meses para comparar.")
            else:
                st.caption(_aviso_periodo_resumo)
                if (prestadores["variacao_pct"] < 0).any():
                    st.warning(
                        "Nem todos os 20 abaixo tiveram alta de verdade — como faltaram "
                        "prestadores subindo o suficiente pra completar a lista, ela trouxe "
                        "também quem caiu menos (marcado com ⚠️ abaixo)."
                    )
                with st.expander("20 prestadores com maior aumento", expanded=False):
                    for _, row in prestadores.iterrows():
                        nome = row.get("NOME_PRESTADOR") or f"Prestador {int(row['CD_PRESTADOR'])}"
                        st.markdown(
                            f"- **{nome}** — CPF/CNPJ: {row.get('CNPJ_CPF_PRESTADOR') or '—'} · "
                            f"{row.get('UF') or '—'} · {row.get('CIDADE') or '—'} · Cluster: {row.get('CLUSTER') or '—'} · "
                            f"Especialidade principal: {row.get('ESPECIALIDADE') or '—'} · "
                            f"{_rotulo_variacao(row['variacao_pct'])}"
                        )
        st.divider()
        # ---------- Alerta: prestador + procedimento com aumento relevante de qtde e valor ----------
        with st.expander("🚨 Prestadores com aumento relevante de quantidade e valor", expanded=False):
            st.caption(
                "Critério (as 5 condições precisam valer juntas): qtde do procedimento no mês atual "
                "> 50, aumento de valor pago > R$ 1.500,00 em relação ao mês anterior, variação de "
                "pelo menos 50% tanto na qtde quanto no valor, e variação do FASE de pelo menos 50% "
                "entre os dois meses. Qtde e valor usam números absolutos (qtde de guias e R$ pago) — "
                "o FASE é calculado no mesmo recorte (prestador + especialidade + procedimento), um "
                "valor por mês."
            )
            alertas, msg_alertas = alertas_prestador_procedimento(df_filtrado, usuarios=usuarios_filtrado)
            if alertas is None or alertas.empty:
                st.info(msg_alertas)
            else:
                st.caption(msg_alertas)
                mes_anterior_lbl = label_mes(alertas["MES_ANTERIOR"].iloc[0])
                mes_atual_lbl = label_mes(alertas["MES_ATUAL"].iloc[0])
                for cd_prestador, grupo in alertas.groupby("CD_PRESTADOR", sort=False):
                    r0 = grupo.iloc[0]
                    nome = r0.get("NOME_PRESTADOR") or f"Prestador {int(cd_prestador)}"
                    cabecalho = (
                        f"{nome} — {r0.get('CIDADE') or '—'}/{r0.get('UF') or '—'} · "
                        f"CPF/CNPJ: {r0.get('CNPJ_CPF_PRESTADOR') or '—'} · Cluster: {r0.get('CLUSTER') or '—'}"
                    )
                    with st.container(border=True):
                        st.markdown(f"**{cabecalho}**")
                        for _, row in grupo.iterrows():
                            texto = (
                                f"**{nome}** ({row.get('CIDADE') or '—'}, CPF/CNPJ {row.get('CNPJ_CPF_PRESTADOR') or '—'}, "
                                f"cluster {row.get('CLUSTER') or '—'}) teve aumento de **{row['variacao_qtd_pct']:+.0f}%** "
                                f"na quantidade em relação a {mes_anterior_lbl}. Esse aumento aconteceu na especialidade "
                                f"**{row['ESPECIALIDADE']}**, no procedimento **{row['NOME_PROCEDIMENTO']}**, que foi de "
                                f"{fmt_int(row['qtd_anterior'])} para {fmt_int(row['qtd_atual'])} solicitações. "
                                f"Em termos de valores, em {mes_anterior_lbl} foi {fmt_brl(row['valor_anterior'])} e em "
                                f"{mes_atual_lbl} foi de {fmt_brl(row['valor_atual'])}, um aumento de "
                                f"**{fmt_brl(row['delta_valor'])}**, que representa **{row['variacao_valor_pct']:+.0f}%**."
                            )
                            if pd.notna(row.get("variacao_usuarios_pct")):
                                texto += (
                                    f" Em termos de vidas, em {mes_anterior_lbl} foram {fmt_int(row['usuarios_anterior'])} "
                                    f"e em {mes_atual_lbl} foram {fmt_int(row['usuarios_atual'])}, uma variação de "
                                    f"**{row['variacao_usuarios_pct']:+.0f}%**."
                                )
                            else:
                                texto += (
                                    f" Em termos de vidas, em {mes_anterior_lbl} foram {fmt_int(row['usuarios_anterior'])} "
                                    f"e em {mes_atual_lbl} foram {fmt_int(row['usuarios_atual'])}."
                                )
                            if pd.notna(row.get("fase_anterior")) and pd.notna(row.get("fase_atual")):
                                if row["fase_atual"] < 0.009:
                                    texto += " Sem variação relevante no FASE."
                                else:
                                    texto += (
                                        f" O FASE em {mes_anterior_lbl} foi {fmt_fase(row['fase_anterior'])} e em "
                                        f"{mes_atual_lbl} foi {fmt_fase(row['fase_atual'])}, com variação de "
                                        f"**{row['variacao_fase_pct']:+.0f}%**."
                                    )
                            st.markdown(texto)
    # ============================================================
    # PROJEÇÃO DE CREDENCIAMENTO — escolhe UF + Cidade (mesmo sem nenhum prestador lá
    # ainda) e projeta CS Ideal/Meta e valor unitário projetado. Procedimento sem nenhum
    # prestador na cidade escolhida fica sem essas informações (aparece "—") — nada de
    # herdar a referência do Cluster nesse caso.
    # ============================================================
    with tab_credenciamento:
        st.markdown("#### 📍 Projeção de Credenciamento")
        st.caption(
            "Escolha a UF e a cidade onde quer credenciar um prestador (mesmo que ainda não "
            "tenha nenhum lá) e clique em **Projetar**. As definições usadas aqui:  \n"
            "**CS Ideal** = o menor CS já praticado por um prestador do mesmo Cluster, "
            "naquele procedimento — a melhor referência real observada.  \n"
            "**CS Meta** = CS Ideal × 0,80 (20% abaixo do Ideal).  \n"
            "**CMP** (Custo Médio Praticado) = valor total pago no procedimento ÷ qtde de "
            "procedimentos, na própria cidade escolhida.  \n"
            "**Valor unit. projetado** = (CMP + menor valor já praticado no Cluster) ÷ 2.  \n"
            "**CS praticado** = o CS já observado na própria cidade escolhida.  \n"
            "Quando a cidade ainda não tiver nenhum prestador para aquele procedimento "
            "(Prestadores na cidade = 0), CS praticado, CS Ideal, CS Meta e Valor unit. "
            "projetado aparecem como **—** — sem herdar a referência do Cluster."
        )

        _crosswalk_cred_temp = _carregar_crosswalk_cidade_cluster_temp(".")
        if _crosswalk_cred_temp.empty:
            st.warning(
                "Não encontrei o arquivo de cluster (cluster*.xlsx) nesta pasta — sem ele não "
                "dá pra saber o Cluster de cidades que ainda não têm prestador."
            )
        else:
            _ufs_cred_temp = sorted(_crosswalk_cred_temp["UF"].dropna().unique())
            cred_col1, cred_col2, cred_col3 = st.columns([1, 2, 1])
            with cred_col1:
                uf_cred_temp = st.selectbox("UF", options=_ufs_cred_temp, key="cred_temp_uf")
            with cred_col2:
                _cidades_cred_temp = sorted(
                    _crosswalk_cred_temp.loc[
                        _crosswalk_cred_temp["UF"] == uf_cred_temp, "CIDADE"
                    ].unique()
                )
                cidade_cred_temp = st.selectbox("Cidade", options=_cidades_cred_temp, key="cred_temp_cidade")
            with cred_col3:
                st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
                projetar_clicado_temp = st.button(
                    "📊 Projetar", key="cred_temp_botao", use_container_width=True
                )
            if projetar_clicado_temp:
                st.session_state["cred_temp_ativa"] = (uf_cred_temp, cidade_cred_temp)

            _ativa_cred_temp = st.session_state.get("cred_temp_ativa")
            if not _ativa_cred_temp:
                st.info("Escolha UF e cidade acima e clique em Projetar.")
            else:
                _uf_ativa_temp, _cidade_ativa_temp = _ativa_cred_temp
                _linha_cluster_temp = _crosswalk_cred_temp[
                    (_crosswalk_cred_temp["UF"] == _uf_ativa_temp)
                    & (_crosswalk_cred_temp["CIDADE"] == _cidade_ativa_temp)
                ]
                if _linha_cluster_temp.empty:
                    st.warning(f"Não encontrei o Cluster de {_cidade_ativa_temp}/{_uf_ativa_temp}.")
                else:
                    _cluster_ativo_temp = _linha_cluster_temp["CLUSTER"].iloc[0]
                    st.markdown(
                        f"📍 **{_cidade_ativa_temp} / {_uf_ativa_temp}** · Cluster **{_cluster_ativo_temp}**"
                    )
                    # ---- aviso de escopo: CMP/menor valor/CS aqui só enxergam o que estiver
                    # dentro dos filtros de página ativos agora (Mês/Plano/Especialidade +
                    # Período do mês) — se algum estiver restringindo, os números batem com
                    # esse recorte, não com a base inteira. ----
                    _filtros_ativos_temp = []
                    if f_mes:
                        _filtros_ativos_temp.append(f"Mês: {', '.join(f_mes)}")
                    if f_plano:
                        _filtros_ativos_temp.append(f"Plano: {', '.join(str(p) for p in f_plano)}")
                    if f_especialidade:
                        _filtros_ativos_temp.append(f"Especialidade: {', '.join(f_especialidade)}")
                    if modo_periodo_temp == "Escolher dias":
                        _filtros_ativos_temp.append(f"Dias: {dia_ini_temp} a {dia_fim_temp}")
                    if _filtros_ativos_temp:
                        st.warning(
                            "⚠️ Filtro(s) de página ativo(s) — CMP, menor valor e CS abaixo refletem "
                            "só esse recorte, não a base inteira: " + " · ".join(_filtros_ativos_temp)
                        )
                    else:
                        st.caption("Nenhum filtro de página ativo (Mês/Plano/Especialidade/Dias) — usando a base inteira.")

                    # ---- taxa nacional por procedimento (mesma referência do FASE usado no
                    # resto do painel — reaproveita calcular_media_nacional(), não mexe em
                    # severidade.py) ----
                    _nacional_cred_temp = calcular_media_nacional(
                        agregado, "NOME_PROCEDIMENTO", usuarios=base_usuarios
                    ).reset_index()[["NOME_PROCEDIMENTO", "qtd_procedimentos", "qtd_usuarios"]].rename(columns={
                        "qtd_procedimentos": "qtd_procedimentos_nacional", "qtd_usuarios": "qtd_vidas_nacional",
                    })

                    # ---- CS por prestador, dentro do Cluster escolhido — base de tudo que
                    # segue (CS Ideal/Meta, CS praticado no Cluster/cidade, valor unitário) ----
                    _grupo_prest_cred_temp = [
                        "CLUSTER", "CIDADE_PRESTADOR", "UF", "ESPECIALIDADE", "NOME_PROCEDIMENTO", "CD_PRESTADOR",
                    ]
                    _base_cluster_temp = df_filtrado[df_filtrado["CLUSTER"] == _cluster_ativo_temp]
                    # ---- código -> nome do prestador (pra exibir nome em vez de só código nos
                    # detalhes de CMP/menor valor) — moda por CD_PRESTADOR, sem entrar no groupby
                    # principal (evita duplicar linha se o nome tiver variação de grafia). ----
                    if "NOME_PRESTADOR" in _base_cluster_temp.columns:
                        _nomes_prest_cred_temp = _base_cluster_temp.groupby(
                            "CD_PRESTADOR", observed=True
                        )["NOME_PRESTADOR"].agg(
                            lambda x: x.mode().iloc[0] if not x.mode().empty else None
                        ).to_dict()
                    else:
                        _nomes_prest_cred_temp = {}

                    def _nome_prestador_temp(cod):
                        if cod is None or (isinstance(cod, float) and pd.isna(cod)):
                            return "—"
                        nome = _nomes_prest_cred_temp.get(cod)
                        if nome is None or (isinstance(nome, float) and pd.isna(nome)) or not str(nome).strip():
                            return f"Prestador {int(cod)}"
                        return str(nome)

                    if _base_cluster_temp.empty:
                        st.info(
                            f"Nenhum procedimento praticado ainda no Cluster {_cluster_ativo_temp} "
                            "(dentro dos filtros de página atuais) — sem dado suficiente pra projetar."
                        )
                    else:
                        _base_prest_temp = _base_cluster_temp.groupby(
                            _grupo_prest_cred_temp, dropna=False, observed=True
                        ).agg(
                            qtd_procedimentos=("qtd_procedimentos", "sum"),
                            soma_valor=("soma_valor", "sum"),
                        ).reset_index()
                        _usuarios_cluster_temp = usuarios_filtrado[usuarios_filtrado["CLUSTER"] == _cluster_ativo_temp]
                        _vidas_prest_temp = vidas_por(_usuarios_cluster_temp, _grupo_prest_cred_temp)
                        _base_prest_temp = _base_prest_temp.merge(
                            _vidas_prest_temp, on=_grupo_prest_cred_temp, how="left"
                        )
                        _base_prest_temp["qtd_usuarios"] = _base_prest_temp["qtd_usuarios"].fillna(0)
                        _base_prest_temp = _base_prest_temp.merge(
                            _nacional_cred_temp, on="NOME_PROCEDIMENTO", how="left"
                        )
                        _base_prest_temp["fase_esperado"] = (
                            _base_prest_temp["qtd_procedimentos_nacional"] / _base_prest_temp["qtd_vidas_nacional"]
                        ) * _base_prest_temp["qtd_usuarios"]
                        _base_prest_temp = _base_prest_temp[_base_prest_temp["fase_esperado"] > 0].copy()
                        _base_prest_temp["cs_prestador"] = (
                            _base_prest_temp["qtd_procedimentos"] / _base_prest_temp["fase_esperado"]
                        ) * 10
                        _base_prest_temp["valor_unitario_prestador"] = (
                            _base_prest_temp["soma_valor"] / _base_prest_temp["qtd_procedimentos"]
                        )
                        # ---- subconjunto só com valor pago real (soma_valor > 0) — usado nos
                        # cálculos de CMP/menor valor (preço), pra não deixar um registro com
                        # VL_PAGO zerado/ausente (erro de dado, não procedimento de graça) virar
                        # "menor valor R$ 0,00" ou derrubar o CMP. O CS continua usando
                        # _base_prest_temp inteiro (volume do procedimento vale mesmo sem preço
                        # registrado). ----
                        _base_valor_valido_temp = _base_prest_temp[_base_prest_temp["soma_valor"] > 0].copy()

                        if _base_prest_temp.empty:
                            st.info(
                                f"Nenhum procedimento com taxa nacional válida no Cluster "
                                f"{_cluster_ativo_temp} — sem dado suficiente pra projetar."
                            )
                        else:
                            _grupo_esp_proc_temp = ["ESPECIALIDADE", "NOME_PROCEDIMENTO"]

                            # ---- CS Ideal (mínimo no Cluster) e CS Meta (Ideal x 0,80) ----
                            _cs_ideal_temp = _base_prest_temp.groupby(
                                _grupo_esp_proc_temp, observed=True
                            )["cs_prestador"].min().reset_index().rename(columns={"cs_prestador": "cs_ideal"})
                            _cs_ideal_temp["cs_meta"] = _cs_ideal_temp["cs_ideal"] * 0.8

                            # ---- MENOR VALOR: o menor valor unitário já praticado por um prestador
                            # do Cluster, naquele procedimento, EXCLUINDO registros com valor pago
                            # zerado/ausente (_base_valor_valido_temp — ver nota acima; sem isso, um
                            # VL_PAGO quebrado vira "menor valor R$ 0,00" e puxa o projetado pra
                            # baixo indevidamente). Mesmo critério do CS Ideal — o melhor caso real
                            # observado, não uma média/mediana. Continua vindo do Cluster inteiro
                            # (referência de negociação), mesmo quando a cidade escolhida ainda não
                            # tiver prestador — só não aparece na tela nesse caso (ver
                            # _tem_prestador_temp mais abaixo). Usa idxmin (não só min()) pra também
                            # guardar QUAL prestador/cidade bateu esse valor — dá pra auditar no
                            # detalhe do cálculo, em vez de confiar cegamente no número. ----
                            if _base_valor_valido_temp.empty:
                                _menor_valor_temp = pd.DataFrame(
                                    columns=_grupo_esp_proc_temp + ["menor_valor", "menor_valor_prestador", "menor_valor_cidade"]
                                )
                            else:
                                _idx_menor_valor_temp = _base_valor_valido_temp.groupby(
                                    _grupo_esp_proc_temp, observed=True
                                )["valor_unitario_prestador"].idxmin()
                                _menor_valor_temp = _base_valor_valido_temp.loc[_idx_menor_valor_temp, [
                                    "ESPECIALIDADE", "NOME_PROCEDIMENTO", "valor_unitario_prestador",
                                    "CD_PRESTADOR", "CIDADE_PRESTADOR",
                                ]].rename(columns={
                                    "valor_unitario_prestador": "menor_valor",
                                    "CD_PRESTADOR": "menor_valor_prestador",
                                    "CIDADE_PRESTADOR": "menor_valor_cidade",
                                })

                            # ---- o que já é praticado NA CIDADE escolhida (qtde de prestadores,
                            # CS e CMP) — sem fallback pro Cluster: procedimento sem prestador na
                            # cidade fica sem essas informações (vira "—" na exibição). ----
                            _base_cidade_temp = _base_prest_temp[
                                (_base_prest_temp["CIDADE_PRESTADOR"] == _cidade_ativa_temp)
                                & (_base_prest_temp["UF"] == _uf_ativa_temp)
                            ]
                            _qtd_prest_cidade_temp = _base_cidade_temp.groupby(
                                _grupo_esp_proc_temp, observed=True
                            )["CD_PRESTADOR"].nunique().reset_index().rename(
                                columns={"CD_PRESTADOR": "qtd_prestadores_cidade"}
                            )
                            _cs_cidade_temp = _base_cidade_temp.groupby(_grupo_esp_proc_temp, observed=True).agg(
                                _fase_soma_cidade=("fase_esperado", "sum"),
                                _qp_soma_cidade=("qtd_procedimentos", "sum"),
                            ).reset_index()
                            _cs_cidade_temp["cs_praticado_cidade"] = (
                                _cs_cidade_temp["_qp_soma_cidade"] / _cs_cidade_temp["_fase_soma_cidade"]
                            ) * 10
                            # CMP também só com registros de valor pago válido (mesmo motivo do
                            # menor valor) — um prestador com VL_PAGO zerado ainda conta em
                            # "Prestadores na cidade" e no CS praticado, só fica fora do CMP.
                            _base_cidade_valor_valido_temp = _base_cidade_temp[_base_cidade_temp["soma_valor"] > 0]
                            _cmp_cidade_temp = _base_cidade_valor_valido_temp.groupby(
                                _grupo_esp_proc_temp, observed=True
                            ).agg(
                                _valor_soma_cidade=("soma_valor", "sum"),
                                _qtd_soma_cidade=("qtd_procedimentos", "sum"),
                            ).reset_index()
                            _cmp_cidade_temp["cmp_cidade"] = (
                                _cmp_cidade_temp["_valor_soma_cidade"] / _cmp_cidade_temp["_qtd_soma_cidade"]
                            )
                            # ---- nomes dos prestadores que entraram no CMP da cidade (só
                            # informativo, pra dar pra ver quem formou aquela média) ----
                            _prestadores_cmp_cidade_temp = _base_cidade_valor_valido_temp.groupby(
                                _grupo_esp_proc_temp, observed=True
                            )["CD_PRESTADOR"].apply(
                                lambda codigos: ", ".join(sorted({_nome_prestador_temp(c) for c in codigos}))
                            ).reset_index().rename(columns={"CD_PRESTADOR": "prestadores_cmp_cidade"})

                            # ---- MENOR VALOR DA CIDADE: mesmo critério do menor valor do Cluster
                            # (só valor pago válido), mas restrito à cidade escolhida — pra comparar
                            # lado a lado com o menor valor do Cluster inteiro. ----
                            if _base_cidade_valor_valido_temp.empty:
                                _menor_valor_cidade_temp = pd.DataFrame(
                                    columns=_grupo_esp_proc_temp + ["menor_valor_da_cidade", "menor_valor_da_cidade_prestador"]
                                )
                            else:
                                _idx_menor_cidade_temp = _base_cidade_valor_valido_temp.groupby(
                                    _grupo_esp_proc_temp, observed=True
                                )["valor_unitario_prestador"].idxmin()
                                _menor_valor_cidade_temp = _base_cidade_valor_valido_temp.loc[_idx_menor_cidade_temp, [
                                    "ESPECIALIDADE", "NOME_PROCEDIMENTO", "valor_unitario_prestador", "CD_PRESTADOR",
                                ]].rename(columns={
                                    "valor_unitario_prestador": "menor_valor_da_cidade",
                                    "CD_PRESTADOR": "menor_valor_da_cidade_prestador",
                                })

                            # ---- MAIOR VALOR DA CIDADE: mesmo critério (só valor pago válido),
                            # restrito à cidade escolhida — mostrado no detalhe no lugar do menor
                            # valor do Cluster, pra dar a faixa de preço praticada na própria cidade. ----
                            if _base_cidade_valor_valido_temp.empty:
                                _maior_valor_cidade_temp = pd.DataFrame(
                                    columns=_grupo_esp_proc_temp + ["maior_valor_da_cidade", "maior_valor_da_cidade_prestador"]
                                )
                            else:
                                _idx_maior_cidade_temp = _base_cidade_valor_valido_temp.groupby(
                                    _grupo_esp_proc_temp, observed=True
                                )["valor_unitario_prestador"].idxmax()
                                _maior_valor_cidade_temp = _base_cidade_valor_valido_temp.loc[_idx_maior_cidade_temp, [
                                    "ESPECIALIDADE", "NOME_PROCEDIMENTO", "valor_unitario_prestador", "CD_PRESTADOR",
                                ]].rename(columns={
                                    "valor_unitario_prestador": "maior_valor_da_cidade",
                                    "CD_PRESTADOR": "maior_valor_da_cidade_prestador",
                                })

                            _grade_cred_temp = (
                                _cs_ideal_temp
                                .merge(_menor_valor_temp, on=_grupo_esp_proc_temp, how="left")
                                .merge(_qtd_prest_cidade_temp, on=_grupo_esp_proc_temp, how="left")
                                .merge(_cs_cidade_temp[_grupo_esp_proc_temp + ["cs_praticado_cidade"]],
                                       on=_grupo_esp_proc_temp, how="left")
                                .merge(_cmp_cidade_temp[_grupo_esp_proc_temp
                                                          + ["cmp_cidade", "_valor_soma_cidade", "_qtd_soma_cidade"]],
                                       on=_grupo_esp_proc_temp, how="left")
                                .merge(_prestadores_cmp_cidade_temp, on=_grupo_esp_proc_temp, how="left")
                                .merge(_menor_valor_cidade_temp, on=_grupo_esp_proc_temp, how="left")
                                .merge(_maior_valor_cidade_temp, on=_grupo_esp_proc_temp, how="left")
                            )
                            _grade_cred_temp["qtd_prestadores_cidade"] = (
                                _grade_cred_temp["qtd_prestadores_cidade"].fillna(0).astype(int)
                            )
                            # ---- Sem prestador na cidade pra aquele procedimento -> nada de
                            # números (nem CS praticado, nem CS Ideal/Meta, nem valor projetado),
                            # só "—". Nada de herdar a referência do Cluster nesse caso: só entra
                            # linha com dado quando a própria cidade já tem prestador ali. ----
                            _tem_prestador_temp = _grade_cred_temp["qtd_prestadores_cidade"] > 0
                            _grade_cred_temp["cs_praticado"] = _grade_cred_temp["cs_praticado_cidade"].where(
                                _tem_prestador_temp
                            )
                            _grade_cred_temp["cmp"] = _grade_cred_temp["cmp_cidade"].where(_tem_prestador_temp)
                            _grade_cred_temp["cs_ideal"] = _grade_cred_temp["cs_ideal"].where(_tem_prestador_temp)
                            _grade_cred_temp["cs_meta"] = _grade_cred_temp["cs_meta"].where(_tem_prestador_temp)
                            _grade_cred_temp["menor_valor_da_cidade"] = _grade_cred_temp[
                                "menor_valor_da_cidade"
                            ].where(_tem_prestador_temp)
                            _grade_cred_temp.loc[~_tem_prestador_temp, "menor_valor_da_cidade_prestador"] = None
                            _grade_cred_temp.loc[~_tem_prestador_temp, "prestadores_cmp_cidade"] = None
                            _grade_cred_temp["maior_valor_da_cidade"] = _grade_cred_temp[
                                "maior_valor_da_cidade"
                            ].where(_tem_prestador_temp)
                            _grade_cred_temp.loc[~_tem_prestador_temp, "maior_valor_da_cidade_prestador"] = None
                            # ---- Valor unit. projetado = (CMP + MENOR VALOR) / 2 — NaN se CMP for
                            # NaN (cidade sem prestador), propagando o "—" automaticamente. ----
                            _grade_cred_temp["valor_unitario_projetado"] = (
                                _grade_cred_temp["cmp"] + _grade_cred_temp["menor_valor"]
                            ) / 2

                            # ---- filtros de busca (procedimento por texto + especialidade) ----
                            fcred1, fcred2 = st.columns([2, 1])
                            with fcred1:
                                _busca_proc_cred_temp = st.text_input(
                                    "Filtrar por procedimento (digite parte do nome)",
                                    key="cred_temp_busca_proc",
                                )
                            with fcred2:
                                _opcoes_esp_cred_temp = ["Todas"] + sorted(
                                    _grade_cred_temp["ESPECIALIDADE"].dropna().unique()
                                )
                                _esp_sel_cred_temp = st.selectbox(
                                    "Especialidade", options=_opcoes_esp_cred_temp, key="cred_temp_especialidade"
                                )

                            # ---- limpar filtros de busca desta aba, de uma vez só (mesmo
                            # padrão da aba Temporária: apaga a key do session_state + rerun) ----
                            if st.button("🧹 Limpar filtros", key="limpar_filtros_cred_temp"):
                                for _chave_filtro_cred_temp in ("cred_temp_busca_proc", "cred_temp_especialidade"):
                                    st.session_state.pop(_chave_filtro_cred_temp, None)
                                st.rerun()

                            _grade_exib_temp = _grade_cred_temp.copy()
                            if _busca_proc_cred_temp.strip():
                                _grade_exib_temp = _grade_exib_temp[
                                    _grade_exib_temp["NOME_PROCEDIMENTO"].str.contains(
                                        _busca_proc_cred_temp.strip(), case=False, na=False
                                    )
                                ]
                            if _esp_sel_cred_temp != "Todas":
                                _grade_exib_temp = _grade_exib_temp[
                                    _grade_exib_temp["ESPECIALIDADE"] == _esp_sel_cred_temp
                                ]
                            _grade_exib_temp = _grade_exib_temp.sort_values(
                                ["ESPECIALIDADE", "NOME_PROCEDIMENTO"]
                            )

                            if _grade_exib_temp.empty:
                                st.info("Nenhum procedimento encontrado com esse filtro.")
                            else:
                                def _fmt_cs_cred_temp(v):
                                    if v is None or (isinstance(v, float) and pd.isna(v)):
                                        return "—"
                                    s = f"{v:,.3f}"
                                    return s.replace(",", "§").replace(".", ",").replace("§", ".")

                                # ---- detalhe do cálculo (hover da coluna Valor unit. projetado) —
                                # pra dar pra auditar o número (valor total/qtde que formaram o CMP
                                # e quem/onde bateu o menor valor), sem precisar confiar às cegas.
                                # Só monta pra quem tem prestador na cidade (senão a célula é "—"). ----
                                def _detalhe_valor_linha(row):
                                    if not (row["qtd_prestadores_cidade"] > 0) or pd.isna(row["cmp"]):
                                        return ""
                                    return (
                                        f"CMP = {fmt_brl(row['_valor_soma_cidade'])} ÷ "
                                        f"{fmt_int(row['_qtd_soma_cidade'])} proced. = {fmt_brl(row['cmp'])}  |  "
                                        f"Menor valor no Cluster = {fmt_brl(row['menor_valor'])} "
                                        f"(prestador {fmt_int(row['menor_valor_prestador'])}, "
                                        f"{row['menor_valor_cidade']})  |  "
                                        f"Projetado = ({fmt_brl(row['cmp'])} + {fmt_brl(row['menor_valor'])}) ÷ 2 = "
                                        f"{fmt_brl(row['valor_unitario_projetado'])}"
                                    )
                                _detalhe_valor_temp = _grade_exib_temp.apply(_detalhe_valor_linha, axis=1)

                                _tabela_final_temp = pd.DataFrame({
                                    "Especialidade": _grade_exib_temp["ESPECIALIDADE"],
                                    "Procedimento": _grade_exib_temp["NOME_PROCEDIMENTO"],
                                    "Prestadores na cidade": _grade_exib_temp["qtd_prestadores_cidade"],
                                    "CS praticado": _grade_exib_temp["cs_praticado"].map(_fmt_cs_cred_temp),
                                    "CS Ideal": _grade_exib_temp["cs_ideal"].map(_fmt_cs_cred_temp),
                                    "CS Meta": _grade_exib_temp["cs_meta"].map(_fmt_cs_cred_temp),
                                    "Valor unit. projetado": _grade_exib_temp["valor_unitario_projetado"].map(fmt_brl),
                                })

                                def _tabela_html_cred_temp(df_exibicao, scroll=True, tooltips_ultima_coluna=None):
                                    st.markdown("""
                                        <style>
                                        .grade-cred-temp-wrap-scroll {
                                            overflow-x: auto; overflow-y: auto; max-height: 420px;
                                        }
                                        .grade-cred-temp { border-collapse: collapse; width: 100%; font-size: 12px; }
                                        .grade-cred-temp th, .grade-cred-temp td {
                                            border: 1px solid #444; padding: 4px 8px; text-align: right;
                                            white-space: nowrap;
                                        }
                                        .grade-cred-temp th:nth-child(-n+2), .grade-cred-temp td:nth-child(-n+2) {
                                            text-align: left; max-width: 260px; overflow: hidden;
                                            text-overflow: ellipsis;
                                        }
                                        .grade-cred-temp th { font-weight: 600; }
                                        </style>
                                    """, unsafe_allow_html=True)
                                    cabecalho = "".join(f"<th>{html.escape(str(c))}</th>" for c in df_exibicao.columns)
                                    _n_colunas_temp = len(df_exibicao.columns)

                                    def _linha_html(linha, tooltip_extra):
                                        celulas = []
                                        for i, v in enumerate(linha):
                                            texto = html.escape(str(v))
                                            if i < 2:
                                                titulo_attr = f' title="{texto}"'
                                            elif i == _n_colunas_temp - 1 and tooltip_extra:
                                                titulo_attr = f' title="{html.escape(tooltip_extra)}"'
                                            else:
                                                titulo_attr = ""
                                            celulas.append(f"<td{titulo_attr}>{texto}</td>")
                                        return "<tr>" + "".join(celulas) + "</tr>"

                                    _tooltips_temp = (
                                        list(tooltips_ultima_coluna) if tooltips_ultima_coluna is not None
                                        else [""] * len(df_exibicao)
                                    )
                                    linhas = "".join(
                                        _linha_html(linha, tt) for linha, tt in zip(
                                            df_exibicao.itertuples(index=False, name=None), _tooltips_temp
                                        )
                                    )
                                    classe_wrap = "grade-cred-temp-wrap-scroll" if scroll else "grade-cred-temp-wrap"
                                    st.markdown(
                                        f"""<div class="{classe_wrap}"><table class="grade-cred-temp">
                                        <thead><tr>{cabecalho}</tr></thead><tbody>{linhas}</tbody></table></div>""",
                                        unsafe_allow_html=True,
                                    )

                                st.caption(f"{len(_tabela_final_temp)} procedimento(s) no Cluster {_cluster_ativo_temp}.")
                                _tabela_html_cred_temp(
                                    _tabela_final_temp, scroll=True, tooltips_ultima_coluna=_detalhe_valor_temp
                                )

                                # ---- detalhe do cálculo, sempre visível (sem depender de hover, que
                                # não funciona em touch/tablet e fica escondido atrás do menu do
                                # Streamlit) — escolhe o procedimento e vê CMP/menor valor por extenso. ----
                                with st.expander("🔍 Ver detalhe do cálculo de um procedimento"):
                                    # zip() em vez de "+" vetorizado: NOME_PROCEDIMENTO/ESPECIALIDADE
                                    # são dtype category (herdado de severidade.py), e o "+" de Series
                                    # nessas colunas estoura TypeError dependendo da versão do pandas/
                                    # pyarrow — mesmo problema já visto no rótulo do ranking por código.
                                    _opcoes_detalhe_temp = [
                                        f"{proc} — {esp}"
                                        for proc, esp in zip(
                                            _grade_exib_temp["NOME_PROCEDIMENTO"], _grade_exib_temp["ESPECIALIDADE"]
                                        )
                                    ]
                                    if not _opcoes_detalhe_temp:
                                        st.info("Nenhum procedimento pra detalhar com o filtro atual.")
                                    else:
                                        _proc_detalhe_temp = st.selectbox(
                                            "Procedimento", options=_opcoes_detalhe_temp, key="cred_temp_detalhe_proc"
                                        )
                                        _idx_detalhe_temp = _opcoes_detalhe_temp.index(_proc_detalhe_temp)
                                        _linha_detalhe_temp = _grade_exib_temp.iloc[_idx_detalhe_temp]
                                        if not (_linha_detalhe_temp["qtd_prestadores_cidade"] > 0):
                                            st.info(
                                                "Sem prestador nesse procedimento na cidade escolhida — "
                                                "por isso a linha aparece com \"—\" na tabela."
                                            )
                                        else:
                                            dc1, dc2, dc3, dc4 = st.columns(4)
                                            dc1.metric(
                                                "CMP (na cidade)", fmt_brl(_linha_detalhe_temp["cmp"]),
                                                help=(
                                                    f"{fmt_brl(_linha_detalhe_temp['_valor_soma_cidade'])} ÷ "
                                                    f"{fmt_int(_linha_detalhe_temp['_qtd_soma_cidade'])} procedimentos"
                                                ),
                                            )

                                            dc2.metric(
                                                "Maior valor (na Cidade)",
                                                fmt_brl(_linha_detalhe_temp["maior_valor_da_cidade"]),
                                            )
                                            dc2.caption(
                                                f"Prestador: "
                                                f"{_nome_prestador_temp(_linha_detalhe_temp['maior_valor_da_cidade_prestador'])}"
                                            )

                                            dc3.metric(
                                                "Menor valor (na cidade)",
                                                fmt_brl(_linha_detalhe_temp["menor_valor_da_cidade"]),
                                            )
                                            dc3.caption(
                                                f"Prestador: "
                                                f"{_nome_prestador_temp(_linha_detalhe_temp['menor_valor_da_cidade_prestador'])}"
                                            )

                                            dc4.metric(
                                                "Valor unit. projetado",
                                                fmt_brl(_linha_detalhe_temp["valor_unitario_projetado"]),
                                                help=(
                                                    f"(CMP {fmt_brl(_linha_detalhe_temp['cmp'])} + Menor valor "
                                                    f"do Cluster {fmt_brl(_linha_detalhe_temp['menor_valor'])}, "
                                                    f"prestador {fmt_int(_linha_detalhe_temp['menor_valor_prestador'])} "
                                                    f"em {_linha_detalhe_temp['menor_valor_cidade']}) ÷ 2"
                                                ),
                                            )
    # ============================================================
    # COEFICIENTE DE SEVERIDADE (+ aba legada "🧪 Temp") — mesmo corpo de código rodado uma
    # vez por aba (ver _config_abas_cs_temp acima): "Coeficiente de Severidade" cobre TODOS
    # os procedimentos; "🧪 Temp" fica restrita aos 13 códigos originais (CODIGOS_TEMP_LEGADO).
    # ============================================================
    for (
        _tab_obj_cs_temp, _titulo_aba_temp, _codigos_restritos_temp, _sufixo_aba_temp,
        _prestador_fixo_temp, _mostrar_calculo_qp_temp,
    ) in _config_abas_cs_temp:
        with _tab_obj_cs_temp:
            st.markdown(f"#### {_titulo_aba_temp}")

            if _sufixo_aba_temp == "_smile":
                st.caption(
                    "Aba dedicada pra investigar o volume de procedimentos (550, 110, 100 e "
                    "510) da SMILE DENTAL CLINICA ODONTOLOGICA LTDA ME em São Paulo — filtro "
                    "Prestador já vem travado nela; troque livremente se quiser comparar com "
                    "outro prestador. \"CS da Cidade\"/\"Cálculo do CS Cidade\" mostram o CS de "
                    "todos os prestadores da mesma cidade, lado a lado com o CS da própria "
                    "clínica (colunas CS/Cálculo do CS), pra ajudar a enxergar se o volume dela "
                    "realmente destoa do praticado ao redor."
                )

            st.caption(
                "CS (Coeficiente de Severidade) = (QP ÷ FASE) × 10 (Se o resultado igual a 10 "
                "significa que o corte praticou exatamente o esperado pela taxa nacional; acima "
                "de 10, mais severo; abaixo de 10, menos severo.) Não considera valores em R$.  \n"
                "FASE = (qtd procedimentos nacional ÷ qtd vidas nacional) × qtd vidas em utilização  \n"
                "QP = qtd de procedimentos"
            )

            st.caption(
                "Selecione ao menos um filtro acima (procedimento, prestador, UF, região, cidade "
                "ou cluster) para ver a dispersão de severidade — sem nenhum filtro, o corte "
                "comparado se aproxima da própria base nacional e o CS fica pouco informativo."
            )

            if not MOSTRAR_FILTROS_TOPO and _sufixo_aba_temp == "_legado":
                # Mês/Plano/Especialidade do quadro de Filtros do topo (hoje oculto) — mesma
                # funcionalidade de antes (afetam df_filtrado/usuarios_filtrado, a página toda),
                # só que os campos agora aparecem aqui, dentro da aba "🧪 Temp: procedimentos
                # selecionados" (Temporária). O valor já foi lido do session_state mais acima
                # (antes de df_filtrado ser montado); declarar o widget aqui só sincroniza a
                # próxima interação do usuário, não afeta o resultado já calculado nesta rodada.
                # Desenhado só na aba Temporária (identificada pelo sufixo "_legado") — evita
                # campo duplicado, já que Mês/Plano/Especialidade são únicos pra página toda,
                # não por aba (mesmo se "Coeficiente de Severidade" for religada ao lado dela).
                fmt1, fmt2, fmt3 = st.columns(3)
                with fmt1:
                    st.multiselect("Mês", options=opcoes_mes_temp, key="temp_filtro_mes")
                with fmt2:
                    st.multiselect("Plano", options=opcoes_plano_temp, key="temp_filtro_plano")
                with fmt3:
                    st.multiselect("Especialidade", options=opcoes_especialidade_temp, key="temp_filtro_especialidade")

            # Mapa código -> nome do procedimento, dentro dos filtros ativos. Sem restrição
            # (_codigos_restritos_temp is None), cobre TODOS os procedimentos presentes; com
            # restrição (a aba legada, com a lista fixa de 13 códigos de origem), só os códigos
            # dessa lista que aparecerem nos filtros atuais (1 código = 1 nome, assumindo que cada
            # CD_PROCEDIMENTO tem uma única NOME_PROCEDIMENTO associada — é assim que o resto do
            # painel já trata "vidas" por procedimento, via NOME_PROCEDIMENTO).
            mapa_cod_nome_temp = (
                df_filtrado.dropna(subset=["CD_PROCEDIMENTO", "NOME_PROCEDIMENTO"])
                .drop_duplicates("CD_PROCEDIMENTO")
                .set_index("CD_PROCEDIMENTO")["NOME_PROCEDIMENTO"]
                .to_dict()
            )
            if _codigos_restritos_temp is not None:
                codigos_ausentes_temp = [c for c in _codigos_restritos_temp if c not in mapa_cod_nome_temp]
                mapa_cod_nome_temp = {
                    c: mapa_cod_nome_temp[c] for c in _codigos_restritos_temp if c in mapa_cod_nome_temp
                }
                if codigos_ausentes_temp:
                    st.caption(
                        f"Códigos sem ocorrência nos filtros atuais: "
                        f"{', '.join(str(c) for c in codigos_ausentes_temp)}."
                    )
            codigos_temp = sorted(mapa_cod_nome_temp.keys())

            nomes_temp = list(mapa_cod_nome_temp.values())

            if not nomes_temp:
                st.info("Nenhum procedimento encontrado nos filtros atuais.")
            else:
                df_temp_base = df_filtrado[df_filtrado["CD_PROCEDIMENTO"].isin(codigos_temp)]

                # ---- filtros extras só desta aba: procedimento, prestador, UF, região, cidade e cluster ----
                opcoes_proc_temp = ["Todos"] + [
                    f"{cod} — {mapa_cod_nome_temp[cod]}" for cod in codigos_temp if cod in mapa_cod_nome_temp
                ]
                def _opcoes_coluna_temp(coluna):
                    if coluna not in df_temp_base.columns:
                        return ["Todos"]
                    return ["Todos"] + sorted(
                        v for v in df_temp_base[coluna].dropna().unique().tolist() if str(v).strip()
                    )
                opcoes_prestador_temp = _opcoes_coluna_temp("NOME_PRESTADOR")
                opcoes_uf_temp = _opcoes_coluna_temp("UF")
                opcoes_regiao_temp = _opcoes_coluna_temp("REGIAO")
                opcoes_cidade_temp = _opcoes_coluna_temp("CIDADE_PRESTADOR")
                opcoes_cluster_temp = _opcoes_coluna_temp("CLUSTER")

                # ---- trava o filtro Prestador desta aba num prestador fixo (só a aba "🔎 SMILE
                # DENTAL" usa isso hoje) — precisa rodar ANTES do st.selectbox correspondente ser
                # instanciado (Streamlit só aceita pré-setar o session_state de uma key antes do
                # widget dessa key existir nesta rodada). Comparação por substring maiúscula pra
                # tolerar pequena diferença de acentuação/espaço no nome cadastrado na base. Só
                # roda na primeira vez que a aba aparece nesta sessão — depois disso a key já
                # existe no session_state e o usuário fica livre pra trocar de prestador (ou
                # limpar com "🧹 Limpar filtros", que apaga a key e faz a trava valer de novo).
                if _prestador_fixo_temp is not None:
                    _chave_prestador_fixo_temp = f"temp_filtro_prestador{_sufixo_aba_temp}"
                    if _chave_prestador_fixo_temp not in st.session_state:
                        _alvo_prestador_fixo_temp = _prestador_fixo_temp.strip().upper()
                        _match_prestador_fixo_temp = next(
                            (
                                p for p in opcoes_prestador_temp
                                if _alvo_prestador_fixo_temp in str(p).strip().upper()
                            ),
                            None,
                        )
                        if _match_prestador_fixo_temp is not None:
                            st.session_state[_chave_prestador_fixo_temp] = _match_prestador_fixo_temp
                        else:
                            st.warning(
                                f"Não encontrei \"{_prestador_fixo_temp}\" entre os prestadores "
                                "dos filtros atuais (Mês/Plano/Especialidade da página) — "
                                "selecione manualmente no filtro Prestador abaixo, ou confira se "
                                "o nome está exatamente assim na base."
                            )

                (
                    fc_proc_temp, fc_prest_temp, fc_uf_temp,
                    fc_regiao_temp, fc_cidade_temp, fc_cluster_temp,
                ) = st.columns(6)
                with fc_proc_temp:
                    proc_sel_temp = st.selectbox(
                        "Procedimento", opcoes_proc_temp, key=f"temp_filtro_procedimento{_sufixo_aba_temp}"
                    )
                with fc_prest_temp:
                    prest_sel_temp = st.selectbox(
                        "Prestador", opcoes_prestador_temp, key=f"temp_filtro_prestador{_sufixo_aba_temp}"
                    )
                with fc_uf_temp:
                    uf_sel_temp = st.selectbox(
                        "UF", opcoes_uf_temp, key=f"temp_filtro_uf{_sufixo_aba_temp}"
                    )
                with fc_regiao_temp:
                    regiao_sel_temp = st.selectbox(
                        "Região", opcoes_regiao_temp, key=f"temp_filtro_regiao{_sufixo_aba_temp}"
                    )
                with fc_cidade_temp:
                    cidade_sel_temp = st.selectbox(
                        "Cidade", opcoes_cidade_temp, key=f"temp_filtro_cidade{_sufixo_aba_temp}"
                    )
                with fc_cluster_temp:
                    cluster_sel_temp = st.selectbox(
                        "Cluster", opcoes_cluster_temp, key=f"temp_filtro_cluster{_sufixo_aba_temp}"
                    )

                # ---- limpar filtros, de uma vez só ---- apaga a key do session_state de cada
                # campo (Mês/Plano/Especialidade também, só na aba Temporária — são únicos pra
                # página toda) e força um rerun; sem a key, o widget volta pro valor padrão dele
                # (lista vazia no multiselect, "Todos" no selectbox) já na próxima rodada. Não dá
                # pra só reatribuir o valor aqui, porque os widgets acima já foram instanciados
                # nesta mesma rodada — Streamlit não permite mudar o valor de um widget já criado
                # sem passar pelo session_state + rerun.
                _chaves_filtro_aba_temp = [
                    f"temp_filtro_procedimento{_sufixo_aba_temp}",
                    f"temp_filtro_prestador{_sufixo_aba_temp}",
                    f"temp_filtro_uf{_sufixo_aba_temp}",
                    f"temp_filtro_regiao{_sufixo_aba_temp}",
                    f"temp_filtro_cidade{_sufixo_aba_temp}",
                    f"temp_filtro_cluster{_sufixo_aba_temp}",
                ]
                if _sufixo_aba_temp == "_legado":
                    _chaves_filtro_aba_temp += [
                        "temp_filtro_mes", "temp_filtro_plano", "temp_filtro_especialidade",
                    ]
                if st.button("🧹 Limpar filtros", key=f"limpar_filtros_temp{_sufixo_aba_temp}"):
                    for _chave_filtro_temp in _chaves_filtro_aba_temp:
                        st.session_state.pop(_chave_filtro_temp, None)
                    st.rerun()

                # Sem nenhum dos 6 filtros desta aba aplicado, o corte comparado tende a se
                # aproximar da própria base nacional usada como referência — o CS fica pouco
                # informativo (varia perto de 10 só por coincidência de escala, não por
                # severidade real). Nesse caso o CS é exibido como "—" em vez do valor calculado.
                nenhum_filtro_temp = (
                    proc_sel_temp == "Todos" and prest_sel_temp == "Todos" and uf_sel_temp == "Todos"
                    and regiao_sel_temp == "Todos" and cidade_sel_temp == "Todos" and cluster_sel_temp == "Todos"
                )

                # Aplica os filtros extras (além dos filtros do topo da página, já embutidos em
                # df_temp_base) por cima da base dos códigos selecionados.
                df_temp = df_temp_base
                cod_sel_temp = None
                if proc_sel_temp != "Todos":
                    cod_sel_temp = int(proc_sel_temp.split(" — ")[0])
                    df_temp = df_temp[df_temp["CD_PROCEDIMENTO"] == cod_sel_temp]
                if prest_sel_temp != "Todos":
                    df_temp = df_temp[df_temp["NOME_PRESTADOR"] == prest_sel_temp]
                if uf_sel_temp != "Todos" and "UF" in df_temp.columns:
                    df_temp = df_temp[df_temp["UF"] == uf_sel_temp]
                if regiao_sel_temp != "Todos" and "REGIAO" in df_temp.columns:
                    df_temp = df_temp[df_temp["REGIAO"] == regiao_sel_temp]
                if cidade_sel_temp != "Todos" and "CIDADE_PRESTADOR" in df_temp.columns:
                    df_temp = df_temp[df_temp["CIDADE_PRESTADOR"] == cidade_sel_temp]
                if cluster_sel_temp != "Todos" and "CLUSTER" in df_temp.columns:
                    df_temp = df_temp[df_temp["CLUSTER"] == cluster_sel_temp]

                nomes_temp_ativos = df_temp["NOME_PROCEDIMENTO"].unique().tolist()
                usuarios_temp = usuarios_filtrado[usuarios_filtrado["NOME_PROCEDIMENTO"].isin(nomes_temp_ativos)]
                if prest_sel_temp != "Todos" and "NOME_PRESTADOR" in usuarios_temp.columns:
                    usuarios_temp = usuarios_temp[usuarios_temp["NOME_PRESTADOR"] == prest_sel_temp]
                if uf_sel_temp != "Todos" and "UF" in usuarios_temp.columns:
                    usuarios_temp = usuarios_temp[usuarios_temp["UF"] == uf_sel_temp]
                if regiao_sel_temp != "Todos" and "REGIAO" in usuarios_temp.columns:
                    usuarios_temp = usuarios_temp[usuarios_temp["REGIAO"] == regiao_sel_temp]
                if cidade_sel_temp != "Todos" and "CIDADE_PRESTADOR" in usuarios_temp.columns:
                    usuarios_temp = usuarios_temp[usuarios_temp["CIDADE_PRESTADOR"] == cidade_sel_temp]
                if cluster_sel_temp != "Todos" and "CLUSTER" in usuarios_temp.columns:
                    usuarios_temp = usuarios_temp[usuarios_temp["CLUSTER"] == cluster_sel_temp]

                # ---- métricas gerais (os códigos selecionados somados, sem contar a mesma vida 2x) ----
                _qtd_geral_temp = df_temp["qtd_procedimentos"].sum()
                _uso_geral_temp = df_temp["soma_uso"].sum()
                _vidas_geral_temp = usuarios_temp["CD_USUARIO"].nunique()

                mt1, mt2, mt3, mt4 = st.columns(4)
                mt1.metric("Qtde de procedimentos", fmt_int(_qtd_geral_temp))
                mt2.metric("Qtde de vidas", fmt_int(_vidas_geral_temp))
                mt3.metric("Soma de uso", fmt_int(_uso_geral_temp))
                mt4.metric(
                    "Uso por vida",
                    fmt_float2(_uso_geral_temp / _vidas_geral_temp) if _vidas_geral_temp else "—",
                )

                # ---- período considerado (data real, não só o mês) — só aparece quando algum
                # filtro está ativo (Mês/Plano/Especialidade da página ou os 6 desta aba), pra
                # não poluir a tela sem filtro nenhum. MES vem como string "AAAA-MM" e DIA como
                # o dia do mês (dt.day) — ambos originados da mesma DATA_REF em severidade.py —,
                # então dá pra reconstruir a data real de início/fim do recorte, não só o mês. ----
                def _periodo_considerado_temp(df):
                    if df is None or df.empty or "MES" not in df.columns:
                        return None
                    meses_presentes_temp = sorted(df["MES"].dropna().unique())
                    if not meses_presentes_temp:
                        return None
                    mes_min_temp, mes_max_temp = meses_presentes_temp[0], meses_presentes_temp[-1]
                    try:
                        ano_min_temp, mes_num_min_temp = (int(p) for p in mes_min_temp.split("-"))
                        ano_max_temp, mes_num_max_temp = (int(p) for p in mes_max_temp.split("-"))
                    except (ValueError, AttributeError):
                        return None
                    if "DIA" in df.columns:
                        _dias_mes_min_temp = df.loc[df["MES"] == mes_min_temp, "DIA"].dropna()
                        dia_min_temp = int(_dias_mes_min_temp.min()) if not _dias_mes_min_temp.empty else 1
                        _dias_mes_max_temp = df.loc[df["MES"] == mes_max_temp, "DIA"].dropna()
                        dia_max_temp = (
                            int(_dias_mes_max_temp.max()) if not _dias_mes_max_temp.empty
                            else calendar.monthrange(ano_max_temp, mes_num_max_temp)[1]
                        )
                    else:
                        dia_min_temp = 1
                        dia_max_temp = calendar.monthrange(ano_max_temp, mes_num_max_temp)[1]
                    # trava defensiva contra dia fora do intervalo do mês (não deveria acontecer
                    # com dado real, mas evita crash se algum DIA vier corrompido/fora de faixa).
                    dia_min_temp = min(max(dia_min_temp, 1), calendar.monthrange(ano_min_temp, mes_num_min_temp)[1])
                    dia_max_temp = min(max(dia_max_temp, 1), calendar.monthrange(ano_max_temp, mes_num_max_temp)[1])
                    try:
                        data_ini_temp = date(ano_min_temp, mes_num_min_temp, dia_min_temp)
                        data_fim_temp = date(ano_max_temp, mes_num_max_temp, dia_max_temp)
                    except ValueError:
                        return None
                    return f"{data_ini_temp.strftime('%d/%m/%Y')} a {data_fim_temp.strftime('%d/%m/%Y')}"

                _algum_filtro_ativo_temp = bool(f_mes or f_plano or f_especialidade) or not nenhum_filtro_temp
                if _algum_filtro_ativo_temp:
                    _periodo_temp = _periodo_considerado_temp(df_temp)
                    if _periodo_temp:
                        st.caption(f"Período considerado: {_periodo_temp}")

                st.divider()

                # ---- ranking por código ----
                # Calculado direto sobre df_temp/usuarios_temp, que já vêm com os filtros do topo da
                # página + os dois filtros extras desta aba (procedimento e prestador) aplicados —
                # não usa mais "peso do grupo" (era só usado pelo FASE oficial, que esta aba não
                # exibe mais), então não precisa mais calcular sobre a base toda antes de recortar.
                rank_temp = ranking_severidade(
                    df_temp, "NOME_PROCEDIMENTO", top_n=1_000_000, usuarios=usuarios_temp
                ).copy()
                nome_para_codigo_temp = {v: k for k, v in mapa_cod_nome_temp.items()}
                rank_temp["CD_PROCEDIMENTO"] = rank_temp["NOME_PROCEDIMENTO"].map(nome_para_codigo_temp)
                # Lista de compreensão em vez de concatenar Series com "+": como
                # NOME_PROCEDIMENTO (e CD_PROCEDIMENTO depois do .map() logo acima) ficam em
                # dtype category/arrow, o "+" vetorizado do pandas pode estourar TypeError
                # ("operation 'add' not supported for dtype 'str' with dtype 'category'")
                # dependendo da versão do pandas/pyarrow — inclusive .astype(str)/.map(str)
                # sozinhos não bastam, porque Series.map em coluna category devolve outra
                # category. Iterando com zip(), cada valor já sai como escalar Python comum,
                # então o f-string nunca encosta em operação vetorizada de Series.
                rank_temp["rotulo"] = [
                    f"{int(cod)} — {nome}"
                    for cod, nome in zip(rank_temp["CD_PROCEDIMENTO"], rank_temp["NOME_PROCEDIMENTO"])
                ]

                # ---- base nacional (sem filtro nenhum) por procedimento — referência do "esperado" ----
                # Taxa nacional = qtd_procedimentos ÷ qtd_vidas, calculada sobre `agregado`/`base_usuarios`
                # CRUS (sem nenhum filtro do topo da página) — "quantos procedimentos desse código o
                # Brasil todo faz, por vida". Reaproveita calcular_media_nacional(), que já existe em
                # severidade.py (usada em Desvios de Solicitações) — não mexe em severidade.py.
                nacional_temp = calcular_media_nacional(
                    agregado, "NOME_PROCEDIMENTO", usuarios=base_usuarios
                ).set_index("NOME_PROCEDIMENTO")
                # Versão "achatada" (colunas já renomeadas), usada via merge em vez de laço linha a
                # linha — com todos os procedimentos (em vez dos 13 fixos de antes), o laço python
                # anterior ficaria lento; merge é vetorizado e escala bem mesmo com muitos códigos.
                # Só as 3 colunas necessárias pro merge — calcular_media_nacional() também devolve
                # "quantidade_uso" (entre outras), que colide com a coluna de mesmo nome que
                # ranking_severidade() já põe em rank_temp; sem esse recorte, o merge renomeia as
                # duas pra "quantidade_uso_x"/"quantidade_uso_y" e a coluna "quantidade_uso" some.
                nacional_temp_flat = nacional_temp.reset_index()[
                    ["NOME_PROCEDIMENTO", "qtd_procedimentos", "qtd_usuarios"]
                ].rename(columns={
                    "qtd_procedimentos": "qtd_procedimentos_nacional", "qtd_usuarios": "qtd_vidas_nacional",
                })

                def _base_nacional_temp(nome_proc):
                    if nome_proc not in nacional_temp.index:
                        return float("nan"), float("nan")
                    return (
                        nacional_temp.loc[nome_proc, "qtd_procedimentos"],
                        nacional_temp.loc[nome_proc, "qtd_usuarios"],
                    )

                rank_temp = rank_temp.merge(nacional_temp_flat, on="NOME_PROCEDIMENTO", how="left")

                # ---- FASE (esperado) / QP (praticado) / CS — regra só desta aba ----
                # NÃO mexe em severidade.py: o FASE oficial (Frequência × Intensidade × Peso do
                # grupo, em _fase()) continua do jeito que está no resto do painel.
                #
                #   FASE (esperado)  = (qtd_procedimentos nacional ÷ qtd_vidas nacional) × qtd_vidas
                #                      em utilização deste corte — quantos procedimentos este corte
                #                      "deveria" ter, seguindo a taxa nacional desse procedimento.
                #   QP (praticado) = qtd_procedimentos realmente observados neste corte — direto,
                #                      sem conta nenhuma.
                #   CS (Coeficiente de Severidade) = (QP ÷ FASE) × 10 — 10,000 = praticado igual ao
                #                      esperado pela taxa nacional; acima de 10, mais severo; abaixo
                #                      de 10, menos severo. O ×10 só amplia a escala (a razão sozinha
                #                      fica sempre bem perto de 1) — não muda a ordem entre os
                #                      procedimentos.
                rank_temp["fase_esperado"] = (
                    rank_temp["qtd_procedimentos_nacional"] / rank_temp["qtd_vidas_nacional"]
                ) * rank_temp["qtd_usuarios"]
                rank_temp["qp_praticado"] = rank_temp["qtd_procedimentos"]
                rank_temp["cs"] = (rank_temp["qp_praticado"] / rank_temp["fase_esperado"]) * 10

                # ---- CS Geral: mesmo cálculo, mas sem os filtros de Procedimento/Prestador/
                # UF/Região/Cidade/Cluster desta aba (só com os filtros de página — Mês/Plano/
                # Especialidade/Período) — referência fixa pra comparar ao lado do CS já
                # filtrado, sem precisar tirar o filtro pra ver o "antes".
                usuarios_geral_temp = usuarios_filtrado[usuarios_filtrado["NOME_PROCEDIMENTO"].isin(nomes_temp)]
                rank_geral_temp = ranking_severidade(
                    df_temp_base, "NOME_PROCEDIMENTO", top_n=1_000_000, usuarios=usuarios_geral_temp
                ).copy()
                rank_geral_temp = rank_geral_temp.merge(nacional_temp_flat, on="NOME_PROCEDIMENTO", how="left")
                rank_geral_temp["fase_esperado_geral"] = (
                    rank_geral_temp["qtd_procedimentos_nacional"] / rank_geral_temp["qtd_vidas_nacional"]
                ) * rank_geral_temp["qtd_usuarios"]
                rank_geral_temp["cs_geral"] = (
                    rank_geral_temp["qtd_procedimentos"] / rank_geral_temp["fase_esperado_geral"]
                ) * 10
                rank_temp = rank_temp.merge(
                    rank_geral_temp[["NOME_PROCEDIMENTO", "cs_geral"]], on="NOME_PROCEDIMENTO", how="left"
                )

                # ---- CS da Cidade: mesmo cálculo do CS Geral, mas em vez de tirar TODOS os
                # filtros desta aba, mantém só o recorte de cidade — a cidade escolhida no
                # filtro "Cidade" (se houver) ou, com um prestador específico selecionado e
                # sem cidade escolhida, a cidade onde esse prestador atua (moda de
                # CIDADE_PRESTADOR dentro do recorte já filtrado por prestador). Serve pra
                # comparar o CS de uma clínica/prestador específico com o CS de todo mundo
                # que atua na mesma cidade pra aquele procedimento — sem cidade de
                # referência (nem filtro de Cidade, nem Prestador selecionado), fica "—".
                _cidade_referencia_temp = None
                if cidade_sel_temp != "Todos":
                    _cidade_referencia_temp = cidade_sel_temp
                elif (
                    prest_sel_temp != "Todos"
                    and "CIDADE_PRESTADOR" in df_temp.columns
                    and not df_temp.empty
                ):
                    _moda_cidade_temp = df_temp["CIDADE_PRESTADOR"].mode()
                    if not _moda_cidade_temp.empty:
                        _cidade_referencia_temp = _moda_cidade_temp.iloc[0]

                if (
                    _cidade_referencia_temp is not None
                    and "CIDADE_PRESTADOR" in df_temp_base.columns
                    and "CIDADE_PRESTADOR" in usuarios_filtrado.columns
                ):
                    df_cidade_ref_temp = df_temp_base[
                        df_temp_base["CIDADE_PRESTADOR"] == _cidade_referencia_temp
                    ]
                    usuarios_cidade_ref_temp = usuarios_filtrado[
                        usuarios_filtrado["NOME_PROCEDIMENTO"].isin(nomes_temp)
                        & (usuarios_filtrado["CIDADE_PRESTADOR"] == _cidade_referencia_temp)
                    ]
                    rank_cidade_temp = ranking_severidade(
                        df_cidade_ref_temp, "NOME_PROCEDIMENTO", top_n=1_000_000, usuarios=usuarios_cidade_ref_temp
                    ).copy()
                    rank_cidade_temp = rank_cidade_temp.merge(nacional_temp_flat, on="NOME_PROCEDIMENTO", how="left")
                    rank_cidade_temp["fase_esperado_cidade"] = (
                        rank_cidade_temp["qtd_procedimentos_nacional"] / rank_cidade_temp["qtd_vidas_nacional"]
                    ) * rank_cidade_temp["qtd_usuarios"]
                    rank_cidade_temp["cs_cidade"] = (
                        rank_cidade_temp["qtd_procedimentos"] / rank_cidade_temp["fase_esperado_cidade"]
                    ) * 10
                    rank_temp = rank_temp.merge(
                        rank_cidade_temp[[
                            "NOME_PROCEDIMENTO", "cs_cidade", "qtd_procedimentos", "fase_esperado_cidade",
                        ]].rename(columns={"qtd_procedimentos": "qtd_procedimentos_cidade"}),
                        on="NOME_PROCEDIMENTO", how="left",
                    )
                else:
                    rank_temp["cs_cidade"] = float("nan")
                    rank_temp["qtd_procedimentos_cidade"] = float("nan")
                    rank_temp["fase_esperado_cidade"] = float("nan")

                # ---- coluna com o CS formatado com 3 casas decimais (padrão fmt_float2 usa só 2) ----
                def _fmt_cs_temp(v):
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        return "—"
                    s = f"{v:,.3f}"
                    return s.replace(",", "§").replace(".", ",").replace("§", ".")

                # ---- colunas com a "continha" de cada um: FASE, QP e CS ----
                def _calculo_fase_esperado_temp(qpn, qun, qu_corte):
                    if not qun or pd.isna(qun):
                        return "—"
                    return f"({fmt_int(qpn)} ÷ {fmt_int(qun)}) × {fmt_int(qu_corte)}"

                def _calculo_cs_temp(qp, fase):
                    if not fase or pd.isna(fase):
                        return "—"
                    return f"({fmt_int(qp)} ÷ {fmt_float2(fase)}) × 10"

                rank_temp["calculo_fase_esperado"] = [
                    _calculo_fase_esperado_temp(qpn, qun, qu)
                    for qpn, qun, qu in zip(
                        rank_temp["qtd_procedimentos_nacional"], rank_temp["qtd_vidas_nacional"], rank_temp["qtd_usuarios"]
                    )
                ]
                # "Cálculo do QP" = o próprio valor observado — sem fórmula (o QP não é calculado
                # a partir de outros números, é o número real do corte), mas mantido como coluna
                # separada da "QP" por simetria com "Cálculo do FASE"/"Cálculo do CS".
                rank_temp["calculo_qp"] = [fmt_int(qp) for qp in rank_temp["qp_praticado"]]
                rank_temp["calculo_cs"] = [
                    _calculo_cs_temp(qp, fase)
                    for qp, fase in zip(rank_temp["qp_praticado"], rank_temp["fase_esperado"])
                ]
                # "Cálculo do CS Cidade" — mesma continha do "Cálculo do CS", só que com o QP e
                # o FASE calculados sobre a cidade de referência (todos os prestadores dela),
                # não só o corte desta aba. "—" quando não há cidade de referência (mesma regra
                # de "CS da Cidade" logo acima).
                rank_temp["calculo_cs_cidade"] = [
                    _calculo_cs_temp(qp_cid, fase_cid)
                    for qp_cid, fase_cid in zip(
                        rank_temp["qtd_procedimentos_cidade"], rank_temp["fase_esperado_cidade"]
                    )
                ]

                # ---- ordena a grade por CS decrescente (do mais severo pro menos severo) ----
                rank_temp = rank_temp.sort_values("cs", ascending=False)

                exib_rank_temp = rank_temp.copy()
                exib_rank_temp["qtd_procedimentos"] = exib_rank_temp["qtd_procedimentos"].map(fmt_int)
                exib_rank_temp["qtd_usuarios"] = exib_rank_temp["qtd_usuarios"].map(fmt_int)
                exib_rank_temp["quantidade_uso"] = exib_rank_temp["quantidade_uso"].map(fmt_int)
                exib_rank_temp["uso_por_procedimento"] = exib_rank_temp["uso_por_procedimento"].map(fmt_float2)
                exib_rank_temp["uso_por_vida"] = exib_rank_temp["uso_por_vida"].map(fmt_float2)
                exib_rank_temp["fase_esperado"] = exib_rank_temp["fase_esperado"].map(fmt_float2)
                exib_rank_temp["qp_praticado"] = exib_rank_temp["qp_praticado"].map(fmt_int)
                # CS Geral é sempre a referência "sem os filtros desta aba" — mostra o valor de
                # verdade mesmo quando nenhum_filtro_temp é True (nesse caso ele só coincide
                # com o CS ao lado, já que os dois corte ficam iguais).
                exib_rank_temp["cs_geral"] = exib_rank_temp["cs_geral"].map(_fmt_cs_temp)
                # CS da Cidade segue a mesma regra do CS Geral — mostra o valor de verdade,
                # com "—" só quando não há cidade de referência (função _fmt_cs_temp já cobre
                # o NaN desse caso).
                exib_rank_temp["cs_cidade"] = exib_rank_temp["cs_cidade"].map(_fmt_cs_temp)
                if nenhum_filtro_temp:
                    exib_rank_temp["cs"] = "—"
                    exib_rank_temp["calculo_cs"] = "—"
                else:
                    exib_rank_temp["cs"] = exib_rank_temp["cs"].map(_fmt_cs_temp)
                # "Cálculo do QP"/"QP" ficam de fora quando a aba pede (_mostrar_calculo_qp_temp
                # = False, hoje só a "🔎 SMILE DENTAL") — o resto das colunas é igual pra todas.
                _colunas_exib_rank_temp = [
                    "rotulo", "qtd_procedimentos", "qtd_usuarios", "quantidade_uso",
                    "uso_por_procedimento", "uso_por_vida",
                    "calculo_fase_esperado", "fase_esperado",
                ]
                if _mostrar_calculo_qp_temp:
                    _colunas_exib_rank_temp += ["calculo_qp", "qp_praticado"]
                _colunas_exib_rank_temp += [
                    "calculo_cs", "cs", "cs_geral", "calculo_cs_cidade", "cs_cidade",
                ]
                # Rótulo da 1ª coluna deixa explícito que cada linha já está filtrada pelo
                # prestador travado desta aba (hoje só a "🔎 SMILE DENTAL") — nas demais abas
                # continua "Procedimento" simples, já que lá o Prestador é um filtro livre.
                _rotulo_coluna_procedimento_temp = (
                    "Procedimento por Prestador" if _prestador_fixo_temp is not None else "Procedimento"
                )
                exib_rank_temp = exib_rank_temp[_colunas_exib_rank_temp].rename(columns={
                    "rotulo": _rotulo_coluna_procedimento_temp,
                    "qtd_procedimentos": "Qtde proced",
                    "qtd_usuarios": "Qtd vidas",
                    "quantidade_uso": "Soma de uso",
                    "uso_por_procedimento": "Uso/proced",
                    "uso_por_vida": "Uso/vida",
                    "calculo_fase_esperado": "Cálculo do FASE",
                    "fase_esperado": "FASE",
                    "calculo_qp": "Cálculo do QP",
                    "qp_praticado": "QP",
                    "calculo_cs": "Cálculo do CS",
                    "cs": "CS",
                    "cs_geral": "CS Geral",
                    "calculo_cs_cidade": "Cálculo do CS Cidade",
                    "cs_cidade": "CS da Cidade",
                })
                # Grade montada como tabela HTML própria, em vez de st.dataframe: o widget padrão do
                # Streamlit desenha o conteúdo das células em canvas (glide-data-grid), então CSS de
                # fonte/alinhamento não alcança o texto de dentro das células — só assim dá pra
                # garantir fonte menor e valores centralizados de verdade. Classe própria (não é um
                # <style> genérico), então não mexe em nenhuma outra tabela do painel — reaproveitada
                # (via _tabela_html_temp) pela grade de prestadores logo abaixo também.
                st.markdown(
                    """
                    <style>
                    .grade-cs-temp-wrap { overflow-x: auto; }
                    .grade-cs-temp-wrap-scroll { overflow-x: auto; overflow-y: auto; max-height: 165px; }
                    .grade-cs-temp { border-collapse: collapse; width: 100%; font-size: 12px; }
                    .grade-cs-temp th, .grade-cs-temp td {
                        text-align: center !important; padding: 4px 8px; white-space: nowrap;
                        border-bottom: 1px solid rgba(128, 128, 128, 0.3);
                    }
                    .grade-cs-temp th:first-child, .grade-cs-temp td:first-child {
                        text-align: left !important;
                        max-width: 260px; overflow: hidden; text-overflow: ellipsis;
                    }
                    .grade-cs-temp th { font-weight: 600; }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

                def _tabela_html_temp(df_exibicao, scroll=False):
                    cabecalho = "".join(f"<th>{html.escape(str(c))}</th>" for c in df_exibicao.columns)
                    def _linha_html(linha):
                        celulas = []
                        for i, v in enumerate(linha):
                            texto = html.escape(str(v))
                            # 1ª coluna trunca com "..." (max-width no CSS) — title= mostra o
                            # texto inteiro ao passar o mouse, já que a célula corta visualmente.
                            titulo_attr = f' title="{texto}"' if i == 0 else ""
                            celulas.append(f"<td{titulo_attr}>{texto}</td>")
                        return "<tr>" + "".join(celulas) + "</tr>"
                    linhas = "".join(_linha_html(linha) for linha in df_exibicao.itertuples(index=False, name=None))
                    classe_wrap = "grade-cs-temp-wrap-scroll" if scroll else "grade-cs-temp-wrap"
                    st.markdown(
                        f"""
                        <div class="{classe_wrap}">
                        <table class="grade-cs-temp">
                        <thead><tr>{cabecalho}</tr></thead>
                        <tbody>{linhas}</tbody>
                        </table>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # A grade volta a aparecer sozinha assim que um prestador específico é
                # selecionado (a flag no topo do arquivo só força ela sempre visível, mesmo
                # sem prestador selecionado, se religada pra True).
                _mostrar_grade_cs_temp = MOSTRAR_GRADE_CS_PROCEDIMENTO_TEMP or prest_sel_temp != "Todos"
                if _mostrar_grade_cs_temp:
                    _tabela_html_temp(exib_rank_temp, scroll=True)

                # ---- prestadores do procedimento selecionado, com FASE/QP/CS por prestador ----
                # Só aparece quando um procedimento específico está selecionado no filtro acima (com
                # "Todos" não faz sentido — a tabela ficaria com todo mundo que atendeu qualquer um
                # dos 13 códigos misturado). Também não aparece se um prestador específico já estiver
                # selecionado, porque aí a grade principal acima já é a linha desse único prestador —
                # mostrar de novo seria redundante.
                if cod_sel_temp is not None and prest_sel_temp == "Todos":
                    st.divider()
                    nome_proc_sel_temp = mapa_cod_nome_temp.get(cod_sel_temp)
                    st.markdown(f"**Prestadores — {cod_sel_temp} — {nome_proc_sel_temp}**")

                    rank_prestador_temp = ranking_severidade(
                        df_temp, "CD_PRESTADOR", top_n=1_000_000, usuarios=usuarios_temp
                    ).copy()
                    if rank_prestador_temp.empty:
                        st.info("Nenhum prestador encontrado para esse procedimento nos filtros atuais.")
                    else:
                        # Mesma taxa nacional já usada na grade principal (constante por
                        # procedimento) — só muda a base de "vidas em utilização", que aqui é por
                        # prestador em vez de por corte inteiro.
                        _qpn_prest, _qun_prest = _base_nacional_temp(nome_proc_sel_temp)
                        _taxa_nac_prest = (_qpn_prest / _qun_prest) if _qun_prest else float("nan")
                        rank_prestador_temp["fase_esperado"] = _taxa_nac_prest * rank_prestador_temp["qtd_usuarios"]
                        rank_prestador_temp["qp_praticado"] = rank_prestador_temp["qtd_procedimentos"]
                        rank_prestador_temp["cs"] = (
                            rank_prestador_temp["qp_praticado"] / rank_prestador_temp["fase_esperado"]
                        ) * 10
                        rank_prestador_temp = rank_prestador_temp.sort_values("cs", ascending=False)

                        _col_nome_prest = (
                            "NOME_PRESTADOR" if "NOME_PRESTADOR" in rank_prestador_temp.columns else "CD_PRESTADOR"
                        )

                        # ---- Cidade/UF/Cluster de cada prestador (moda — mesmo critério do hover
                        # dos gráficos de dispersão) — só informativo, não entra em nenhuma conta;
                        # juntado ao nome do prestador num rótulo só, não em colunas separadas. ----
                        _colunas_info_prest_temp = [
                            c for c in ("CIDADE_PRESTADOR", "UF", "CLUSTER") if c in df_temp.columns
                        ]
                        if _colunas_info_prest_temp:
                            _info_extra_prest_temp = df_temp.groupby("CD_PRESTADOR", observed=True).agg(**{
                                c: (c, lambda x: x.mode().iloc[0] if not x.mode().empty else "—")
                                for c in _colunas_info_prest_temp
                            }).reset_index()
                            rank_prestador_temp = rank_prestador_temp.merge(
                                _info_extra_prest_temp, on="CD_PRESTADOR", how="left"
                            )
                        for c in ("CIDADE_PRESTADOR", "UF", "CLUSTER"):
                            if c not in rank_prestador_temp.columns:
                                rank_prestador_temp[c] = "—"
                            rank_prestador_temp[c] = rank_prestador_temp[c].fillna("—")

                        rank_prestador_temp["rotulo_prestador"] = [
                            f"{nome_fmt} - {uf} - {cidade} - {cluster}"
                            for nome_fmt, uf, cidade, cluster in zip(
                                [
                                    str(nome) if pd.notna(nome) and str(nome).strip() else f"Prestador {int(cod)}"
                                    for cod, nome in zip(
                                        rank_prestador_temp["CD_PRESTADOR"], rank_prestador_temp[_col_nome_prest]
                                    )
                                ],
                                rank_prestador_temp["UF"], rank_prestador_temp["CIDADE_PRESTADOR"],
                                rank_prestador_temp["CLUSTER"],
                            )
                        ]

                        # Mesmas "continhas" da grade principal, agora reaproveitadas aqui — cada
                        # prestador funciona como um "corte" à parte, mas comparado com a mesma taxa
                        # nacional desse procedimento.
                        rank_prestador_temp["calculo_fase_esperado"] = [
                            _calculo_fase_esperado_temp(_qpn_prest, _qun_prest, qu)
                            for qu in rank_prestador_temp["qtd_usuarios"]
                        ]
                        rank_prestador_temp["calculo_qp"] = [
                            fmt_int(qp) for qp in rank_prestador_temp["qp_praticado"]
                        ]
                        rank_prestador_temp["calculo_cs"] = [
                            _calculo_cs_temp(qp, fase)
                            for qp, fase in zip(
                                rank_prestador_temp["qp_praticado"], rank_prestador_temp["fase_esperado"]
                            )
                        ]

                        exib_prestador_temp = rank_prestador_temp.copy()
                        exib_prestador_temp["qtd_procedimentos"] = exib_prestador_temp["qtd_procedimentos"].map(fmt_int)
                        exib_prestador_temp["qtd_usuarios"] = exib_prestador_temp["qtd_usuarios"].map(fmt_int)
                        exib_prestador_temp["quantidade_uso"] = exib_prestador_temp["quantidade_uso"].map(fmt_int)
                        exib_prestador_temp["uso_por_procedimento"] = exib_prestador_temp["uso_por_procedimento"].map(fmt_float2)
                        exib_prestador_temp["uso_por_vida"] = exib_prestador_temp["uso_por_vida"].map(fmt_float2)
                        exib_prestador_temp["fase_esperado"] = exib_prestador_temp["fase_esperado"].map(fmt_float2)
                        exib_prestador_temp["qp_praticado"] = exib_prestador_temp["qp_praticado"].map(fmt_int)
                        exib_prestador_temp["cs"] = exib_prestador_temp["cs"].map(_fmt_cs_temp)
                        exib_prestador_temp = exib_prestador_temp[[
                            "rotulo_prestador",
                            "qtd_procedimentos", "qtd_usuarios", "quantidade_uso",
                            "uso_por_procedimento", "uso_por_vida",
                            "calculo_fase_esperado", "fase_esperado",
                            "calculo_qp", "qp_praticado",
                            "calculo_cs", "cs",
                        ]].rename(columns={
                            "rotulo_prestador": "Prestador",
                            "qtd_procedimentos": "Qtde proced",
                            "qtd_usuarios": "Qtd vidas",
                            "quantidade_uso": "Soma de uso",
                            "uso_por_procedimento": "Uso/proced",
                            "uso_por_vida": "Uso/vida",
                            "calculo_fase_esperado": "Cálculo do FASE",
                            "fase_esperado": "FASE",
                            "calculo_qp": "Cálculo do QP",
                            "qp_praticado": "QP",
                            "calculo_cs": "Cálculo do CS",
                            "cs": "CS",
                        })
                        _tabela_html_temp(exib_prestador_temp, scroll=True)
                # ---- dispersão CS × volume: onde estão as severidades (outliers) ----
                # Substitui os gráficos de barra/evolução mensal desta aba (removidos a pedido).
                # Objetivo: achar procedimentos, prestadores e cidades com CS alto que sejam um
                # padrão de verdade (muito volume) e não ruído de amostra pequena (pouco volume).
                st.divider()
                st.markdown("**Onde estão as severidades — dispersão CS × volume**")
                st.caption(
                    "Cada ponto é um procedimento, prestador ou cidade. Eixo X = qtd de vidas em "
                    "utilização (escala log, pra caber quem tem muita e pouca vida no mesmo "
                    "gráfico); eixo Y = CS; tamanho do ponto = qtd de procedimentos. Linha "
                    "pontilhada em CS = 10 (praticado igual ao esperado). Ponto acima da linha e "
                    "bem à direita (muito volume) é o sinal mais confiável de severidade real — "
                    "acima da linha mas bem à esquerda (pouco volume) pode ser só instabilidade de "
                    "amostra pequena, não um padrão (passe o mouse pra ver os números de cada ponto)."
                )

                if nenhum_filtro_temp:
                    st.info(
                        "Selecione ao menos um filtro acima (procedimento, prestador, UF, "
                        "região, cidade ou cluster) para ver a dispersão de severidade — sem "
                        "nenhum filtro, o corte comparado se aproxima da própria base nacional "
                        "e o CS fica pouco informativo."
                    )
                else:
                    def _info_extra_temp(coluna_dimensao, colunas_extra):
                        """Atributo mais frequente (moda) de cada `coluna_dimensao` — ex.: cidade/UF/
                        cluster de cada prestador — só pra enriquecer o hover dos gráficos, não entra
                        em nenhum cálculo de FASE/QP/CS."""
                        colunas_presentes = [c for c in colunas_extra if c in df_temp.columns]
                        if not colunas_presentes:
                            return pd.DataFrame()
                        agregacoes = {
                            c: (c, lambda x: x.mode().iloc[0] if not x.mode().empty else "—")
                            for c in colunas_presentes
                        }
                        return df_temp.groupby(coluna_dimensao, observed=True).agg(**agregacoes).reset_index()

                    def _severidade_agregada_temp(coluna_dimensao, colunas_extra=None):
                        """
                        FASE/QP/CS por `coluna_dimensao` (ex.: CD_PRESTADOR, CIDADE_PRESTADOR),
                        somando entre TODOS os procedimentos desta aba. A taxa nacional de cada
                        procedimento é constante — aplicada às vidas em utilização daquele
                        procedimento dentro de cada grupo da dimensão — e só depois de somar FASE e
                        QP entre os procedimentos é que o CS final do grupo é calculado. Não é uma
                        média dos CS de cada procedimento (isso não pesaria pelo volume de cada um).
                        `colunas_extra` são atributos descritivos (cidade, UF, cluster) trazidos à
                        parte, pela moda de cada grupo, só pra hover — não afetam o cálculo.
                        """
                        grupo_cols = [coluna_dimensao, "NOME_PROCEDIMENTO"]
                        extra_cols = ["NOME_PRESTADOR"] if (
                            coluna_dimensao == "CD_PRESTADOR" and "NOME_PRESTADOR" in df_temp.columns
                        ) else []
                        base = df_temp.groupby(grupo_cols + extra_cols, dropna=False, observed=True).agg(
                            qtd_procedimentos=("qtd_procedimentos", "sum"),
                        ).reset_index()
                        base = base[base[coluna_dimensao].notna() & base["NOME_PROCEDIMENTO"].notna()]
                        if base.empty:
                            return pd.DataFrame()
                        vidas_cel = vidas_por(usuarios_temp, grupo_cols)
                        base = base.merge(vidas_cel, on=grupo_cols, how="left")
                        base["qtd_usuarios"] = base["qtd_usuarios"].fillna(0)
                        # Merge vetorizado (em vez de laço linha a linha) — com todos os procedimentos,
                        # essa base pode ter muito mais linhas do que quando eram só 13 códigos fixos.
                        base = base.merge(nacional_temp_flat, on="NOME_PROCEDIMENTO", how="left")
                        base["fase_esperado"] = (
                            base["qtd_procedimentos_nacional"] / base["qtd_vidas_nacional"]
                        ) * base["qtd_usuarios"]
                        base["qp_praticado"] = base["qtd_procedimentos"]

                        group_final = [coluna_dimensao] + extra_cols
                        resultado = base.groupby(group_final, dropna=False, observed=True).agg(
                            fase_esperado=("fase_esperado", "sum"),
                            qp_praticado=("qp_praticado", "sum"),
                        ).reset_index()
                        vidas_total = vidas_por(usuarios_temp, coluna_dimensao)
                        resultado = resultado.merge(vidas_total, on=coluna_dimensao, how="left")
                        resultado["qtd_usuarios"] = resultado["qtd_usuarios"].fillna(0)
                        resultado = resultado[resultado["fase_esperado"] > 0]
                        resultado["cs"] = (resultado["qp_praticado"] / resultado["fase_esperado"]) * 10

                        info_extra = _info_extra_temp(coluna_dimensao, colunas_extra or [])
                        if not info_extra.empty:
                            resultado = resultado.merge(info_extra, on=coluna_dimensao, how="left")
                        return resultado

                    _rotulos_hover_temp = {
                        "qtd_usuarios": "Qtd vidas", "qp_praticado": "Qtd procedimentos", "cs": "CS",
                        "CIDADE_PRESTADOR": "Cidade", "UF": "UF", "CLUSTER": "Cluster",
                    }

                    def _grafico_dispersao_cs_temp(dados, rotulo_col, titulo, hover_extra=None):
                        if dados is None or dados.empty or "qtd_usuarios" not in dados.columns:
                            st.info(f"Sem dados suficientes para o gráfico de {titulo.lower()}.")
                            return
                        dados_plot = dados[(dados["qtd_usuarios"] > 0) & dados["cs"].notna()].copy()
                        if dados_plot.empty:
                            st.info(f"Sem dados suficientes para o gráfico de {titulo.lower()}.")
                            return
                        hover_data = {"qtd_usuarios": ":,.0f", "qp_praticado": ":,.0f", "cs": ":.3f"}
                        for col in (hover_extra or []):
                            if col in dados_plot.columns:
                                dados_plot[col] = dados_plot[col].fillna("—")
                                hover_data[col] = True
                        fig = px.scatter(
                            dados_plot, x="qtd_usuarios", y="cs", size="qp_praticado", color="cs",
                            color_continuous_scale=["#2ecc71", "#f1c40f", "#e74c3c"],
                            color_continuous_midpoint=10, size_max=32, hover_name=rotulo_col,
                            hover_data=hover_data, labels=_rotulos_hover_temp,
                            log_x=True, title=titulo,
                        )
                        fig.add_hline(y=10, line_dash="dash", line_color="#888")
                        fig.update_layout(
                            height=280, margin=dict(l=10, r=10, t=40, b=10),
                            coloraxis_showscale=False, xaxis_title="Qtd vidas (escala log)", yaxis_title="CS",
                        )
                        # key único (por aba + título do gráfico) — evita colisão de ID quando o
                        # mesmo gráfico é desenhado duas vezes (uma por aba, no laço que reusa
                        # este bloco pra "Coeficiente de Severidade" e pra aba legada de 13 códigos).
                        st.plotly_chart(
                            fig, use_container_width=True,
                            key=f"grafico_disp_temp_{titulo}{_sufixo_aba_temp}",
                        )

                    df_disp_prest_temp = _severidade_agregada_temp(
                        "CD_PRESTADOR", colunas_extra=["CIDADE_PRESTADOR", "UF", "CLUSTER"]
                    )
                    if not df_disp_prest_temp.empty:
                        col_nome_disp_prest = (
                            "NOME_PRESTADOR" if "NOME_PRESTADOR" in df_disp_prest_temp.columns else "CD_PRESTADOR"
                        )
                        df_disp_prest_temp["rotulo"] = [
                            str(nome) if pd.notna(nome) and str(nome).strip() else f"Prestador {int(cod)}"
                            for cod, nome in zip(
                                df_disp_prest_temp["CD_PRESTADOR"], df_disp_prest_temp[col_nome_disp_prest]
                            )
                        ]

                    df_disp_cidade_temp = _severidade_agregada_temp(
                        "CIDADE_PRESTADOR", colunas_extra=["UF", "CLUSTER"]
                    )
                    if not df_disp_cidade_temp.empty:
                        df_disp_cidade_temp["rotulo"] = df_disp_cidade_temp["CIDADE_PRESTADOR"].astype(str)

                    col_disp_prest, col_disp_cidade = st.columns(2)
                    with col_disp_prest:
                        _grafico_dispersao_cs_temp(
                            df_disp_prest_temp, "rotulo", "Prestadores",
                            hover_extra=["CIDADE_PRESTADOR", "UF", "CLUSTER"],
                        )
                    with col_disp_cidade:
                        _grafico_dispersao_cs_temp(
                            df_disp_cidade_temp, "rotulo", "Cidades",
                            hover_extra=["UF", "CLUSTER"],
                        )

                    # ---- gráficos fixos de Região, UF, Cluster e Especialidade ----
                    # Quando o próprio filtro dessa dimensão está acionado (um valor específico
                    # escolhido, em vez de "Todos"/nenhum selecionado), não faz sentido mostrar a
                    # dispersão dela — o corte já está fixo num único valor. Nesse caso o gráfico
                    # fica em branco (nem título, nem "sem dados"); os outros 3 continuam batendo
                    # normal, já que já vêm calculados em cima de df_temp/usuarios_temp, que já
                    # respeitam esse (e qualquer outro) filtro ativo.
                    regiao_ativo_temp = regiao_sel_temp != "Todos"
                    uf_ativo_temp = uf_sel_temp != "Todos"
                    cluster_ativo_temp = cluster_sel_temp != "Todos"
                    especialidade_ativo_temp = bool(f_especialidade)

                    col_disp_regiao, col_disp_uf, col_disp_cluster, col_disp_esp = st.columns(4)
                    with col_disp_regiao:
                        if not regiao_ativo_temp and "REGIAO" in df_temp.columns:
                            df_disp_regiao_temp = _severidade_agregada_temp("REGIAO")
                            if not df_disp_regiao_temp.empty:
                                df_disp_regiao_temp["rotulo"] = df_disp_regiao_temp["REGIAO"].astype(str)
                            _grafico_dispersao_cs_temp(df_disp_regiao_temp, "rotulo", "Região")
                    with col_disp_uf:
                        if not uf_ativo_temp and "UF" in df_temp.columns:
                            df_disp_uf_temp = _severidade_agregada_temp("UF")
                            if not df_disp_uf_temp.empty:
                                df_disp_uf_temp["rotulo"] = df_disp_uf_temp["UF"].astype(str)
                            _grafico_dispersao_cs_temp(df_disp_uf_temp, "rotulo", "UF")
                    with col_disp_cluster:
                        if not cluster_ativo_temp and "CLUSTER" in df_temp.columns:
                            df_disp_cluster_temp = _severidade_agregada_temp("CLUSTER")
                            if not df_disp_cluster_temp.empty:
                                df_disp_cluster_temp["rotulo"] = df_disp_cluster_temp["CLUSTER"].astype(str)
                            _grafico_dispersao_cs_temp(df_disp_cluster_temp, "rotulo", "Cluster")
                    with col_disp_esp:
                        if not especialidade_ativo_temp and "ESPECIALIDADE" in df_temp.columns:
                            df_disp_esp_temp = _severidade_agregada_temp("ESPECIALIDADE")
                            if not df_disp_esp_temp.empty:
                                df_disp_esp_temp["rotulo"] = df_disp_esp_temp["ESPECIALIDADE"].astype(str)
                            _grafico_dispersao_cs_temp(df_disp_esp_temp, "rotulo", "Especialidade")

                # ---- histórico por mês: CS, qtd de vidas, qtd de procedimentos, soma de uso ----
                # Mesma exigência de "pelo menos 1 filtro acionado" do bloco de dispersão acima —
                # sem filtro, o corte se aproxima da própria base nacional e a série mês a mês
                # fica pouco informativa.
                st.divider()
                st.markdown("**Histórico por mês**")
                if nenhum_filtro_temp:
                    st.info(
                        "Selecione ao menos um filtro acima (procedimento, prestador, UF, região, "
                        "cidade ou cluster) para ver o histórico por mês."
                    )
                elif "MES" not in df_temp.columns:
                    st.info("Sem coluna de mês nos dados pra montar o histórico.")
                else:
                    metrica_hist_temp = st.selectbox(
                        "Métrica do histórico",
                        ["CS", "Qtd de vidas", "Qtd de procedimentos", "Soma de uso"],
                        key=f"temp_hist_metrica{_sufixo_aba_temp}",
                    )
                    # CS/qtd de vidas/qtd de procedimentos por mês vêm do mesmo agregador usado nos
                    # gráficos de dispersão acima, só que agrupando por MES em vez de prestador/
                    # cidade/etc. Soma de uso não faz parte desse cálculo (não entra na fórmula do
                    # CS), então é somada à parte, direto de df_temp.
                    df_hist_temp = _severidade_agregada_temp("MES")
                    soma_uso_mes_temp = (
                        df_temp.groupby("MES", dropna=False, observed=True)["soma_uso"]
                        .sum().rename("soma_uso_mes").reset_index()
                    )
                    if not df_hist_temp.empty:
                        df_hist_temp = df_hist_temp.merge(soma_uso_mes_temp, on="MES", how="outer")
                    else:
                        df_hist_temp = soma_uso_mes_temp.copy()
                        for _col_vazia in ("cs", "qtd_usuarios", "qp_praticado"):
                            df_hist_temp[_col_vazia] = float("nan")
                    df_hist_temp = df_hist_temp[df_hist_temp["MES"].notna()]
                    if df_hist_temp.empty:
                        st.info("Sem dados suficientes para o histórico.")
                    else:
                        df_hist_temp = df_hist_temp.sort_values("MES")
                        df_hist_temp["mes_rotulo"] = df_hist_temp["MES"].map(label_mes)
                        _col_metrica_hist_temp = {
                            "CS": "cs", "Qtd de vidas": "qtd_usuarios",
                            "Qtd de procedimentos": "qp_praticado", "Soma de uso": "soma_uso_mes",
                        }[metrica_hist_temp]
                        fig_hist_temp = px.line(
                            df_hist_temp, x="mes_rotulo", y=_col_metrica_hist_temp, markers=True,
                            title=f"{metrica_hist_temp} por mês",
                        )
                        if metrica_hist_temp == "CS":
                            fig_hist_temp.add_hline(y=10, line_dash="dash", line_color="#888")
                        fig_hist_temp.update_layout(
                            height=320, margin=dict(l=10, r=10, t=40, b=10),
                            xaxis_title="Mês", yaxis_title=metrica_hist_temp,
                        )
                        st.plotly_chart(
                            fig_hist_temp, use_container_width=True,
                            key=f"grafico_hist_temp{_sufixo_aba_temp}",
                        )
