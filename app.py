import streamlit as st
import pandas as pd
import os
from datetime import date, datetime
from supabase import create_client, Client
from projecao_sinistro import projetar_sinistro_mes_atual, projetar_dias_restantes

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
html, body, [class*="css"]  { font-size: 14px !important; }
h1 { font-size: 1.6rem !important; }
h2 { font-size: 1.3rem !important; }
h3 { font-size: 1.1rem !important; }
[data-testid="stMetricValue"] { font-size: 1.3rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.78rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }
.stCaption, [data-testid="stCaptionContainer"] { font-size: 0.75rem !important; }
div[data-testid="stDataFrame"] * { font-size: 0.8rem !important; }
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
        col_logo, col_txt = st.columns([1, 6])
        with col_logo:
            st.image(LOGO_PATH, width=70)
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

def calibrar_baseline_mensal(mes_key_atual):
    ano_atual, mes_num = (int(x) for x in mes_key_atual.split("-"))
    chave_ano_anterior = mes_key(ano_atual - 1, mes_num)
    dado_ano_anterior = st.session_state.historico_mensal.get(chave_ano_anterior)
    valor_ano_anterior = None
    if dado_ano_anterior:
        valor_ano_anterior = dado_ano_anterior["real"] if dado_ano_anterior["real"] is not None else dado_ano_anterior["projetado"]

    chaves = sorted(k for k in st.session_state.historico_mensal if k < mes_key_atual)
    recentes = chaves[-6:]
    valores_recentes = []
    for k in recentes:
        d = st.session_state.historico_mensal[k]
        v = d["real"] if d["real"] is not None else d["projetado"]
        if v is not None:
            valores_recentes.append(v)
    media_recente = sum(valores_recentes) / len(valores_recentes) if valores_recentes else None

    if valor_ano_anterior is not None and media_recente is not None:
        return {"baseline": (valor_ano_anterior + media_recente) / 2,
                "fonte": f"média entre {label_mes(chave_ano_anterior)} (ano anterior) e os últimos {len(valores_recentes)} meses"}
    if valor_ano_anterior is not None:
        return {"baseline": valor_ano_anterior, "fonte": f"{label_mes(chave_ano_anterior)} (ano anterior)"}
    if media_recente is not None:
        return {"baseline": media_recente, "fonte": f"média dos últimos {len(valores_recentes)} meses fechados"}
    return None

def calcular_indice_dow():
    """Sazonalidade por dia da semana, aprendida dos lançamentos ao vivo (não só da semente)."""
    por_mes = {}
    for key, valor in st.session_state.lancamentos.items():
        mk = key[:7]
        por_mes.setdefault(mk, []).append(valor)
    media_mes = {mk: sum(v) / len(v) for mk, v in por_mes.items()}

    soma = [0.0] * 7
    cont = [0] * 7
    for key, valor in st.session_state.lancamentos.items():
        mk = key[:7]
        if media_mes.get(mk, 0) == 0:
            continue
        y, m, d = (int(x) for x in key.split("-"))
        wd = date(y, m, d).weekday()
        soma[wd] += valor / media_mes[mk]
        cont[wd] += 1
    return [soma[i] / cont[i] if cont[i] > 0 else 1.0 for i in range(7)]

def projecao_sazonal_de(y, m, total, entradas, acumulado, mes_key_atual):
    n = len(entradas)
    if n == 0:
        return {"final": acumulado, "baseline": None, "peso_atual": 0, "fonte": None}
    if n == total:
        return {"final": acumulado, "baseline": None, "peso_atual": 1, "fonte": "mês completo — 100% dado real"}

    info = calibrar_baseline_mensal(mes_key_atual)
    if info is None:
        return {"final": max(acumulado, 0), "baseline": None, "peso_atual": 1, "fonte": None}

    dow_idx = calcular_indice_dow()
    indices_do_mes = [dow_idx[date(y, m, d).weekday()] for d in range(1, total + 1)]
    soma_indices = sum(indices_do_mes)
    baseline_diario = [info["baseline"] * (idx / soma_indices) for idx in indices_do_mes]

    soma_baseline_com_dado = sum(baseline_diario[d - 1] for d in entradas)
    escala = acumulado / soma_baseline_com_dado if soma_baseline_com_dado > 0 else 1
    rr_atual_sazonal = escala * info["baseline"]

    K = 16  # meia-vida em dias corridos lançados
    peso_atual = n / (n + K)
    blend = peso_atual * rr_atual_sazonal + (1 - peso_atual) * info["baseline"]
    return {"final": max(blend, acumulado), "baseline": info["baseline"], "peso_atual": peso_atual, "fonte": info["fonte"]}

# ============================================================
# LOGIN
# ============================================================
if "user_email" not in st.session_state:
    st.session_state.user_email = None
    st.session_state.role = None

if st.session_state.user_email is None:
    titulo_com_logo()
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
col_titulo, col_user = st.columns([3, 1])
with col_titulo:
    titulo_com_logo()
