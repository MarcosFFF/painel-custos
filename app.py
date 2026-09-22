import streamlit as st
import pandas as pd
import numpy as np
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
# ---------- monitor de memória (RAM) ----------
# Ajuda a diagnosticar o app "parando de rodar" no Streamlit Community Cloud, que
# costuma ser estouro do limite de memória do plano (~1 GB por app, valor
# aproximado — o oficial varia entre ~690 MB e 2,7 GB conforme a carga geral da
# plataforma). Atualiza a cada interação (o Streamlit reexecuta o script inteiro
# a cada rerun, então o valor mostrado é sempre o consumo "agora"). psutil é
# opcional: se ainda não estiver no requirements.txt do servidor, o try/except
# evita que o painel inteiro quebre por causa só desse indicador — ele
# simplesmente não aparece até o requirements.txt ser atualizado e o app
# reiniciado.
try:
    import psutil
    _mem_mb_temp = psutil.Process().memory_info().rss / (1024 ** 2)
    _limite_mb_temp = 1024.0  # ~1 GB — limite aproximado do plano gratuito
    _pct_mem_temp = min(_mem_mb_temp / _limite_mb_temp, 1.0)
    if _pct_mem_temp >= 0.9:
        _icone_mem_temp = "🔴"
    elif _pct_mem_temp >= 0.7:
        _icone_mem_temp = "🟡"
    else:
        _icone_mem_temp = "🟢"
    st.sidebar.caption(
        f"{_icone_mem_temp} Memória em uso: **"
        f"{_mem_mb_temp:,.0f}".replace(",", ".") + " MB** de ~1.024 MB "
        "(limite aproximado do plano gratuito do Streamlit Cloud)"
    )
    st.sidebar.progress(_pct_mem_temp)
    # ---------- libera cache acumulado quando a memória aperta ----------
    # ranking_severidade / calcular_media_nacional / alertas_prestador_procedimento
    # (severidade.py, cacheados com @st.cache_data) guardam 1 entrada nova pra cada
    # combinação de filtro (Mês/Plano/Especialidade/UF/Cidade/Cluster/Prestador/
    # Procedimento) que a sessão testa — sem limite automático de tamanho, então
    # ficam acumulando pra sempre. Numa sessão testando vários filtros ao longo do
    # tempo, isso empilha e é o principal motivo do app se aproximar do limite de
    # RAM do plano gratuito mesmo sem nenhuma aba pesada. Em vez de tirar mês ou
    # funcionalidade disponível, a saída é liberar esses 3 caches (NÃO o de
    # carregar_base_severidade — esse é o carregamento caro que precisa continuar
    # guardado) assim que a memória passa de 75% do limite: a próxima chamada
    # recalcula na hora (rápido, é só a combinação de filtro atual), mas as
    # combinações antigas acumuladas na memória são liberadas de vez. Só libera 1x
    # por "aperto" (flag em session_state), pra não ficar recalculando à toa a cada
    # rerun; a flag reseta quando a memória volta a ficar folgada (<50%), liberando
    # de novo se precisar.
    if _pct_mem_temp >= 0.75 and not st.session_state.get("_cache_liberado_mem_temp", False):
        for _fn_cache_temp in (ranking_severidade, calcular_media_nacional, alertas_prestador_procedimento):
            _fn_cache_temp.clear()
        st.session_state["_cache_liberado_mem_temp"] = True
    elif _pct_mem_temp < 0.5:
        st.session_state["_cache_liberado_mem_temp"] = False
