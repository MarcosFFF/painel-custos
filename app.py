import streamlit as st
import pandas as pd
import html
import os
import io
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
        carregar_base_severidade, aplicar_filtros,
        ranking_severidade,
        resumo_comparativo, alertas_prestador_procedimento,
        calcular_media_nacional, vidas_por,
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
def enviar_email_resumo_ranking_temp(destinatarios, periodo_texto, ranqueado_por_texto,
                                      filtros_texto, partes_resumo_html):
    """E-mail pontual com o 'Resumo — o que chama a atenção' da aba Ranking (texto, sem
    anexo) — mesmas credenciais/servidor SMTP de enviar_email_projecao, mas destinatários
    vêm do campo na tela (não do EMAIL_DESTINATARIO fixo dos Secrets), porque esse resumo
    muda de gente a depender do filtro aplicado (ex.: gestor de uma UF específica)."""
    try:
        remetente = st.secrets["EMAIL_REMETENTE"]
        senha = st.secrets["EMAIL_SENHA_APP"]
        smtp_host = st.secrets.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("EMAIL_SMTP_PORT", 587))
    except KeyError as e:
        return False, f"Faltou configurar o segredo {e} em Settings → Secrets do Streamlit Cloud."
    if not destinatarios:
        return False, "Informe pelo menos um e-mail de destino válido."
    _corpo_partes_temp = [
        '<p style="margin:0 0 10px 0;"><strong>Resumo do Ranking — Odonto</strong></p>',
        (
            '<p style="margin:0 0 10px 0;">'
            f"Período: {html.escape(periodo_texto)}<br>"
            f"Ranqueado por: {html.escape(ranqueado_por_texto)}<br>"
            f"Filtros: {html.escape(filtros_texto)}</p>"
        ),
    ]
    _corpo_partes_temp += [f'<p style="margin:0 0 8px 0;">{p}</p>' for p in partes_resumo_html]
    corpo_html = (
        '<div style="font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#1a1a1a;">'
        + "".join(_corpo_partes_temp) + "</div>"
    )
    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = f"Resumo do Ranking - Odonto"
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
    # Quadro "Filtros" do topo da página (Mês/Região/Plano/UF/Especialidade/Cluster/Cidade +
    # volume mínimo) fica oculto — Mês/Plano/Especialidade continuam funcionando do mesmo
    # jeito (mesmo efeito sobre df_filtrado/usuarios_filtrado), só que os campos aparecem
    # agora dentro da aba "📊 Ranking"; Região/UF/Cluster/Cidade da página ficam sem filtro
    # próprio (já têm equivalente dentro da aba Ranking) e o volume mínimo volta pro padrão
    # antigo
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
    agregado, base_usuarios, aviso_carga = carregar_base_severidade(".")
    if agregado is None:
        st.error(f"Não consegui carregar os dados de severidade: {aviso_carga}")
        st.stop()
    if aviso_carga:
        st.warning(aviso_carga)
    # ---------- filtros ----------
    # Opções sempre calculadas (servem tanto pro quadro original, se reativado, quanto pros
    # campos de Mês/Plano/Especialidade agora dentro da aba Ranking).
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
    # dentro da aba Ranking, que filtra em cima do resultado destes.
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
    # Sequência das abas: Ranking, Projeção, Resumo.
    _labels_abas_temp = ["📊 Ranking", "📍 Projeção de Credenciamento", "Resumo"]
    _abas_criadas_temp = st.tabs(_labels_abas_temp)
    tab_ranking_temp, tab_credenciamento, tab_resumo = (
        _abas_criadas_temp[0], _abas_criadas_temp[1], _abas_criadas_temp[2],
    )
    # (tab_obj, título exibido, lista de códigos que restringe a aba — None = todos os
    # procedimentos, sufixo pra deixar as keys dos widgets únicas por aba, nome do prestador
    # travado por padrão no filtro Prestador dessa aba — None = sem trava, nenhum, mostra as
    # colunas Cálculo do QP/QP — True mostra, False esconde) — o corpo da aba (logo abaixo)
    # roda uma vez por item desta lista; hoje só a "📊 Ranking" usa esse corpo.
    _config_abas_cs_temp = [
        (tab_ranking_temp, "📊 Ranking", None, "_ranking", None, False),
    ]
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
    # Corpo da aba "📊 Ranking" — desenhado num loop (ver _config_abas_cs_temp acima) que
    # reaproveita o mesmo código pra qualquer aba que venha a entrar nessa lista no futuro.
    # ============================================================
    for (
        _tab_obj_cs_temp, _titulo_aba_temp, _codigos_restritos_temp, _sufixo_aba_temp,
        _prestador_fixo_temp, _mostrar_calculo_qp_temp,
    ) in _config_abas_cs_temp:
        with _tab_obj_cs_temp:
            st.markdown(f"#### {_titulo_aba_temp}")

            if _sufixo_aba_temp == "_ranking":
                st.caption(
                    "Cada LINHA aqui é um prestador (não um procedimento) — soma todos os "
                    "procedimentos que ele faz dentro dos filtros atuais (Procedimento, "
                    "Prestador, UF, Região, Cidade, Cluster). \"Qtde por prestador Nacional/"
                    "Cidade\", FASE, CS e CS da Cidade são somados procedimento a "
                    "procedimento (cada um com sua própria taxa nacional) e só depois viram "
                    "um número só por prestador — não é média dos procedimentos. \"Qtde por "
                    "prestador - Cidade\"/\"CS da Cidade\" comparam cada prestador com a "
                    "PRÓPRIA cidade dele (cada linha pode ser de uma cidade diferente). Use "
                    "\"Ranquear por\" (abaixo dos filtros) pra reordenar a grade pela métrica "
                    "que interessar — sempre do maior pro menor."
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

            # ---- cada filtro com seu próprio "✕ limpar" embaixo, em vez de um botão só que
            # limpa tudo de uma vez — apaga só a key desse campo específico do session_state e
            # força um rerun; sem a key, o widget volta pro valor padrão dele ("Todos" no
            # selectbox, lista vazia no multiselect) já na próxima rodada. Não dá pra só
            # reatribuir o valor aqui porque o widget já foi instanciado nesta mesma rodada —
            # Streamlit não permite mudar o valor de um widget já criado sem passar pelo
            # session_state + rerun. Campo e botão ficam na MESMA coluna, um embaixo do
            # outro (nada de coluna extra pro botão) — assim o botão não fica espremido
            # numa coluna estreita demais pro texto/ícone aparecer (era isso que deixava
            # ele com cara de "vazio"), e continua pequeno porque não usa
            # use_container_width (o botão só ocupa o espaço do próprio conteúdo, não a
            # largura toda da coluna). Definidas aqui (antes do primeiro uso, no bloco de
            # Mês/Plano/Especialidade logo abaixo) e reaproveitadas também nos 6 filtros da
            # aba e no "Ranquear por" mais adiante.
            def _selectbox_com_limpar_temp(coluna, label, opcoes, chave):
                with coluna:
                    valor = st.selectbox(label, opcoes, key=chave)
                    if st.button(
                        "🧹 limpar", key=f"limpar_campo_temp_{chave}", help="Limpar este filtro"
                    ):
                        st.session_state.pop(chave, None)
                        st.rerun()
                return valor

            def _multiselect_com_limpar_temp(coluna, label, opcoes, chave):
                with coluna:
                    valor = st.multiselect(label, options=opcoes, key=chave)
                    if st.button(
                        "🧹 limpar", key=f"limpar_campo_temp_{chave}", help="Limpar este filtro"
                    ):
                        st.session_state.pop(chave, None)
                        st.rerun()
                return valor

            if not MOSTRAR_FILTROS_TOPO and _sufixo_aba_temp == "_ranking":
                # Mês/Plano/Especialidade do quadro de Filtros do topo (hoje oculto) — mesma
                # funcionalidade de antes (afetam df_filtrado/usuarios_filtrado, a página toda),
                # só que os campos agora aparecem aqui, dentro da aba "📊 Ranking". O valor já
                # foi lido do session_state mais acima (antes de df_filtrado ser montado);
                # declarar o widget aqui só sincroniza a próxima interação do usuário, não
                # afeta o resultado já calculado nesta rodada.
                # Desenhado só na aba Ranking (identificada pelo sufixo "_ranking") — evita
                # campo duplicado, já que Mês/Plano/Especialidade são únicos pra página toda,
                # não por aba.
                fmt1, fmt2, fmt3 = st.columns(3)
                _multiselect_com_limpar_temp(fmt1, "Mês", opcoes_mes_temp, "temp_filtro_mes")
                _multiselect_com_limpar_temp(fmt2, "Plano", opcoes_plano_temp, "temp_filtro_plano")
                _multiselect_com_limpar_temp(
                    fmt3, "Especialidade", opcoes_especialidade_temp, "temp_filtro_especialidade"
                )

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

                # ---- trava o filtro Prestador desta aba num prestador fixo (nenhuma aba usa
                # isso hoje — _prestador_fixo_temp vem None em todas; fica pronto caso alguma
                # aba futura precise) — precisa rodar ANTES do st.selectbox correspondente ser
                # instanciado (Streamlit só aceita pré-setar o session_state de uma key antes do
                # widget dessa key existir nesta rodada). Comparação por substring maiúscula pra
                # tolerar pequena diferença de acentuação/espaço no nome cadastrado na base. Só
                # roda na primeira vez que a aba aparece nesta sessão — depois disso a key já
                # existe no session_state e o usuário fica livre pra trocar de prestador (ou
                # limpar com o "✕ limpar" do campo Prestador, que apaga a key e faz a trava
                # valer de novo).
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

                # ---- cada filtro com seu próprio "🧹 limpar" embaixo, em vez de um botão só
                # que limpa tudo de uma vez — _selectbox_com_limpar_temp já foi definida mais
                # acima (antes do bloco Mês/Plano/Especialidade), reaproveitada aqui. 1 coluna
                # por filtro (o botão fica na mesma coluna do campo, embaixo dele).
                (
                    fc_proc_temp, fc_prest_temp, fc_uf_temp,
                    fc_regiao_temp, fc_cidade_temp, fc_cluster_temp,
                ) = st.columns(6)
                proc_sel_temp = _selectbox_com_limpar_temp(
                    fc_proc_temp, "Procedimento", opcoes_proc_temp, f"temp_filtro_procedimento{_sufixo_aba_temp}"
                )
                prest_sel_temp = _selectbox_com_limpar_temp(
                    fc_prest_temp, "Prestador", opcoes_prestador_temp, f"temp_filtro_prestador{_sufixo_aba_temp}"
                )
                uf_sel_temp = _selectbox_com_limpar_temp(
                    fc_uf_temp, "UF", opcoes_uf_temp, f"temp_filtro_uf{_sufixo_aba_temp}"
                )
                regiao_sel_temp = _selectbox_com_limpar_temp(
                    fc_regiao_temp, "Região", opcoes_regiao_temp, f"temp_filtro_regiao{_sufixo_aba_temp}"
                )
                cidade_sel_temp = _selectbox_com_limpar_temp(
                    fc_cidade_temp, "Cidade", opcoes_cidade_temp, f"temp_filtro_cidade{_sufixo_aba_temp}"
                )
                cluster_sel_temp = _selectbox_com_limpar_temp(
                    fc_cluster_temp, "Cluster", opcoes_cluster_temp, f"temp_filtro_cluster{_sufixo_aba_temp}"
                )

                # ---- "Ranquear por" — só na aba "📊 Ranking": reordena a grade pela métrica
                # escolhida (sempre do maior pro menor), em vez do CS decrescente fixo usado
                # nas outras abas. As chaves do dicionário são os mesmos nomes internos de
                # coluna já calculados mais abaixo em rank_temp — reaproveitados no
                # .sort_values() logo antes de montar a grade de exibição. ----
                if _sufixo_aba_temp == "_ranking":
                    _OPCOES_RANQUEAR_TEMP = {
                        "Qtde de vidas": "qtd_usuarios",
                        "Qtde de procedimentos": "qtd_procedimentos",
                        "Qtde por prestador (Nacional)": "qtd_por_prestador_nacional",
                        "Qtde por prestador (Cidade)": "qtd_por_prestador_cidade",
                        "FASE": "fase_esperado",
                        "CS": "cs",
                        "CS da Cidade": "cs_cidade",
                        "Índice de Atenção (Volume)": "indice_atencao_volume",
                    }
                    fc_ranquear_temp, _fc_ranquear_vazio_temp = st.columns([2, 4])
                    ranquear_por_temp = _selectbox_com_limpar_temp(
                        fc_ranquear_temp, "Ranquear por", list(_OPCOES_RANQUEAR_TEMP.keys()),
                        f"temp_ranquear_por{_sufixo_aba_temp}",
                    )

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
                # A aba "📊 Ranking" pede a grade agrupada por PRESTADOR, não por procedimento —
                # rank_temp é montado logo abaixo, já com o cálculo de FASE/CS/Qtde-por-prestador,
                # depois de ter a base nacional (nacional_temp_flat) pronta.

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
                # Qtde de prestadores distintos (Brasil todo, sem filtro nenhum) que fazem cada
                # procedimento — junto com qtd_procedimentos_nacional acima, dá pra calcular
                # "Qtde por prestador nacional" (quanto, em média, um prestador qualquer no
                # Brasil faz daquele procedimento).
                _prestadores_nacional_temp = agregado.groupby(
                    "NOME_PROCEDIMENTO", observed=True
                )["CD_PRESTADOR"].nunique()
                # .astype(float) no final: Series.map() numa coluna category (NOME_PROCEDIMENTO)
                # contra outra Series pode devolver o resultado também em dtype category (mesmo
                # os valores sendo numéricos) dependendo da versão do pandas — e divisão não é
                # suportada em Categorical, quebraria mais abaixo com TypeError. Sem esse cast,
                # o bug só aparece dependendo da versão instalada, então corrige aqui na raiz.
                nacional_temp_flat["qtd_prestadores_nacional"] = nacional_temp_flat["NOME_PROCEDIMENTO"].map(
                    _prestadores_nacional_temp
                ).astype(float)

                def _base_nacional_temp(nome_proc):
                    if nome_proc not in nacional_temp.index:
                        return float("nan"), float("nan")
                    return (
                        nacional_temp.loc[nome_proc, "qtd_procedimentos"],
                        nacional_temp.loc[nome_proc, "qtd_usuarios"],
                    )

                if _sufixo_aba_temp == "_ranking":
                    # ---- Ranking POR PRESTADOR: agrega todos os procedimentos em escopo
                    # (respeita o filtro Procedimento, se houver) por CD_PRESTADOR. FASE é
                    # somado entre os procedimentos que o prestador faz (cada um com sua
                    # própria taxa nacional) e só DEPOIS o CS final é calculado — não é uma
                    # média dos CS de cada procedimento (isso não pesaria pelo volume de
                    # cada um). Mesma lógica já usada nos gráficos de dispersão desta aba,
                    # mais abaixo (_severidade_agregada_temp), só que aqui vira uma grade,
                    # com também "Qtde por prestador Nacional/Cidade" e "CS da Cidade" por
                    # prestador (cada um comparado com a PRÓPRIA cidade dele, não uma única
                    # cidade de referência pra aba toda). ----
                    def _div_segura_rank_temp(a, b):
                        if b is None or pd.isna(b) or b == 0 or pd.isna(a):
                            return float("nan")
                        return a / b

                    _base_rank_prest_temp = df_temp.groupby(
                        ["CD_PRESTADOR", "NOME_PROCEDIMENTO"], dropna=False, observed=True
                    ).agg(
                        qtd_procedimentos=("qtd_procedimentos", "sum"),
                        quantidade_uso=("soma_uso", "sum"),
                    ).reset_index()
                    _base_rank_prest_temp = _base_rank_prest_temp[
                        _base_rank_prest_temp["CD_PRESTADOR"].notna()
                        & _base_rank_prest_temp["NOME_PROCEDIMENTO"].notna()
                    ]
                    if _base_rank_prest_temp.empty:
                        rank_temp = pd.DataFrame({c: [] for c in [
                            "CD_PRESTADOR", "rotulo", "qtd_usuarios", "qtd_procedimentos",
                            "quantidade_uso", "uso_por_procedimento", "uso_por_vida",
                            "qtd_procedimentos_nacional", "qtd_vidas_nacional",
                            "qtd_por_prestador_nacional", "qtd_procedimentos_cidade",
                            "fase_esperado_cidade", "qtd_por_prestador_cidade",
                            "fase_esperado", "qp_praticado", "cs", "cs_geral", "cs_cidade",
                        ]})
                    else:
                        _vidas_cel_rank_temp = vidas_por(
                            usuarios_temp, ["CD_PRESTADOR", "NOME_PROCEDIMENTO"]
                        )
                        _base_rank_prest_temp = _base_rank_prest_temp.merge(
                            _vidas_cel_rank_temp, on=["CD_PRESTADOR", "NOME_PROCEDIMENTO"], how="left"
                        )
                        _base_rank_prest_temp["qtd_usuarios"] = _base_rank_prest_temp["qtd_usuarios"].fillna(0)
                        _base_rank_prest_temp = _base_rank_prest_temp.merge(
                            nacional_temp_flat, on="NOME_PROCEDIMENTO", how="left"
                        )
                        _base_rank_prest_temp["fase_esperado_linha"] = (
                            _base_rank_prest_temp["qtd_procedimentos_nacional"]
                            / _base_rank_prest_temp["qtd_vidas_nacional"]
                        ) * _base_rank_prest_temp["qtd_usuarios"]
                        _base_rank_prest_temp["qtd_por_prestador_nacional_linha"] = (
                            _base_rank_prest_temp["qtd_procedimentos_nacional"]
                            / _base_rank_prest_temp["qtd_prestadores_nacional"]
                        )

                        # ---- referência por cidade: cada prestador compara com a PRÓPRIA
                        # cidade dele (moda de CIDADE_PRESTADOR dentro dos filtros atuais). ----
                        _cidade_por_prestador_rank_temp = df_temp.groupby(
                            "CD_PRESTADOR", observed=True
                        )["CIDADE_PRESTADOR"].agg(
                            lambda x: x.mode().iloc[0] if not x.mode().empty else None
                        ).rename("CIDADE_PRESTADOR_ref").reset_index()
                        _base_rank_prest_temp = _base_rank_prest_temp.merge(
                            _cidade_por_prestador_rank_temp, on="CD_PRESTADOR", how="left"
                        )
                        if "CIDADE_PRESTADOR" in df_temp_base.columns:
                            _cidade_proc_rank_temp = df_temp_base.groupby(
                                ["CIDADE_PRESTADOR", "NOME_PROCEDIMENTO"], observed=True
                            ).agg(
                                qtd_procedimentos_cidade=("qtd_procedimentos", "sum"),
                                qtd_prestadores_cidade=("CD_PRESTADOR", "nunique"),
                            ).reset_index()
                            _vidas_cidade_proc_rank_temp = vidas_por(
                                usuarios_filtrado[usuarios_filtrado["NOME_PROCEDIMENTO"].isin(nomes_temp)],
                                ["CIDADE_PRESTADOR", "NOME_PROCEDIMENTO"],
                            ).rename(columns={"qtd_usuarios": "qtd_vidas_cidade"})
                            _cidade_proc_rank_temp = _cidade_proc_rank_temp.merge(
                                _vidas_cidade_proc_rank_temp,
                                on=["CIDADE_PRESTADOR", "NOME_PROCEDIMENTO"], how="left",
                            )
                            _base_rank_prest_temp = _base_rank_prest_temp.merge(
                                _cidade_proc_rank_temp.rename(columns={"CIDADE_PRESTADOR": "CIDADE_PRESTADOR_ref"}),
                                on=["CIDADE_PRESTADOR_ref", "NOME_PROCEDIMENTO"], how="left",
                            )
                        else:
                            _base_rank_prest_temp["qtd_procedimentos_cidade"] = float("nan")
                            _base_rank_prest_temp["qtd_prestadores_cidade"] = float("nan")
                            _base_rank_prest_temp["qtd_vidas_cidade"] = float("nan")
                        _base_rank_prest_temp["qtd_por_prestador_cidade_linha"] = (
                            _base_rank_prest_temp["qtd_procedimentos_cidade"]
                            / _base_rank_prest_temp["qtd_prestadores_cidade"]
                        )
                        # FASE da cidade (por linha prestador+procedimento) — mesma taxa
                        # nacional aplicada às vidas DA CIDADE nesse procedimento; QP da
                        # cidade = soma de TODOS os prestadores da cidade nesse procedimento —
                        # junto formam o "CS da Cidade" agregado por prestador (severidade da
                        # cidade dele nesses procedimentos, não o CS do próprio prestador
                        # recalculado).
                        _base_rank_prest_temp["fase_esperado_cidade_linha"] = (
                            _base_rank_prest_temp["qtd_procedimentos_nacional"]
                            / _base_rank_prest_temp["qtd_vidas_nacional"]
                        ) * _base_rank_prest_temp["qtd_vidas_cidade"]

                        rank_temp = _base_rank_prest_temp.groupby("CD_PRESTADOR", observed=True).agg(
                            qtd_procedimentos=("qtd_procedimentos", "sum"),
                            quantidade_uso=("quantidade_uso", "sum"),
                            qtd_procedimentos_nacional=("qtd_procedimentos_nacional", "sum"),
                            qtd_vidas_nacional=("qtd_vidas_nacional", "sum"),
                            fase_esperado=("fase_esperado_linha", "sum"),
                            qtd_por_prestador_nacional=("qtd_por_prestador_nacional_linha", "sum"),
                            qtd_por_prestador_cidade=("qtd_por_prestador_cidade_linha", "sum"),
                            fase_esperado_cidade=("fase_esperado_cidade_linha", "sum"),
                            qtd_procedimentos_cidade=("qtd_procedimentos_cidade", "sum"),
                        ).reset_index()
                        _vidas_prest_total_rank_temp = vidas_por(usuarios_temp, "CD_PRESTADOR")
                        rank_temp = rank_temp.merge(_vidas_prest_total_rank_temp, on="CD_PRESTADOR", how="left")
                        rank_temp["qtd_usuarios"] = rank_temp["qtd_usuarios"].fillna(0)
                        rank_temp["uso_por_procedimento"] = (
                            rank_temp["quantidade_uso"] / rank_temp["qtd_procedimentos"]
                        )
                        rank_temp["uso_por_vida"] = rank_temp["quantidade_uso"] / rank_temp["qtd_usuarios"]
                        rank_temp["qp_praticado"] = rank_temp["qtd_procedimentos"]
                        rank_temp["cs"] = [
                            _div_segura_rank_temp(qp, fase) * 10
                            for qp, fase in zip(rank_temp["qtd_procedimentos"], rank_temp["fase_esperado"])
                        ]
                        rank_temp["cs_cidade"] = [
                            _div_segura_rank_temp(qpc, fasec) * 10
                            for qpc, fasec in zip(
                                rank_temp["qtd_procedimentos_cidade"], rank_temp["fase_esperado_cidade"]
                            )
                        ]
                        rank_temp["cs_geral"] = float("nan")  # não se aplica a esta aba (sem "corte" único)

                        # ---- rótulo "Prestador - UF - Cidade - Cluster" (mesmo padrão já
                        # usado na tabela "Prestadores do procedimento selecionado" mais
                        # abaixo nesta aba). ----
                        _colunas_info_rank_prest_temp = [
                            c for c in ("NOME_PRESTADOR", "CIDADE_PRESTADOR", "UF", "CLUSTER")
                            if c in df_temp.columns
                        ]
                        _info_extra_rank_prest_temp = df_temp.groupby("CD_PRESTADOR", observed=True).agg(**{
                            c: (c, lambda x: x.mode().iloc[0] if not x.mode().empty else "—")
                            for c in _colunas_info_rank_prest_temp
                        }).reset_index()
                        rank_temp = rank_temp.merge(_info_extra_rank_prest_temp, on="CD_PRESTADOR", how="left")
                        for c in ("NOME_PRESTADOR", "CIDADE_PRESTADOR", "UF", "CLUSTER"):
                            if c not in rank_temp.columns:
                                rank_temp[c] = "—"
                            rank_temp[c] = rank_temp[c].fillna("—")
                        rank_temp["rotulo"] = [
                            f"{nome_fmt} - {uf} - {cidade} - {cluster}"
                            for nome_fmt, uf, cidade, cluster in zip(
                                [
                                    str(nome) if pd.notna(nome) and str(nome).strip() and str(nome) != "—"
                                    else f"Prestador {int(cod)}"
                                    for cod, nome in zip(rank_temp["CD_PRESTADOR"], rank_temp["NOME_PRESTADOR"])
                                ],
                                rank_temp["UF"], rank_temp["CIDADE_PRESTADOR"], rank_temp["CLUSTER"],
                            )
                        ]
                else:
                    rank_temp = rank_temp.merge(nacional_temp_flat, on="NOME_PROCEDIMENTO", how="left")

                    # ---- Qtde por prestador (Nacional) = qtd_procedimentos_nacional ÷ qtd de
                    # prestadores distintos que fazem esse procedimento no Brasil todo — quanto, em
                    # média, cada prestador nacional faz daquele procedimento. Serve pra comparar com
                    # o volume de UM prestador específico e ver se ele destoa muito da média por
                    # prestador. ----
                    rank_temp["qtd_por_prestador_nacional"] = (
                        rank_temp["qtd_procedimentos_nacional"] / rank_temp["qtd_prestadores_nacional"]
                    )

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
                        # Qtde de prestadores distintos NA CIDADE de referência que fazem cada
                        # procedimento — junto com qtd_procedimentos (da cidade) acima, dá "Qtde por
                        # prestador (Cidade)": quanto, em média, um prestador qualquer da cidade faz
                        # daquele procedimento, pra comparar com o volume do prestador investigado.
                        _prestadores_cidade_temp = df_cidade_ref_temp.groupby(
                            "NOME_PROCEDIMENTO", observed=True
                        )["CD_PRESTADOR"].nunique()
                        # .astype(float) pelo mesmo motivo do "qtd_prestadores_nacional" mais acima —
                        # .map() numa coluna category pode devolver category mesmo com valores
                        # numéricos, e a divisão logo abaixo não é suportada em Categorical.
                        rank_cidade_temp["qtd_prestadores_cidade"] = rank_cidade_temp["NOME_PROCEDIMENTO"].map(
                            _prestadores_cidade_temp
                        ).astype(float)
                        rank_temp = rank_temp.merge(
                            rank_cidade_temp[[
                                "NOME_PROCEDIMENTO", "cs_cidade", "qtd_procedimentos", "fase_esperado_cidade",
                                "qtd_prestadores_cidade",
                            ]].rename(columns={"qtd_procedimentos": "qtd_procedimentos_cidade"}),
                            on="NOME_PROCEDIMENTO", how="left",
                        )
                    else:
                        rank_temp["cs_cidade"] = float("nan")
                        rank_temp["qtd_procedimentos_cidade"] = float("nan")
                        rank_temp["fase_esperado_cidade"] = float("nan")
                        rank_temp["qtd_prestadores_cidade"] = float("nan")

                    rank_temp["qtd_por_prestador_cidade"] = (
                        rank_temp["qtd_procedimentos_cidade"] / rank_temp["qtd_prestadores_cidade"]
                    )

                # ---- Índice de Atenção (Volume) — quantas vezes o volume do PRESTADOR
                # selecionado neste filtro está acima da média por prestador (referência: a
                # cidade dele, se houver; senão, o Brasil todo) — pra sinalizar concentração de
                # volume que o CS sozinho pode não capturar (CS é normalizado por vidas/taxa
                # nacional, então pode ficar perto de 10 mesmo com volume concentrado). Só faz
                # sentido com UM prestador específico selecionado (senão "Qtde proced" é a soma
                # de vários prestadores misturados, e a razão não quer dizer nada) — com
                # "Todos", ou sem referência pra comparar, fica "—". NÃO é prova de fraude — é
                # só um sinal pra priorizar revisão manual, calculado de um jeito auditável
                # (mesma lógica simples de razão usada no resto da aba).
                LIMIAR_ATENCAO_MEDIO_TEMP = 2.0   # ⚠️ triângulo amarelo a partir de quantas vezes a média
                LIMIAR_ATENCAO_ALTO_TEMP = 5.0    # 🚩 bandeirinha vermelha a partir de quantas vezes a média

                def _texto_indice_atencao_temp(razao):
                    return f"×{razao:.1f} a média".replace(".", ",")

                def _icone_indice_atencao_temp(razao):
                    if razao >= LIMIAR_ATENCAO_ALTO_TEMP:
                        return "🚩 "
                    if razao >= LIMIAR_ATENCAO_MEDIO_TEMP:
                        return "⚠️ "
                    return ""

                _indices_atencao_temp = []
                _rotulos_atencao_temp = []
                _icones_atencao_temp = []
                for _qtd_prest_idx_temp, _qtd_pp_cidade_idx_temp, _qtd_pp_nacional_idx_temp in zip(
                    rank_temp["qtd_procedimentos"], rank_temp["qtd_por_prestador_cidade"],
                    rank_temp["qtd_por_prestador_nacional"],
                ):
                    _ref_idx_temp = (
                        _qtd_pp_cidade_idx_temp if pd.notna(_qtd_pp_cidade_idx_temp)
                        else _qtd_pp_nacional_idx_temp
                    )
                    # Na aba "📊 Ranking" cada LINHA já é um prestador específico (a grade é
                    # agrupada por prestador, não por procedimento) — então o índice faz
                    # sentido linha a linha mesmo com o filtro Prestador em "Todos" (que é
                    # como a aba abre por padrão). Nas outras abas, só calcula com um
                    # prestador específico selecionado no filtro (senão "Qtde proced" seria a
                    # soma de vários prestadores misturados).
                    if (
                        (prest_sel_temp == "Todos" and _sufixo_aba_temp != "_ranking")
                        or pd.isna(_ref_idx_temp) or _ref_idx_temp == 0
                        or pd.isna(_qtd_prest_idx_temp)
                    ):
                        _indices_atencao_temp.append(float("nan"))
                        _rotulos_atencao_temp.append("—")
                        _icones_atencao_temp.append("")
                        continue
                    _razao_idx_temp = _qtd_prest_idx_temp / _ref_idx_temp
                    _indices_atencao_temp.append(_razao_idx_temp)
                    _rotulos_atencao_temp.append(_texto_indice_atencao_temp(_razao_idx_temp))
                    _icones_atencao_temp.append(_icone_indice_atencao_temp(_razao_idx_temp))
                rank_temp["indice_atencao_volume"] = _indices_atencao_temp
                rank_temp["indice_atencao_volume_rotulo"] = _rotulos_atencao_temp
                # ---- bandeirinha/triângulo já direto ao lado do nome do procedimento (coluna
                # "Procedimento"), em vez de só na coluna do índice — assim salta aos olhos
                # rolando a grade sem precisar olhar a última coluna. A legenda dos ícones
                # aparece logo acima da grade (ver st.caption antes do _tabela_html_temp). ----
                rank_temp["rotulo"] = [
                    f"{_icone_temp}{_rotulo_temp}"
                    for _icone_temp, _rotulo_temp in zip(_icones_atencao_temp, rank_temp["rotulo"])
                ]

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

                # ---- ordena a grade: nas outras abas, sempre por CS decrescente (do mais
                # severo pro menos severo); na aba "📊 Ranking", pela métrica escolhida no
                # "Ranquear por" acima (mesma direção — sempre do maior pro menor). ----
                if _sufixo_aba_temp == "_ranking":
                    _coluna_ordenacao_temp = _OPCOES_RANQUEAR_TEMP.get(ranquear_por_temp, "cs")
                    rank_temp = rank_temp.sort_values(
                        _coluna_ordenacao_temp, ascending=False, na_position="last"
                    )
                else:
                    rank_temp = rank_temp.sort_values("cs", ascending=False)

                exib_rank_temp = rank_temp.copy()
                exib_rank_temp["qtd_procedimentos"] = exib_rank_temp["qtd_procedimentos"].map(fmt_int)
                exib_rank_temp["qtd_usuarios"] = exib_rank_temp["qtd_usuarios"].map(fmt_int)
                exib_rank_temp["quantidade_uso"] = exib_rank_temp["quantidade_uso"].map(fmt_int)
                exib_rank_temp["uso_por_procedimento"] = exib_rank_temp["uso_por_procedimento"].map(fmt_float2)
                exib_rank_temp["uso_por_vida"] = exib_rank_temp["uso_por_vida"].map(fmt_float2)
                exib_rank_temp["fase_esperado"] = exib_rank_temp["fase_esperado"].map(fmt_float2)
                exib_rank_temp["qp_praticado"] = exib_rank_temp["qp_praticado"].map(fmt_int)
                # Qtde por prestador (Nacional/Cidade) — "—" quando não dá pra calcular (sem
                # cidade de referência, no caso da Cidade; fmt_float2 já cobre o NaN).
                exib_rank_temp["qtd_por_prestador_nacional"] = exib_rank_temp["qtd_por_prestador_nacional"].map(
                    fmt_float2
                )
                exib_rank_temp["qtd_por_prestador_cidade"] = exib_rank_temp["qtd_por_prestador_cidade"].map(
                    fmt_float2
                )
                # CS Geral é sempre a referência "sem os filtros desta aba" — mostra o valor de
                # verdade mesmo quando nenhum_filtro_temp é True (nesse caso ele só coincide
                # com o CS ao lado, já que os dois corte ficam iguais).
                exib_rank_temp["cs_geral"] = exib_rank_temp["cs_geral"].map(_fmt_cs_temp)
                # CS da Cidade segue a mesma regra do CS Geral — mostra o valor de verdade,
                # com "—" só quando não há cidade de referência (função _fmt_cs_temp já cobre
                # o NaN desse caso).
                exib_rank_temp["cs_cidade"] = exib_rank_temp["cs_cidade"].map(_fmt_cs_temp)
                # Na aba "📊 Ranking" cada linha já é UM prestador específico (o "corte" é o
                # próprio prestador, não a base toda) — o CS continua informativo mesmo sem
                # nenhum filtro extra ligado, então não some por conta de nenhum_filtro_temp
                # (essa regra é só pra evitar CS artificialmente perto de 10 quando o "corte"
                # das outras abas, sem filtro, se aproxima da própria base nacional).
                if nenhum_filtro_temp and _sufixo_aba_temp != "_ranking":
                    exib_rank_temp["cs"] = "—"
                    exib_rank_temp["calculo_cs"] = "—"
                else:
                    exib_rank_temp["cs"] = exib_rank_temp["cs"].map(_fmt_cs_temp)
                # "Cálculo do QP"/"QP" ficam de fora quando a aba pede (_mostrar_calculo_qp_temp
                # = False, hoje o caso da "📊 Ranking") — o resto das colunas é igual pra todas.
                # "Qtde por prestador Nacional/Cidade" ficam logo depois de "Qtde proced", pra
                # comparar de cara o volume do corte com a média por prestador (Brasil/cidade).
                _colunas_exib_rank_temp = [
                    "rotulo", "qtd_procedimentos",
                    "qtd_por_prestador_nacional", "qtd_por_prestador_cidade",
                    "qtd_usuarios", "quantidade_uso",
                    "uso_por_procedimento", "uso_por_vida",
                    "calculo_fase_esperado", "fase_esperado",
                ]
                if _mostrar_calculo_qp_temp:
                    _colunas_exib_rank_temp += ["calculo_qp", "qp_praticado"]
                _colunas_exib_rank_temp += [
                    "calculo_cs", "cs", "cs_geral", "calculo_cs_cidade", "cs_cidade",
                    "indice_atencao_volume_rotulo",
                ]
                # A aba "📊 Ranking" pediu uma grade enxuta — só as 8 colunas de volume/
                # severidade (mais "Procedimento", pra identificar a linha), sem "Cálculo
                # do X"/Soma de uso/Uso por proced-vida/CS Geral/QP. Sobrescreve a lista
                # padrão montada acima em vez de remontar do zero.
                if _sufixo_aba_temp == "_ranking":
                    _colunas_exib_rank_temp = [
                        "rotulo", "qtd_usuarios", "qtd_procedimentos",
                        "qtd_por_prestador_nacional", "qtd_por_prestador_cidade",
                        "fase_esperado", "cs", "cs_cidade", "indice_atencao_volume_rotulo",
                    ]
                exib_rank_temp = exib_rank_temp[_colunas_exib_rank_temp].rename(columns={
                    # Na aba "📊 Ranking" a linha é um prestador, não um procedimento — o
                    # cabeçalho da 1ª coluna muda pra "Prestador" nesse caso.
                    "rotulo": "Prestador" if _sufixo_aba_temp == "_ranking" else "Procedimento",
                    "qtd_procedimentos": "Qtde proced",
                    "qtd_por_prestador_nacional": "Qtde por prestador Nacional",
                    "qtd_por_prestador_cidade": "Qtde por prestador - Cidade",
                    "qtd_usuarios": "Qtd vidas",
                    "quantidade_uso": "Soma de uso",
                    "uso_por_procedimento": "Uso/proced",
                    "uso_por_vida": "Uso/vida",
                    "calculo_fase_esperado": "Cálculo do FASE",
                    "fase_esperado": "FASE",
                    "indice_atencao_volume_rotulo": "Índice de Atenção (Volume)",
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
                    /* Cabeçalho congelado: fica parado no topo ao rolar a grade (só tem
                    efeito visível na variante com scroll vertical — grade-cs-temp-wrap-scroll,
                    max-height: 165px — nas grades sem scroll vertical o "sticky" não muda
                    nada). Precisa de fundo sólido, senão as linhas por trás aparecem por baixo
                    do texto do cabeçalho ao rolar — var(--background-color) acompanha o tema
                    claro/escuro do Streamlit; sem essa variável (temas mais antigos), cai pro
                    branco do fallback. */
                    .grade-cs-temp th {
                        font-weight: 600;
                        position: sticky;
                        top: 0;
                        background-color: var(--background-color, #ffffff);
                        z-index: 1;
                    }
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
                # sem prestador selecionado, se religada pra True) — na aba "📊 Ranking" ela
                # fica sempre visível, já que essa aba não trava nem depende de um prestador
                # específico (o objetivo é rankear procedimentos/cortes de cara).
                _mostrar_grade_cs_temp = (
                    MOSTRAR_GRADE_CS_PROCEDIMENTO_TEMP or prest_sel_temp != "Todos"
                    or _sufixo_aba_temp == "_ranking"
                )
                if _mostrar_grade_cs_temp:
                    st.caption(
                        "**Alerta de volume**  \n"
                        "🚩 bandeirinha vermelha: volume ≥ 5× a média por prestador (alerta "
                        "forte)  \n"
                        "⚠️ triângulo amarelo: volume ≥ 2× a média por prestador (atenção "
                        "moderada)"
                    )
                    # Na aba "📊 Ranking" a grade somada por prestador foi substituída pela
                    # lista de expanders logo abaixo (cada prestador já mostra seu resumo no
                    # próprio título do expander) — nas outras abas a grade continua igual.
                    if _sufixo_aba_temp != "_ranking":
                        _tabela_html_temp(exib_rank_temp, scroll=True)

                    # ---- Detalhamento por procedimento, um expander por prestador — só na
                    # aba "📊 Ranking". O título do expander já traz o resumo do prestador
                    # (mesmos números que antes apareciam na grade); abrir mostra o "por
                    # dentro" dele, uma linha por procedimento, com as mesmas colunas. Mesma
                    # ordem da grade (rank_temp já está ordenado pelo "Ranquear por" escolhido
                    # acima). _base_rank_prest_temp (por prestador+procedimento, ainda não
                    # somado por prestador) foi montada mais acima, na construção da grade
                    # desta aba — _detalhe_procedimentos_prestador_temp fica disponível pra
                    # reaproveitar também no PDF (botão "Gerar PDF" logo abaixo).
                    def _cs_procedimento_temp(qp, fase):
                        v = _div_segura_rank_temp(qp, fase)
                        return v * 10 if pd.notna(v) else float("nan")

                    def _detalhe_procedimentos_prestador_temp(cd_prestador):
                        _detalhe_proc_temp = _base_rank_prest_temp[
                            _base_rank_prest_temp["CD_PRESTADOR"] == cd_prestador
                        ].sort_values("qtd_procedimentos", ascending=False).copy()
                        if _detalhe_proc_temp.empty:
                            return None

                        _detalhe_proc_temp["cs_proc"] = [
                            _cs_procedimento_temp(qp, fase)
                            for qp, fase in zip(
                                _detalhe_proc_temp["qtd_procedimentos"],
                                _detalhe_proc_temp["fase_esperado_linha"],
                            )
                        ]
                        _detalhe_proc_temp["cs_cidade_proc"] = [
                            _cs_procedimento_temp(qpc, fasec)
                            for qpc, fasec in zip(
                                _detalhe_proc_temp["qtd_procedimentos_cidade"],
                                _detalhe_proc_temp["fase_esperado_cidade_linha"],
                            )
                        ]
                        # mesma regra do Índice de Atenção (Volume) da grade principal: ícone
                        # junto do nome (aqui, do Procedimento), texto puro ("×X,X a média")
                        # na coluna do índice.
                        _icones_proc_temp = []
                        _textos_proc_temp = []
                        for _qp_proc_temp, _pp_cidade_proc_temp, _pp_nacional_proc_temp in zip(
                            _detalhe_proc_temp["qtd_procedimentos"],
                            _detalhe_proc_temp["qtd_por_prestador_cidade_linha"],
                            _detalhe_proc_temp["qtd_por_prestador_nacional_linha"],
                        ):
                            _ref_proc_temp = (
                                _pp_cidade_proc_temp if pd.notna(_pp_cidade_proc_temp)
                                else _pp_nacional_proc_temp
                            )
                            if (
                                pd.isna(_ref_proc_temp) or _ref_proc_temp == 0
                                or pd.isna(_qp_proc_temp)
                            ):
                                _icones_proc_temp.append("")
                                _textos_proc_temp.append("—")
                                continue
                            _razao_proc_temp = _qp_proc_temp / _ref_proc_temp
                            _icones_proc_temp.append(_icone_indice_atencao_temp(_razao_proc_temp))
                            _textos_proc_temp.append(_texto_indice_atencao_temp(_razao_proc_temp))

                        return pd.DataFrame({
                            "Procedimento": [
                                f"{icone}{nome}" for icone, nome in zip(
                                    _icones_proc_temp, _detalhe_proc_temp["NOME_PROCEDIMENTO"]
                                )
                            ],
                            "Qtd vidas": _detalhe_proc_temp["qtd_usuarios"].map(fmt_int),
                            "Qtde proced": _detalhe_proc_temp["qtd_procedimentos"].map(fmt_int),
                            "Qtde por prestador Nacional": _detalhe_proc_temp[
                                "qtd_por_prestador_nacional_linha"
                            ].map(fmt_float2),
                            "Qtde por prestador - Cidade": _detalhe_proc_temp[
                                "qtd_por_prestador_cidade_linha"
                            ].map(fmt_float2),
                            "FASE": _detalhe_proc_temp["fase_esperado_linha"].map(fmt_float2),
                            "CS": _detalhe_proc_temp["cs_proc"].map(_fmt_cs_temp),
                            "CS da Cidade": _detalhe_proc_temp["cs_cidade_proc"].map(_fmt_cs_temp),
                            "Índice de Atenção (Volume)": _textos_proc_temp,
                        })

                    if _sufixo_aba_temp == "_ranking":
                        # ============================================================
                        # PDF — "Gerar PDF" exporta esta aba (Ranking) com os filtros atuais:
                        # cabeçalho com a logo, período trabalhado e filtros aplicados, legenda,
                        # 2 gráficos (dispersão CS × volume e Top 10 pela métrica escolhida em
                        # "Ranquear por") e o detalhamento por prestador já "aberto" (mesmo
                        # conteúdo dos expanders logo abaixo — não dá pra ter expander de verdade num
                        # PDF, então cada prestador vira uma seção com a tabela de procedimentos
                        # logo abaixo, na mesma ordem da tela). reportlab e matplotlib são
                        # importados só aqui dentro (nunca no topo do arquivo) — se ainda não
                        # estiverem no requirements.txt, o resto do painel continua funcionando
                        # normalmente; só o botão avisa o que falta instalar.
                        # ============================================================
                        def _gerar_pdf_ranking_temp():
                            # Trava de segurança contra PDF com a base toda (nunca pode sair
                            # sem recorte) — mesma checagem que já desabilita o botão "Gerar
                            # PDF" na tela, repetida aqui como segunda linha de defesa, caso
                            # esta função algum dia seja chamada de outro lugar sem passar por
                            # aquele botão.
                            if (
                                uf_sel_temp == "Todos" and cidade_sel_temp == "Todos"
                                and cluster_sel_temp == "Todos" and prest_sel_temp == "Todos"
                            ):
                                st.error(
                                    "Selecione pelo menos UF, Cidade, Cluster ou Prestador "
                                    "antes de gerar o PDF — não é permitido gerar com a base toda."
                                )
                                return None
                            try:
                                import matplotlib
                                matplotlib.use("Agg")
                                import matplotlib.pyplot as plt
                                from matplotlib.colors import LinearSegmentedColormap
                                from reportlab.lib.pagesizes import A4
                                from reportlab.lib.units import mm
                                from reportlab.lib import colors as rl_colors
                                from reportlab.platypus import (
                                    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
                                    Image as RLImage,
                                )
                                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                            except ImportError as _erro_libs_pdf_temp:
                                st.error(
                                    "Pra gerar o PDF faltam bibliotecas no ambiente (`reportlab` "
                                    "e/ou `matplotlib`). Adicione as duas ao requirements.txt e "
                                    f"reinicie o app. Detalhe técnico: {_erro_libs_pdf_temp}"
                                )
                                return None

                            _COR_PRIMARIA_PDF_TEMP = rl_colors.HexColor("#0f5f8c")
                            _COR_PRIMARIA_CLARA_PDF_TEMP = rl_colors.HexColor("#e8f2f8")
                            _COR_ALERTA_PDF_TEMP = rl_colors.HexColor("#e74c3c")
                            _COR_ATENCAO_PDF_TEMP = rl_colors.HexColor("#f1c40f")
                            _COR_TEXTO_PDF_TEMP = rl_colors.HexColor("#1f2d3a")
                            _COR_ZEBRA_PDF_TEMP = rl_colors.HexColor("#f6f8fa")
                            _COR_BORDA_PDF_TEMP = rl_colors.HexColor("#d8dee3")
                            _LARGURA_UTIL_PDF_TEMP = 182 * mm  # A4 (210mm) - 14mm de margem de cada lado

                            def _truncar_nome_pdf_temp(nome, limite=38):
                                nome = str(nome)
                                return nome if len(nome) <= limite else nome[: limite - 1] + "…"

                            def _grafico_dispersao_pdf_temp(rank_df):
                                dados = rank_df[
                                    (rank_df["qtd_usuarios"] > 0) & rank_df["cs"].notna()
                                ].copy()
                                if dados.empty:
                                    return None
                                _cmap_temp = LinearSegmentedColormap.from_list(
                                    "cs_pdf_temp", ["#2ecc71", "#f1c40f", "#e74c3c"]
                                )
                                fig, ax = plt.subplots(figsize=(7.2, 3.2), dpi=150)
                                _tam_max_temp = dados["qtd_procedimentos"].max()
                                _tamanhos_temp = 20 + (dados["qtd_procedimentos"] / _tam_max_temp) * 380
                                sc = ax.scatter(
                                    dados["qtd_usuarios"], dados["cs"].clip(0, 20), s=_tamanhos_temp,
                                    c=dados["cs"].clip(0, 20), cmap=_cmap_temp, vmin=0, vmax=20,
                                    alpha=0.85, edgecolors="white", linewidths=0.5,
                                )
                                ax.set_xscale("log")
                                ax.axhline(10, color="#888888", linestyle="--", linewidth=1)
                                ax.set_xlabel("Qtd vidas (escala log)", fontsize=9)
                                ax.set_ylabel("CS", fontsize=9)
                                ax.set_title(
                                    "CS × volume por prestador", fontsize=11, fontweight="bold",
                                    color="#0f5f8c",
                                )
                                ax.tick_params(labelsize=8)
                                ax.grid(True, alpha=0.25)
                                cbar = fig.colorbar(sc, ax=ax, pad=0.01)
                                cbar.set_label("CS", fontsize=8)
                                cbar.ax.tick_params(labelsize=7)
                                fig.tight_layout()
                                buf = io.BytesIO()
                                fig.savefig(buf, format="png")
                                plt.close(fig)
                                buf.seek(0)
                                return buf

                            def _grafico_top10_pdf_temp(rank_df, coluna_metrica, rotulo_metrica):
                                if coluna_metrica not in rank_df.columns:
                                    return None
                                dados = rank_df.head(10).sort_values(
                                    coluna_metrica, ascending=True, na_position="first"
                                ).copy()
                                if dados.empty:
                                    return None
                                _nomes_temp = [
                                    _truncar_nome_pdf_temp(
                                        r.replace("🚩 ", "").replace("⚠️ ", "").split(" - ")[0]
                                    )
                                    for r in dados["rotulo"]
                                ]
                                _valores_temp = dados[coluna_metrica].fillna(0)
                                fig, ax = plt.subplots(figsize=(7.2, 3.2), dpi=150)
                                ax.barh(_nomes_temp, _valores_temp, color="#0f5f8c")
                                ax.set_xlabel(rotulo_metrica, fontsize=9)
                                ax.set_title(
                                    f"Top 10 por {rotulo_metrica}", fontsize=11, fontweight="bold",
                                    color="#0f5f8c",
                                )
                                ax.tick_params(labelsize=8)
                                ax.grid(True, axis="x", alpha=0.25)
                                fig.tight_layout()
                                buf = io.BytesIO()
                                fig.savefig(buf, format="png")
                                plt.close(fig)
                                buf.seek(0)
                                return buf

                            buf_pdf = io.BytesIO()
                            doc = SimpleDocTemplate(
                                buf_pdf, pagesize=A4,
                                topMargin=18 * mm, bottomMargin=16 * mm,
                                leftMargin=14 * mm, rightMargin=14 * mm,
                                title="Ranking de Prestadores - Odonto",
                            )

                            styles = getSampleStyleSheet()
                            estilo_titulo = ParagraphStyle(
                                "TituloPdfTemp", parent=styles["Title"], fontSize=17,
                                textColor=rl_colors.white, leading=20, spaceAfter=0,
                            )
                            estilo_subtitulo = ParagraphStyle(
                                "SubtituloPdfTemp", parent=styles["Normal"], fontSize=10,
                                textColor=rl_colors.white, leading=13,
                            )
                            estilo_secao = ParagraphStyle(
                                "SecaoPdfTemp", parent=styles["Heading2"], fontSize=12.5,
                                textColor=_COR_PRIMARIA_PDF_TEMP, spaceBefore=10, spaceAfter=4,
                            )
                            estilo_prestador = ParagraphStyle(
                                "PrestadorPdfTemp", parent=styles["Normal"], fontSize=9.5,
                                textColor=rl_colors.white, leading=12,
                            )
                            estilo_corpo = ParagraphStyle(
                                "CorpoPdfTemp", parent=styles["Normal"], fontSize=8.5,
                                textColor=_COR_TEXTO_PDF_TEMP, leading=11,
                            )
                            estilo_legenda = ParagraphStyle(
                                "LegendaPdfTemp", parent=styles["Normal"], fontSize=8,
                                textColor=_COR_TEXTO_PDF_TEMP, leading=11,
                            )

                            story = []

                            # ---- cabeçalho: faixa azul com logo + título ----
                            _logo_flowable_temp = ""
                            if LOGO_PATH and os.path.exists(LOGO_PATH):
                                try:
                                    from PIL import Image as PILImageTemp
                                    with PILImageTemp.open(LOGO_PATH) as _im_teste_temp:
                                        _im_teste_temp.verify()
                                    _logo_flowable_temp = RLImage(
                                        LOGO_PATH, width=26 * mm, height=26 * mm, kind="proportional"
                                    )
                                except Exception:
                                    _logo_flowable_temp = ""
                            _titulo_cel_temp = [
                                Paragraph("Painel de Gestão de Sinistro — Odonto", estilo_titulo),
                                Paragraph("Ranking de prestadores", estilo_subtitulo),
                            ]
                            _tabela_cabecalho_temp = Table(
                                [[_logo_flowable_temp, _titulo_cel_temp]],
                                colWidths=[30 * mm, 152 * mm],
                            )
                            _tabela_cabecalho_temp.setStyle(TableStyle([
                                ("BACKGROUND", (0, 0), (-1, -1), _COR_PRIMARIA_PDF_TEMP),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                ("TOPPADDING", (0, 0), (-1, -1), 8),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                            ]))
                            story.append(_tabela_cabecalho_temp)
                            story.append(Spacer(1, 8))

                            # ---- metadados: período, ranqueado por, filtros ativos, gerado em ----
                            _periodo_pdf_temp = (
                                _periodo_considerado_temp(df_temp) or "Base completa (sem recorte de período)"
                            )
                            _filtros_ativos_pdf_temp = []
                            if f_mes:
                                _filtros_ativos_pdf_temp.append(f"Mês: {', '.join(f_mes)}")
                            if f_plano:
                                _filtros_ativos_pdf_temp.append(f"Plano: {', '.join(f_plano)}")
                            if f_especialidade:
                                _filtros_ativos_pdf_temp.append(f"Especialidade: {', '.join(f_especialidade)}")
                            for _rotulo_filtro_temp, _valor_filtro_temp in (
                                ("Procedimento", proc_sel_temp), ("Prestador", prest_sel_temp),
                                ("UF", uf_sel_temp), ("Região", regiao_sel_temp),
                                ("Cidade", cidade_sel_temp), ("Cluster", cluster_sel_temp),
                            ):
                                if _valor_filtro_temp != "Todos":
                                    _filtros_ativos_pdf_temp.append(f"{_rotulo_filtro_temp}: {_valor_filtro_temp}")
                            _texto_filtros_pdf_temp = (
                                "; ".join(_filtros_ativos_pdf_temp) if _filtros_ativos_pdf_temp
                                else "Nenhum filtro adicional — todos os prestadores/procedimentos do período"
                            )
                            _linhas_meta_temp = [
                                ("Período considerado", _periodo_pdf_temp),
                                ("Ranqueado por", ranquear_por_temp),
                                ("Filtros aplicados", _texto_filtros_pdf_temp),
                                ("Gerado em", datetime.now().strftime("%d/%m/%Y às %H:%M")),
                            ]
                            _tabela_meta_temp = Table(
                                [
                                    [Paragraph(f"<b>{html.escape(k)}</b>", estilo_corpo),
                                     Paragraph(html.escape(v), estilo_corpo)]
                                    for k, v in _linhas_meta_temp
                                ],
                                colWidths=[38 * mm, 144 * mm],
                            )
                            _tabela_meta_temp.setStyle(TableStyle([
                                ("BACKGROUND", (0, 0), (-1, -1), _COR_ZEBRA_PDF_TEMP),
                                ("BOX", (0, 0), (-1, -1), 0.5, _COR_BORDA_PDF_TEMP),
                                ("INNERGRID", (0, 0), (-1, -1), 0.5, rl_colors.white),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 4),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ]))
                            story.append(_tabela_meta_temp)
                            story.append(Spacer(1, 6))

                            # ---- legenda ----
                            story.append(Paragraph("Alerta de volume", estilo_secao))
                            _tabela_legenda_temp = Table(
                                [
                                    ["", Paragraph(
                                        "Volume ≥ 5× a média por prestador (alerta forte)", estilo_legenda
                                    )],
                                    ["", Paragraph(
                                        "Volume ≥ 2× a média por prestador (atenção moderada)", estilo_legenda
                                    )],
                                ],
                                colWidths=[6 * mm, 176 * mm], rowHeights=[6 * mm, 6 * mm],
                            )
                            _tabela_legenda_temp.setStyle(TableStyle([
                                ("BACKGROUND", (0, 0), (0, 0), _COR_ALERTA_PDF_TEMP),
                                ("BACKGROUND", (0, 1), (0, 1), _COR_ATENCAO_PDF_TEMP),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ]))
                            story.append(_tabela_legenda_temp)
                            story.append(Spacer(1, 8))

                            # ---- resumo em texto: só os prestadores em ALERTA FORTE (volume de
                            # procedimentos ≥ 5× a média por prestador) — a pedido do usuário, o
                            # resumo deixou de trazer atenção moderada e os desvios de CS acima/
                            # abaixo de 10 (isso tudo continua na grade/expanders da aba, só saiu
                            # deste resumo executivo). Cada prestador em alerta forte vira um bloco
                            # explicativo (não só números soltos): Qtde proced e Qtde por prestador
                            # da cidade lado a lado com uma frase comparando os dois, CS e CS da
                            # Cidade com outra frase comparando os dois, e o Índice de Atenção
                            # fechando com a explicação do que ele significa e de que "média" ele
                            # está falando (a média de procedimentos por prestador, na cidade dele
                            # ou, sem prestador suficiente na cidade, no Brasil todo).
                            story.append(Paragraph("Resumo — o que chama a atenção", estilo_secao))
                            if rank_temp.empty:
                                story.append(Paragraph("Nenhum prestador nos filtros atuais.", estilo_corpo))
                            else:
                                def _nome_prest_pdf_temp(row):
                                    _nome_temp = getattr(row, "NOME_PRESTADOR", None)
                                    if not _nome_temp or str(_nome_temp).strip() in ("", "—"):
                                        return f"Prestador {int(row.CD_PRESTADOR)}"
                                    return str(_nome_temp)

                                def _linha_alerta_forte_pdf_temp(row):
                                    _uf_temp = getattr(row, "UF", None) or "—"
                                    _cidade_temp = getattr(row, "CIDADE_PRESTADOR", None) or "—"
                                    _cluster_temp = getattr(row, "CLUSTER", None) or "—"

                                    _usa_cidade_temp = pd.notna(row.qtd_por_prestador_cidade)
                                    _qtd_ref_temp = (
                                        row.qtd_por_prestador_cidade if _usa_cidade_temp
                                        else row.qtd_por_prestador_nacional
                                    )
                                    _rotulo_ref_temp = "na cidade" if _usa_cidade_temp else "no Brasil"
                                    _fonte_texto_temp = "nesta cidade" if _usa_cidade_temp else "no Brasil todo"

                                    if pd.notna(row.indice_atencao_volume):
                                        _razao_fmt_temp = f"{row.indice_atencao_volume:.1f}".replace(".", ",")
                                        _comparacao_volume_temp = (
                                            f"Ou seja, esse prestador fez cerca de "
                                            f"<b>{_razao_fmt_temp} vezes</b> mais procedimentos do que a "
                                            f"média por prestador {_fonte_texto_temp}."
                                        )
                                        _indice_atencao_texto_temp = f"×{_razao_fmt_temp} acima da média"
                                    else:
                                        _comparacao_volume_temp = (
                                            "Sem referência de volume por prestador pra comparar nesta "
                                            "seleção (sem cidade/nacional disponível)."
                                        )
                                        _indice_atencao_texto_temp = html.escape(row.indice_atencao_volume_rotulo)

                                    if pd.notna(row.cs) and pd.notna(row.cs_cidade) and row.cs_cidade:
                                        _dif_pct_temp = (row.cs / row.cs_cidade - 1) * 100
                                        if abs(_dif_pct_temp) < 0.5:
                                            _comparacao_cs_temp = (
                                                "O CS desse prestador está no mesmo nível do CS médio "
                                                "praticado pelos prestadores dessa cidade."
                                            )
                                        else:
                                            _direcao_temp = "acima" if _dif_pct_temp > 0 else "abaixo"
                                            _comparacao_cs_temp = (
                                                f"O CS desse prestador está "
                                                f"<b>{abs(_dif_pct_temp):.0f}% {_direcao_temp}</b> do CS "
                                                f"médio praticado pelos prestadores dessa cidade."
                                            )
                                    else:
                                        _comparacao_cs_temp = "Sem CS de referência da cidade para comparar."

                                    # explicação do fallback pra média nacional só aparece quando ela
                                    # de fato foi usada (cidade sem prestadores suficientes pra comparar)
                                    if _usa_cidade_temp:
                                        _explicacao_indice_temp = (
                                            f"<i>(mostra quantas vezes o volume de procedimentos desse "
                                            f"prestador é maior que a média de procedimentos por "
                                            f"prestador — aqui, a média nesta cidade.)</i>"
                                        )
                                    else:
                                        _explicacao_indice_temp = (
                                            f"<i>(mostra quantas vezes o volume de procedimentos desse "
                                            f"prestador é maior que a média de procedimentos por "
                                            f"prestador — aqui, usada a média nacional pois na cidade "
                                            f"não tem prestadores suficientes para comparação.)</i>"
                                        )

                                    return (
                                        f"<b>{html.escape(_nome_prest_pdf_temp(row))}</b> — "
                                        f"{html.escape(str(_uf_temp))}, {html.escape(str(_cidade_temp))} "
                                        f"— Cluster {html.escape(str(_cluster_temp))}<br/><br/>"
                                        f"Qtde proced do prestador: {fmt_int(row.qtd_procedimentos)}<br/>"
                                        f"Qtde de proced por prestador {_rotulo_ref_temp}: "
                                        f"{fmt_float2(_qtd_ref_temp)}<br/>"
                                        f"{_comparacao_volume_temp}<br/><br/>"
                                        f"CS: {_fmt_cs_temp(row.cs)} <i>(Coeficiente de Severidade — mede "
                                        f"se o prestador praticou mais ou menos procedimentos do que o "
                                        f"esperado pela média nacional; nesse coeficiente, 10 é "
                                        f"considerado a média nacional — acima é mais severo, abaixo é "
                                        f"menos)</i><br/>"
                                        f"CS da Cidade: {_fmt_cs_temp(row.cs_cidade)}<br/>"
                                        f"{_comparacao_cs_temp}<br/><br/>"
                                        f"Índice de Atenção: {_indice_atencao_texto_temp} "
                                        f"{_explicacao_indice_temp}"
                                    )

                                def _bloco_alerta_forte_pdf_temp(df_lista, limite=5):
                                    for _r_temp in df_lista.head(limite).itertuples():
                                        story.append(Paragraph(
                                            _linha_alerta_forte_pdf_temp(_r_temp), estilo_corpo
                                        ))
                                        story.append(Spacer(1, 8))
                                    if len(df_lista) > limite:
                                        story.append(Paragraph(
                                            f"<i>...e mais {len(df_lista) - limite} prestador(es) em "
                                            f"alerta forte nesta seleção.</i>",
                                            estilo_corpo,
                                        ))
                                        story.append(Spacer(1, 4))

                                _total_prest_pdf_temp = len(rank_temp)
                                _validos_atencao_pdf_temp = rank_temp[rank_temp["indice_atencao_volume"].notna()]
                                _flag_alto_pdf_temp = _validos_atencao_pdf_temp[
                                    _validos_atencao_pdf_temp["indice_atencao_volume"] >= LIMIAR_ATENCAO_ALTO_TEMP
                                ].sort_values("indice_atencao_volume", ascending=False)

                                # Cor em vez de 🚩 (a fonte padrão do reportlab não tem esse glyph —
                                # mesma solução já usada nas tabelas de procedimento).
                                _ROTULO_ALTO_PDF_TEMP = '<font color="#e74c3c"><b>alerta forte</b></font>'

                                if _total_prest_pdf_temp == 1:
                                    if not _flag_alto_pdf_temp.empty:
                                        story.append(Paragraph(
                                            f"O prestador selecionado está em {_ROTULO_ALTO_PDF_TEMP} "
                                            f"— volume de procedimentos ≥ 5× a média por prestador.",
                                            estilo_corpo,
                                        ))
                                    else:
                                        story.append(Paragraph(
                                            "O prestador selecionado não está em alerta forte nesta "
                                            "seleção.", estilo_corpo,
                                        ))
                                else:
                                    if not _flag_alto_pdf_temp.empty:
                                        story.append(Paragraph(
                                            f"<b>{len(_flag_alto_pdf_temp)}</b> está(ão) em "
                                            f"{_ROTULO_ALTO_PDF_TEMP} — volume de procedimentos ≥ 5× a "
                                            f"média por prestador.",
                                            estilo_corpo,
                                        ))
                                    else:
                                        story.append(Paragraph(
                                            "Nenhum prestador está em alerta forte (volume de "
                                            "procedimentos ≥ 5× a média por prestador).",
                                            estilo_corpo,
                                        ))
                                story.append(Spacer(1, 4))
                                if not _flag_alto_pdf_temp.empty:
                                    _bloco_alerta_forte_pdf_temp(_flag_alto_pdf_temp)

                            # ---- gráficos ----
                            if not rank_temp.empty:
                                story.append(Paragraph("Visão geral", estilo_secao))
                                _buf_disp_temp = _grafico_dispersao_pdf_temp(rank_temp)
                                if _buf_disp_temp is not None:
                                    story.append(RLImage(_buf_disp_temp, width=180 * mm, height=80 * mm))
                                    story.append(Spacer(1, 4))
                                _coluna_metrica_pdf_temp = _OPCOES_RANQUEAR_TEMP.get(ranquear_por_temp, "cs")
                                _buf_top10_temp = _grafico_top10_pdf_temp(
                                    rank_temp, _coluna_metrica_pdf_temp, ranquear_por_temp
                                )
                                if _buf_top10_temp is not None:
                                    story.append(RLImage(_buf_top10_temp, width=180 * mm, height=80 * mm))
                                story.append(Spacer(1, 8))

                            # ---- detalhamento por prestador (mesmo conteúdo dos expanders, já "aberto") ----
                            story.append(
                                Paragraph(f"Detalhamento por prestador ({len(rank_temp)})", estilo_secao)
                            )
                            if rank_temp.empty:
                                story.append(Paragraph("Nenhum prestador nos filtros atuais.", estilo_corpo))
                            for _linha_pdf_temp in rank_temp.itertuples():
                                _rotulo_bruto_temp = _linha_pdf_temp.rotulo
                                if _rotulo_bruto_temp.startswith("🚩"):
                                    _cor_fundo_prest_temp = _COR_ALERTA_PDF_TEMP
                                elif _rotulo_bruto_temp.startswith("⚠️"):
                                    _cor_fundo_prest_temp = _COR_ATENCAO_PDF_TEMP
                                else:
                                    _cor_fundo_prest_temp = _COR_PRIMARIA_PDF_TEMP
                                _rotulo_limpo_temp = (
                                    _rotulo_bruto_temp.replace("🚩", "").replace("⚠️", "").strip()
                                )
                                _resumo_pdf_temp = (
                                    f"{html.escape(_rotulo_limpo_temp)}  —  "
                                    f"{fmt_int(_linha_pdf_temp.qtd_usuarios)} vidas · "
                                    f"{fmt_int(_linha_pdf_temp.qtd_procedimentos)} proced. · "
                                    f"CS {_fmt_cs_temp(_linha_pdf_temp.cs)} · "
                                    f"CS Cidade {_fmt_cs_temp(_linha_pdf_temp.cs_cidade)} · "
                                    f"{html.escape(_linha_pdf_temp.indice_atencao_volume_rotulo)}"
                                )
                                _cabecalho_prest_temp = Table(
                                    [[Paragraph(_resumo_pdf_temp, estilo_prestador)]],
                                    colWidths=[_LARGURA_UTIL_PDF_TEMP],
                                )
                                _cabecalho_prest_temp.setStyle(TableStyle([
                                    ("BACKGROUND", (0, 0), (-1, -1), _cor_fundo_prest_temp),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                ]))
                                story.append(_cabecalho_prest_temp)

                                _detalhe_pdf_temp = _detalhe_procedimentos_prestador_temp(
                                    _linha_pdf_temp.CD_PRESTADOR
                                )
                                if _detalhe_pdf_temp is None or _detalhe_pdf_temp.empty:
                                    story.append(
                                        Paragraph("Sem procedimentos pra detalhar.", estilo_corpo)
                                    )
                                else:
                                    _cabecalho_tabela_temp = [
                                        Paragraph(f"<b>{html.escape(str(c))}</b>", estilo_corpo)
                                        for c in _detalhe_pdf_temp.columns
                                    ]
                                    # A 1ª coluna (Procedimento) vem com 🚩/⚠️ na tela — a
                                    # fonte padrão do PDF não tem esses glyphs (viravam um
                                    # quadradinho preto sem sentido); troca por cor no próprio
                                    # texto (vermelho/laranja), mesma linguagem visual do
                                    # cabeçalho colorido de cada prestador.
                                    def _celula_procedimento_pdf_temp(valor):
                                        texto = str(valor)
                                        if texto.startswith("🚩"):
                                            cor_temp = "#e74c3c"
                                        elif texto.startswith("⚠️"):
                                            cor_temp = "#c98a00"
                                        else:
                                            return Paragraph(html.escape(texto), estilo_corpo)
                                        texto_limpo = texto.replace("🚩", "").replace("⚠️", "").strip()
                                        return Paragraph(
                                            f'<font color="{cor_temp}"><b>{html.escape(texto_limpo)}</b></font>',
                                            estilo_corpo,
                                        )

                                    _linhas_tabela_temp = [
                                        [
                                            _celula_procedimento_pdf_temp(v) if i == 0
                                            else Paragraph(html.escape(str(v)), estilo_corpo)
                                            for i, v in enumerate(linha)
                                        ]
                                        for linha in _detalhe_pdf_temp.itertuples(index=False, name=None)
                                    ]
                                    _pesos_col_temp = [40] + [10] * (len(_detalhe_pdf_temp.columns) - 1)
                                    _soma_pesos_temp = sum(_pesos_col_temp)
                                    _larguras_proc_temp = [
                                        _LARGURA_UTIL_PDF_TEMP * (w / _soma_pesos_temp) for w in _pesos_col_temp
                                    ]
                                    _tabela_proc_temp = Table(
                                        [_cabecalho_tabela_temp] + _linhas_tabela_temp,
                                        colWidths=_larguras_proc_temp, repeatRows=1,
                                    )
                                    _estilo_tabela_proc_temp = [
                                        ("BACKGROUND", (0, 0), (-1, 0), _COR_PRIMARIA_CLARA_PDF_TEMP),
                                        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _COR_PRIMARIA_PDF_TEMP),
                                        ("LINEBELOW", (0, 1), (-1, -1), 0.3, _COR_BORDA_PDF_TEMP),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                    ]
                                    for _i_zebra_temp in range(1, len(_linhas_tabela_temp) + 1, 2):
                                        _estilo_tabela_proc_temp.append((
                                            "BACKGROUND", (0, _i_zebra_temp), (-1, _i_zebra_temp),
                                            _COR_ZEBRA_PDF_TEMP,
                                        ))
                                    _tabela_proc_temp.setStyle(TableStyle(_estilo_tabela_proc_temp))
                                    story.append(_tabela_proc_temp)
                                story.append(Spacer(1, 6))

                            def _rodape_pdf_temp(canvas_temp, doc_temp):
                                canvas_temp.saveState()
                                canvas_temp.setFont("Helvetica", 7.5)
                                canvas_temp.setFillColor(rl_colors.HexColor("#8a97a3"))
                                canvas_temp.drawString(
                                    14 * mm, 10 * mm,
                                    "Painel de Gestão de Sinistro - Odonto — gerado automaticamente",
                                )
                                canvas_temp.drawRightString(
                                    A4[0] - 14 * mm, 10 * mm, f"Página {doc_temp.page}"
                                )
                                canvas_temp.restoreState()

                            doc.build(story, onFirstPage=_rodape_pdf_temp, onLaterPages=_rodape_pdf_temp)
                            buf_pdf.seek(0)
                            return buf_pdf.getvalue()

                        # ============================================================
                        # E-MAIL — mesmo conteúdo do "Resumo — o que chama a atenção" do
                        # PDF acima, só que em HTML pro corpo do e-mail (sem o PDF anexado
                        # — é um resumo rápido, não o relatório completo). Lógica paralela
                        # à de dentro de _gerar_pdf_ranking_temp (mesmas contas, mesmos
                        # limiares) — se um dia mudar o critério de "o que chama a
                        # atenção", replicar a mudança nos dois lugares.
                        # ============================================================
                        def _construir_partes_resumo_email_temp(rank_df):
                            # Só traz os prestadores em ALERTA FORTE (volume de procedimentos ≥ 5×
                            # a média por prestador) — mesma restrição do resumo do PDF (ver
                            # _linha_alerta_forte_pdf_temp), a pedido do usuário: o resumo por
                            # e-mail deixou de trazer atenção moderada e os desvios de CS acima/
                            # abaixo de 10, e cada prestador em alerta forte vira um bloco
                            # explicativo em vez de só números soltos numa linha.
                            if rank_df.empty:
                                return ["Nenhum prestador nos filtros atuais."]

                            def _nome_prest_email_temp(row):
                                _nome_temp = getattr(row, "NOME_PRESTADOR", None)
                                if not _nome_temp or str(_nome_temp).strip() in ("", "—"):
                                    return f"Prestador {int(row.CD_PRESTADOR)}"
                                return str(_nome_temp)

                            def _linha_alerta_forte_email_temp(row):
                                _uf_temp = getattr(row, "UF", None) or "—"
                                _cidade_temp = getattr(row, "CIDADE_PRESTADOR", None) or "—"
                                _cluster_temp = getattr(row, "CLUSTER", None) or "—"

                                _usa_cidade_temp = pd.notna(row.qtd_por_prestador_cidade)
                                _qtd_ref_temp = (
                                    row.qtd_por_prestador_cidade if _usa_cidade_temp
                                    else row.qtd_por_prestador_nacional
                                )
                                _rotulo_ref_temp = "na cidade" if _usa_cidade_temp else "no Brasil"
                                _fonte_texto_temp = "nesta cidade" if _usa_cidade_temp else "no Brasil todo"

                                if pd.notna(row.indice_atencao_volume):
                                    _razao_fmt_temp = f"{row.indice_atencao_volume:.1f}".replace(".", ",")
                                    _comparacao_volume_temp = (
                                        f"Ou seja, esse prestador fez cerca de "
                                        f"<strong>{_razao_fmt_temp} vezes</strong> mais procedimentos do "
                                        f"que a média por prestador {_fonte_texto_temp}."
                                    )
                                    _indice_atencao_texto_temp = f"×{_razao_fmt_temp} acima da média"
                                else:
                                    _comparacao_volume_temp = (
                                        "Sem referência de volume por prestador pra comparar nesta "
                                        "seleção (sem cidade/nacional disponível)."
                                    )
                                    _indice_atencao_texto_temp = html.escape(row.indice_atencao_volume_rotulo)

                                if pd.notna(row.cs) and pd.notna(row.cs_cidade) and row.cs_cidade:
                                    _dif_pct_temp = (row.cs / row.cs_cidade - 1) * 100
                                    if abs(_dif_pct_temp) < 0.5:
                                        _comparacao_cs_temp = (
                                            "O CS desse prestador está no mesmo nível do CS médio "
                                            "praticado pelos prestadores dessa cidade."
                                        )
                                    else:
                                        _direcao_temp = "acima" if _dif_pct_temp > 0 else "abaixo"
                                        _comparacao_cs_temp = (
                                            f"O CS desse prestador está "
                                            f"<strong>{abs(_dif_pct_temp):.0f}% {_direcao_temp}</strong> "
                                            f"do CS médio praticado pelos prestadores dessa cidade."
                                        )
                                else:
                                    _comparacao_cs_temp = "Sem CS de referência da cidade para comparar."

                                # explicação do fallback pra média nacional só aparece quando ela
                                # de fato foi usada (cidade sem prestadores suficientes pra comparar)
                                if _usa_cidade_temp:
                                    _explicacao_indice_temp = (
                                        f"<em>(mostra quantas vezes o volume de procedimentos desse "
                                        f"prestador é maior que a média de procedimentos por "
                                        f"prestador — aqui, a média nesta cidade.)</em>"
                                    )
                                else:
                                    _explicacao_indice_temp = (
                                        f"<em>(mostra quantas vezes o volume de procedimentos desse "
                                        f"prestador é maior que a média de procedimentos por "
                                        f"prestador — aqui, usada a média nacional pois na cidade "
                                        f"não tem prestadores suficientes para comparação.)</em>"
                                    )

                                return (
                                    f"<strong>{html.escape(_nome_prest_email_temp(row))}</strong> — "
                                    f"{html.escape(str(_uf_temp))}, {html.escape(str(_cidade_temp))} "
                                    f"— Cluster {html.escape(str(_cluster_temp))}<br><br>"
                                    f"Qtde proced do prestador: {fmt_int(row.qtd_procedimentos)}<br>"
                                    f"Qtde de proced por prestador {_rotulo_ref_temp}: "
                                    f"{fmt_float2(_qtd_ref_temp)}<br>"
                                    f"{_comparacao_volume_temp}<br><br>"
                                    f"CS: {_fmt_cs_temp(row.cs)} <em>(Coeficiente de Severidade — mede "
                                    f"se o prestador praticou mais ou menos procedimentos do que o "
                                    f"esperado pela média nacional; nesse coeficiente, 10 é "
                                    f"considerado a média nacional — acima é mais severo, abaixo é "
                                    f"menos)</em><br>"
                                    f"CS da Cidade: {_fmt_cs_temp(row.cs_cidade)}<br>"
                                    f"{_comparacao_cs_temp}<br><br>"
                                    f"Índice de Atenção: {_indice_atencao_texto_temp} "
                                    f"{_explicacao_indice_temp}"
                                )

                            def _bloco_alerta_forte_email_temp(partes, df_lista, limite=5):
                                for r in df_lista.head(limite).itertuples():
                                    partes.append(_linha_alerta_forte_email_temp(r))
                                if len(df_lista) > limite:
                                    partes.append(
                                        f"<em>...e mais {len(df_lista) - limite} prestador(es) em "
                                        f"alerta forte nesta seleção.</em>"
                                    )

                            _ALTO_HTML_TEMP = (
                                '<span style="color:#e74c3c;font-weight:bold;">alerta forte</span>'
                            )

                            _total_email_temp = len(rank_df)
                            _validos_atencao_email_temp = rank_df[rank_df["indice_atencao_volume"].notna()]
                            _flag_alto_email_temp = _validos_atencao_email_temp[
                                _validos_atencao_email_temp["indice_atencao_volume"] >= LIMIAR_ATENCAO_ALTO_TEMP
                            ].sort_values("indice_atencao_volume", ascending=False)

                            _partes_temp = []

                            if _total_email_temp == 1:
                                if not _flag_alto_email_temp.empty:
                                    _partes_temp.append(
                                        f"O prestador selecionado está em {_ALTO_HTML_TEMP} — volume "
                                        f"de procedimentos ≥ 5× a média por prestador."
                                    )
                                else:
                                    _partes_temp.append(
                                        "O prestador selecionado não está em alerta forte nesta "
                                        "seleção."
                                    )
                            else:
                                if not _flag_alto_email_temp.empty:
                                    _partes_temp.append(
                                        f"<strong>{len(_flag_alto_email_temp)}</strong> está(ão) em "
                                        f"{_ALTO_HTML_TEMP} — volume de procedimentos ≥ 5× a média por "
                                        f"prestador."
                                    )
                                else:
                                    _partes_temp.append(
                                        "Nenhum prestador está em alerta forte (volume de procedimentos "
                                        "≥ 5× a média por prestador)."
                                    )

                            if not _flag_alto_email_temp.empty:
                                _bloco_alerta_forte_email_temp(_partes_temp, _flag_alto_email_temp)

                            return _partes_temp

                        st.divider()
                        st.markdown("**📄 Relatório em PDF**")
                        st.caption(
                            "Gera um PDF com os filtros atuais desta aba: cabeçalho com a logo, "
                            "período trabalhado e filtros aplicados, legenda, um resumo em texto "
                            "do que chama a atenção (🚩/⚠️) e do que desvia (CS acima/abaixo de "
                            "10) nesta seleção, gráficos (dispersão CS × volume e Top 10 pela "
                            "métrica de \"Ranquear por\") e o detalhamento por prestador já "
                            "\"aberto\" (mesmo conteúdo dos expanders logo abaixo)."
                        )
                        # Trava: nunca deixa gerar o PDF com a base toda (sem nenhum recorte) —
                        # obrigatório escolher pelo menos UF, Cidade, Cluster ou Prestador ali
                        # em cima. Procedimento/Região sozinhos não contam.
                        _tem_filtro_pdf_temp = (
                            uf_sel_temp != "Todos" or cidade_sel_temp != "Todos"
                            or cluster_sel_temp != "Todos" or prest_sel_temp != "Todos"
                        )
                        if not _tem_filtro_pdf_temp:
                            st.warning(
                                "Selecione pelo menos UF, Cidade, Cluster ou Prestador nos "
                                "filtros acima pra liberar o PDF — ele nunca pode ser gerado "
                                "com a base toda."
                            )
                        col_gerar_pdf_temp, col_baixar_pdf_temp = st.columns([1, 2])
                        with col_gerar_pdf_temp:
                            if st.button(
                                "📄 Gerar PDF", key="gerar_pdf_ranking_temp", use_container_width=True,
                                disabled=not _tem_filtro_pdf_temp,
                            ):
                                with st.spinner("Gerando PDF..."):
                                    _pdf_bytes_temp = _gerar_pdf_ranking_temp()
                                if _pdf_bytes_temp:
                                    st.session_state["pdf_ranking_bytes_temp"] = _pdf_bytes_temp
                                    st.session_state["pdf_ranking_nome_temp"] = (
                                        f"ranking_odonto_{datetime.now():%Y%m%d_%H%M}.pdf"
                                    )
                        with col_baixar_pdf_temp:
                            if st.session_state.get("pdf_ranking_bytes_temp"):
                                st.download_button(
                                    "⬇️ Baixar PDF",
                                    data=st.session_state["pdf_ranking_bytes_temp"],
                                    file_name=st.session_state.get(
                                        "pdf_ranking_nome_temp", "ranking_odonto.pdf"
                                    ),
                                    mime="application/pdf",
                                    key="baixar_pdf_ranking_temp",
                                    use_container_width=True,
                                )

                        st.markdown("**📧 Resumo por e-mail**")
                        st.caption(
                            "Envia por e-mail só o texto do \"Resumo — o que chama a atenção\" "
                            "desta seleção (sem anexar o PDF) — mesma trava de filtro do PDF "
                            "acima: nunca envia com a base toda."
                        )
                        _destino_email_resumo_temp = st.text_input(
                            "E-mail(s) de destino (separe por vírgula)",
                            key="destino_email_resumo_ranking_temp",
                            placeholder="nome@empresa.com, outro@empresa.com",
                        )
                        if st.button(
                            "📧 Enviar resumo por e-mail", key="enviar_email_resumo_ranking_temp",
                            disabled=not _tem_filtro_pdf_temp,
                        ):
                            _destinatarios_resumo_temp = [
                                e.strip() for e in _destino_email_resumo_temp.split(",") if e.strip()
                            ]
                            _invalidos_email_temp = [e for e in _destinatarios_resumo_temp if "@" not in e]
                            if not _destinatarios_resumo_temp:
                                st.error("Informe pelo menos um e-mail de destino.")
                            elif _invalidos_email_temp:
                                st.error(f"E-mail(s) inválido(s): {', '.join(_invalidos_email_temp)}")
                            else:
                                # Mesmos metadados (período/filtros) montados dentro de
                                # _gerar_pdf_ranking_temp acima, recalculados aqui porque são
                                # locais aquela função — mantenha os dois em sincronia se o
                                # formato mudar.
                                _periodo_email_temp = (
                                    _periodo_considerado_temp(df_temp)
                                    or "Base completa (sem recorte de período)"
                                )
                                _filtros_ativos_email_temp = []
                                if f_mes:
                                    _filtros_ativos_email_temp.append(f"Mês: {', '.join(f_mes)}")
                                if f_plano:
                                    _filtros_ativos_email_temp.append(f"Plano: {', '.join(f_plano)}")
                                if f_especialidade:
                                    _filtros_ativos_email_temp.append(
                                        f"Especialidade: {', '.join(f_especialidade)}"
                                    )
                                for _rotulo_filtro_temp, _valor_filtro_temp in (
                                    ("Procedimento", proc_sel_temp), ("Prestador", prest_sel_temp),
                                    ("UF", uf_sel_temp), ("Região", regiao_sel_temp),
                                    ("Cidade", cidade_sel_temp), ("Cluster", cluster_sel_temp),
                                ):
                                    if _valor_filtro_temp != "Todos":
                                        _filtros_ativos_email_temp.append(
                                            f"{_rotulo_filtro_temp}: {_valor_filtro_temp}"
                                        )
                                _texto_filtros_email_temp = (
                                    "; ".join(_filtros_ativos_email_temp) if _filtros_ativos_email_temp
                                    else "Nenhum filtro adicional — todos os prestadores/procedimentos do período"
                                )
                                with st.spinner("Enviando e-mail..."):
                                    _partes_resumo_email_temp = _construir_partes_resumo_email_temp(rank_temp)
                                    _ok_email_resumo_temp, _erro_email_resumo_temp = (
                                        enviar_email_resumo_ranking_temp(
                                            _destinatarios_resumo_temp, _periodo_email_temp,
                                            ranquear_por_temp, _texto_filtros_email_temp,
                                            _partes_resumo_email_temp,
                                        )
                                    )
                                if _ok_email_resumo_temp:
                                    st.success(f"E-mail enviado para {', '.join(_destinatarios_resumo_temp)}.")
                                else:
                                    st.error(f"Erro ao enviar e-mail: {_erro_email_resumo_temp}")

                    if _sufixo_aba_temp == "_ranking" and not rank_temp.empty:
                        st.caption(
                            "Abra um prestador abaixo pra ver o detalhamento por procedimento "
                            "(mesmas colunas de antes, uma linha por procedimento em vez de "
                            "somadas). O título já traz o resumo do prestador."
                        )
                        # st.container(height=...) — caixa com rolagem própria (recurso nativo
                        # do Streamlit, não é gambiarra de CSS): a lista de prestadores rola
                        # AQUI DENTRO, sem precisar rolar a página inteira até o fim pra
                        # alcançar o que vem depois (benchmark, gráficos etc.). Altura fixa em
                        # pixels — 480px dá pra uns 4-5 expanders fechados por vez.
                        with st.container(height=480):
                            for _linha_prest_exp_temp in rank_temp.itertuples():
                                _cd_prest_exp_temp = _linha_prest_exp_temp.CD_PRESTADOR
                                _resumo_prest_exp_temp = (
                                    f"{_linha_prest_exp_temp.rotulo}  —  "
                                    f"{fmt_int(_linha_prest_exp_temp.qtd_usuarios)} vidas · "
                                    f"{fmt_int(_linha_prest_exp_temp.qtd_procedimentos)} proced. · "
                                    f"CS {_fmt_cs_temp(_linha_prest_exp_temp.cs)} · "
                                    f"CS Cidade {_fmt_cs_temp(_linha_prest_exp_temp.cs_cidade)} · "
                                    f"{_linha_prest_exp_temp.indice_atencao_volume_rotulo}"
                                )
                                with st.expander(_resumo_prest_exp_temp):
                                    _exib_detalhe_proc_temp = _detalhe_procedimentos_prestador_temp(
                                        _cd_prest_exp_temp
                                    )
                                    if _exib_detalhe_proc_temp is None:
                                        st.caption("Sem procedimentos pra detalhar.")
                                    else:
                                        _tabela_html_temp(_exib_detalhe_proc_temp, scroll=False)

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
                        # key único (por aba + título do gráfico) — evita colisão de ID se esse
                        # bloco vier a ser reaproveitado por outra aba no futuro (ver
                        # _config_abas_cs_temp acima).
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