with col_user:
    nome_exibicao = st.session_state.get("nome_usuario") or st.session_state.user_email
    badge = "🟢 Administrador" if is_admin else "🔵 Visualização"
    st.write(f"**{nome_exibicao}**")
    st.caption(badge)
    if st.button("Sair", use_container_width=True):
        fazer_logout()
        st.rerun()

# ---------- navegação de mês ----------
if "view_year" not in st.session_state:
    st.session_state.view_year = ANO_HOJE
    st.session_state.view_month = MES_HOJE

c1, c2, c3, c4 = st.columns([1, 3, 1, 2])
with c1:
    if st.button("◀", use_container_width=True):
        vy, vm = st.session_state.view_year, st.session_state.view_month - 1
        if vm < 1:
            vm, vy = 12, vy - 1
        st.session_state.view_year, st.session_state.view_month = vy, vm
        st.rerun()
with c2:
    st.markdown(f"### {MESES[st.session_state.view_month - 1]} / {st.session_state.view_year}")
with c3:
    eh_mes_atual_nav = (st.session_state.view_year == ANO_HOJE and st.session_state.view_month == MES_HOJE)
    if st.button("▶", use_container_width=True, disabled=eh_mes_atual_nav):
        vy, vm = st.session_state.view_year, st.session_state.view_month + 1
        if vm > 12:
            vm, vy = 1, vy + 1
        st.session_state.view_year, st.session_state.view_month = vy, vm
        st.rerun()
with c4:
    if not eh_mes_atual_nav:
        if st.button("Ir para o mês atual"):
            st.session_state.view_year, st.session_state.view_month = ANO_HOJE, MES_HOJE
            st.rerun()
    if st.button("🔄 Atualizar dados"):
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
    nota = f"Solicitado projetado: {fmt_brl(resultado_sinistro['projecao_solicitado'])} · razão histórica: {resultado_sinistro['razao_media_historica']:.2%}"
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

col_comp1, col_comp2 = st.columns(2)
with col_comp1:
    st.markdown(f"**{label_mes(key_mes_anterior)}** (mês anterior)")
    st.metric("Valor projetado", fmt_brl(proj_mes_anterior))
    st.metric(f"Valor acumulado até dia {DIA_HOJE:02d}", fmt_brl(acum_mes_anterior))
with col_comp2:
    st.markdown(f"**{label_mes(key_mesmo_mes_ano_anterior)}** (mesmo mês, ano anterior)")
    st.metric("Valor projetado", fmt_brl(proj_mesmo_mes_ano_anterior))
    st.metric(f"Valor acumulado até dia {DIA_HOJE:02d}", fmt_brl(acum_mesmo_mes_ano_anterior))

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

st.divider()

# ============================================================
# HISTÓRICO MENSAL — Projetado × Real
# ============================================================
st.subheader("Histórico mensal · Projetado × Real")

linhas_mensal = []
for k in sorted(st.session_state.historico_mensal.keys(), reverse=True):
    dado = st.session_state.historico_mensal[k]
    eh_atual = k >= mes_key(ANO_HOJE, MES_HOJE)
    linhas_mensal.append({
        "Mês": label_mes(k),
        "_key": k,
        "Projetado (R$)": dado["projetado"],
        "Real (R$)": "mês corrente" if eh_atual else dado["real"],
        "_editavel": not eh_atual,
    })

df_mensal = pd.DataFrame(linhas_mensal)
df_mensal_exibir = df_mensal.drop(columns=["_key", "_editavel"])

if is_admin:
    # separa o mês corrente (não editável) do restante, para permitir edição só nos meses fechados
    df_editaveis = df_mensal[df_mensal["_editavel"]].copy()
    df_editaveis["Real (R$)"] = pd.to_numeric(df_editaveis["Real (R$)"], errors="coerce")

    editado_mensal = st.data_editor(
        df_editaveis.drop(columns=["_key", "_editavel"]),
        hide_index=True,
        use_container_width=True,
        disabled=["Mês", "Projetado (R$)"],
        column_config={
            "Real (R$)": st.column_config.NumberColumn(format="R$ %.2f", step=0.01),
        },
        key=f"editor_mensal_{view_year}_{view_month}",
    )

    for i, row in editado_mensal.iterrows():
        k = df_editaveis.iloc[i]["_key"]
        novo = row["Real (R$)"]
        atual = st.session_state.historico_mensal[k]["real"]
        if valor_valido(novo) and novo != atual:
            ok, erro = gravar_real_mensal(k, novo)
            if ok:
                st.rerun()
            else:
                st.error(f"Erro ao salvar {label_mes(k)}: {erro}")

    st.caption("Toque no valor Real de um mês encerrado para corrigir. O mês corrente não é editável aqui.")
else:
    st.dataframe(df_mensal_exibir, hide_index=True, use_container_width=True)