except Exception:
    pass
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
def _agora_brasilia_temp():
    """Horário atual em Brasília (America/Sao_Paulo) — usado nos textos "Gerado em".
    Cai pra UTC-3 fixo (Brasil não tem mais horário de verão) se o ambiente não tiver
    o banco de fusos horários (zoneinfo/tzdata) disponível."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        from datetime import timezone, timedelta
        return datetime.now(timezone(timedelta(hours=-3)))
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
    msg["Subject"] = f"Projeção Sinistro - {titulo_mes}"
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
    # Só Ranking. (Resumo e Projeção de Credenciamento ocultas — o corpo de
    # Resumo está comentado logo abaixo, em "with tab_resumo:"; o de Projeção de
    # Credenciamento foi removido junto com sua aba a pedido do usuário em
    # 22/09 — pra trazer alguma de volta, é reescrever o bloco "with tab_x:" e
    # devolver o label/desempacotamento aqui.)
    _labels_abas_temp = [
        "📊 Ranking",
    ]
    _abas_criadas_temp = st.tabs(_labels_abas_temp)
    (tab_ranking_temp,) = (
        _abas_criadas_temp[0],
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
#     with tab_resumo:
#         st.markdown("#### 📌 Resumo do mês vs. mês anterior")
#         st.caption(
#             "Compara o último mês com o anterior pela **variação % de uso** (não em números "
#             "absolutos). Clique num item abaixo para expandir e ver o que causou o aumento. "
#             f"Só entram grupos com volume ≥ {volume_minimo} procedimentos em ambos os meses "
#             "(ajustável no filtro acima)."
#         )
#         resumo, msg_resumo = resumo_comparativo(df_filtrado, volume_minimo=volume_minimo, usuarios=usuarios_filtrado)
#         if resumo is None:
#             st.info(msg_resumo)
#         else:
#             st.caption(msg_resumo)

#             def _fmt_pct(v):
#                 return f"{v:+.1f}%" if pd.notna(v) else "—"

#             def _linha_resumo(row):
#                 """Grade de 1 linha com o resumo (uso e vidas) do item expandido — especialidade ou UF."""
#                 dados = {
#                     "Soma uso atual": [fmt_int(row.get("soma_uso_atual"))],
#                     "Soma uso anterior": [fmt_int(row.get("soma_uso_anterior"))],
#                     "Variação uso": [_fmt_pct(row.get("variacao_pct"))],
#                     "Qtde de vidas atual": [fmt_int(row.get("qtd_usuarios_atual"))],
#                     "Qtde de vidas anterior": [fmt_int(row.get("qtd_usuarios_anterior"))],
#                     "Variação de vidas": [_fmt_pct(row.get("variacao_vidas_pct"))],
#                 }
#                 st.dataframe(pd.DataFrame(dados), hide_index=True, use_container_width=True)

#             def _tabela_detalhe(det, coluna_chave, label_chave, extra_cols=None):
#                 """
#                 Grade de detalhe (procedimentos dentro de uma especialidade, cidades dentro
#                 de uma UF etc.). extra_cols: lista de (coluna, rótulo) inseridas logo após
#                 a coluna-chave (ex.: Cluster ao lado de Cidade).
#                 """
#                 if det is None or det.empty:
#                     return
#                 colunas_ordem = [coluna_chave]
#                 renome = {coluna_chave: label_chave}
#                 if extra_cols:
#                     for col, label in extra_cols:
#                         colunas_ordem.append(col)
#                         renome[col] = label
#                 colunas_ordem += [
#                     "soma_uso_atual", "soma_uso_anterior", "variacao_pct",
#                     "qtd_usuarios_atual", "qtd_usuarios_anterior", "variacao_vidas_pct",
#                 ]
#                 renome.update({
#                     "soma_uso_atual": "Soma uso atual",
#                     "soma_uso_anterior": "Soma uso anterior",
#                     "variacao_pct": "Variação uso",
#                     "qtd_usuarios_atual": "Qtde de vidas atual",
#                     "qtd_usuarios_anterior": "Qtde de vidas anterior",
#                     "variacao_vidas_pct": "Variação de vidas",
#                 })
#                 colunas_ordem = [c for c in colunas_ordem if c in det.columns]
#                 det_show = det[colunas_ordem].copy()
#                 det_show["variacao_pct"] = det_show["variacao_pct"].map(_fmt_pct)
#                 if "variacao_vidas_pct" in det_show.columns:
#                     det_show["variacao_vidas_pct"] = det_show["variacao_vidas_pct"].map(_fmt_pct)
#                 for c in ["soma_uso_atual", "soma_uso_anterior", "qtd_usuarios_atual", "qtd_usuarios_anterior"]:
#                     if c in det_show.columns:
#                         det_show[c] = det_show[c].map(fmt_int)
#                 det_show = det_show.rename(columns=renome)
#                 st.dataframe(det_show, hide_index=True, use_container_width=True)

#             # Repetido perto de cada lista (não só no topo da aba) e usado pro aviso de item
#             # negativo: essas listas são sempre "top N por variação" — se não existirem N grupos
#             # realmente subindo, a lista completa a cota com quem caiu menos, ainda assim rotulado
#             # "maior aumento". O sinal (+/-) de cada variação mostra a diferença.
#             _aviso_periodo_resumo = (
#                 "📅 Comparação sempre no mesmo período em ambos os meses (detalhe completo no "
#                 "topo desta aba)."
#             )

#             def _rotulo_variacao(v):
#                 if pd.isna(v):
#                     return "Variação de uso: —"
#                 aviso = "⚠️ caiu, não subiu — " if v < 0 else ""
#                 return f"{aviso}Variação de uso: {v:+.1f}%"

#             # ---------- Especialidades ----------
#             especialidades = resumo["especialidades"]
#             if especialidades.empty:
#                 st.markdown("##### 5 especialidades com maior aumento")
#                 st.info("Nenhuma especialidade com volume suficiente nos dois meses para comparar.")
#             else:
#                 st.caption(_aviso_periodo_resumo)
#                 if (especialidades["variacao_pct"] < 0).any():
#                     st.warning(
#                         "Nem todas as 5 abaixo tiveram alta de verdade — como faltaram "
#                         "especialidades subindo o suficiente pra completar a lista, ela trouxe "
#                         "também quem caiu menos (marcado com ⚠️ abaixo)."
#                     )
#                 with st.expander("5 especialidades com maior aumento", expanded=False):
#                     for _, row in especialidades.iterrows():
#                         titulo = f"{row['ESPECIALIDADE']} · {_rotulo_variacao(row['variacao_pct'])}"
#                         with st.container(border=True):
#                             st.markdown(f"**{titulo}**")
#                             _linha_resumo(row)
#                             det = resumo["detalhes_especialidade"].get(row["ESPECIALIDADE"])
#                             if det is not None and not det.empty:
#                                 st.markdown("**Procedimentos que causaram o aumento:**")
#                                 _tabela_detalhe(det, "NOME_PROCEDIMENTO", "Procedimento")
#         st.divider()
#         if resumo is not None:
#             # ---------- UFs ----------
#             ufs = resumo["ufs"]
#             if ufs.empty:
#                 st.markdown("##### 10 UFs com maior aumento")
#                 st.info("Nenhuma UF com volume suficiente nos dois meses para comparar.")
#             else:
#                 st.caption(_aviso_periodo_resumo)
#                 if (ufs["variacao_pct"] < 0).any():
#                     st.warning(
#                         "Nem todas as 10 abaixo tiveram alta de verdade — como faltaram UFs "
#                         "subindo o suficiente pra completar a lista, ela trouxe também quem caiu "
#                         "menos (marcado com ⚠️ abaixo)."
#                     )
#                 with st.expander("10 UFs com maior aumento", expanded=False):
#                     for _, row in ufs.iterrows():
#                         titulo = f"{row['UF']} · {_rotulo_variacao(row['variacao_pct'])}"
#                         with st.container(border=True):
#                             st.markdown(f"**{titulo}**")
#                             _linha_resumo(row)
#                             det = resumo["detalhes_uf"].get(row["UF"])
#                             if det is not None and not det.empty:
#                                 st.markdown("**Cidades (com cluster) que causaram o aumento:**")
#                                 _tabela_detalhe(det, "CIDADE_PRESTADOR", "Cidade", extra_cols=[("CLUSTER", "Cluster")])
#         st.divider()
#         if resumo is not None:
#             # ---------- Prestadores ----------
#             prestadores = resumo["prestadores"]
#             if prestadores.empty:
#                 st.markdown("##### 20 prestadores com maior aumento")
#                 st.info("Nenhum prestador com volume suficiente nos dois meses para comparar.")
#             else:
#                 st.caption(_aviso_periodo_resumo)
#                 if (prestadores["variacao_pct"] < 0).any():
#                     st.warning(
#                         "Nem todos os 20 abaixo tiveram alta de verdade — como faltaram "
#                         "prestadores subindo o suficiente pra completar a lista, ela trouxe "
#                         "também quem caiu menos (marcado com ⚠️ abaixo)."
#                     )
#                 with st.expander("20 prestadores com maior aumento", expanded=False):
#                     for _, row in prestadores.iterrows():
#                         nome = row.get("NOME_PRESTADOR") or f"Prestador {int(row['CD_PRESTADOR'])}"
#                         st.markdown(
#                             f"- **{nome}** — CPF/CNPJ: {row.get('CNPJ_CPF_PRESTADOR') or '—'} · "
#                             f"{row.get('UF') or '—'} · {row.get('CIDADE') or '—'} · Cluster: {row.get('CLUSTER') or '—'} · "
#                             f"Especialidade principal: {row.get('ESPECIALIDADE') or '—'} · "
#                             f"{_rotulo_variacao(row['variacao_pct'])}"
#                         )
#         st.divider()
#         # ---------- Alerta: prestador + procedimento com aumento relevante de qtde e valor ----------
#         with st.expander("🚨 Prestadores com aumento relevante de quantidade e valor", expanded=False):
#             st.caption(
#                 "Critério (as 5 condições precisam valer juntas): qtde do procedimento no mês atual "
#                 "> 50, aumento de valor pago > R$ 1.500,00 em relação ao mês anterior, variação de "
#                 "pelo menos 50% tanto na qtde quanto no valor, e variação do FASE de pelo menos 50% "
#                 "entre os dois meses. Qtde e valor usam números absolutos (qtde de guias e R$ pago) — "
#                 "o FASE é calculado no mesmo recorte (prestador + especialidade + procedimento), um "
#                 "valor por mês."
#             )
#             alertas, msg_alertas = alertas_prestador_procedimento(df_filtrado, usuarios=usuarios_filtrado)
#             if alertas is None or alertas.empty:
#                 st.info(msg_alertas)
#             else:
#                 st.caption(msg_alertas)
#                 mes_anterior_lbl = label_mes(alertas["MES_ANTERIOR"].iloc[0])
#                 mes_atual_lbl = label_mes(alertas["MES_ATUAL"].iloc[0])
#                 for cd_prestador, grupo in alertas.groupby("CD_PRESTADOR", sort=False):
#                     r0 = grupo.iloc[0]
#                     nome = r0.get("NOME_PRESTADOR") or f"Prestador {int(cd_prestador)}"
#                     cabecalho = (
#                         f"{nome} — {r0.get('CIDADE') or '—'}/{r0.get('UF') or '—'} · "
#                         f"CPF/CNPJ: {r0.get('CNPJ_CPF_PRESTADOR') or '—'} · Cluster: {r0.get('CLUSTER') or '—'}"
#                     )
#                     with st.container(border=True):
#                         st.markdown(f"**{cabecalho}**")
#                         for _, row in grupo.iterrows():
#                             texto = (
#                                 f"**{nome}** ({row.get('CIDADE') or '—'}, CPF/CNPJ {row.get('CNPJ_CPF_PRESTADOR') or '—'}, "
#                                 f"cluster {row.get('CLUSTER') or '—'}) teve aumento de **{row['variacao_qtd_pct']:+.0f}%** "
#                                 f"na quantidade em relação a {mes_anterior_lbl}. Esse aumento aconteceu na especialidade "
#                                 f"**{row['ESPECIALIDADE']}**, no procedimento **{row['NOME_PROCEDIMENTO']}**, que foi de "
#                                 f"{fmt_int(row['qtd_anterior'])} para {fmt_int(row['qtd_atual'])} solicitações. "
#                                 f"Em termos de valores, em {mes_anterior_lbl} foi {fmt_brl(row['valor_anterior'])} e em "
#                                 f"{mes_atual_lbl} foi de {fmt_brl(row['valor_atual'])}, um aumento de "
#                                 f"**{fmt_brl(row['delta_valor'])}**, que representa **{row['variacao_valor_pct']:+.0f}%**."
#                             )
#                             if pd.notna(row.get("variacao_usuarios_pct")):
#                                 texto += (
#                                     f" Em termos de vidas, em {mes_anterior_lbl} foram {fmt_int(row['usuarios_anterior'])} "
#                                     f"e em {mes_atual_lbl} foram {fmt_int(row['usuarios_atual'])}, uma variação de "
#                                     f"**{row['variacao_usuarios_pct']:+.0f}%**."
#                                 )
#                             else:
#                                 texto += (
#                                     f" Em termos de vidas, em {mes_anterior_lbl} foram {fmt_int(row['usuarios_anterior'])} "
#                                     f"e em {mes_atual_lbl} foram {fmt_int(row['usuarios_atual'])}."
#                                 )
#                             if pd.notna(row.get("fase_anterior")) and pd.notna(row.get("fase_atual")):
#                                 if row["fase_atual"] < 0.009:
#                                     texto += " Sem variação relevante no FASE."
#                                 else:
#                                     texto += (
#                                         f" O FASE em {mes_anterior_lbl} foi {fmt_fase(row['fase_anterior'])} e em "
#                                         f"{mes_atual_lbl} foi {fmt_fase(row['fase_atual'])}, com variação de "
#                                         f"**{row['variacao_fase_pct']:+.0f}%**."
#                                     )
#                             st.markdown(texto)
