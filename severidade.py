"""
Módulo de Severidade — carrega CSVs, cruza com 1004_claude.xlsx, cluster_claude.xlsx
e a relação de prestadores (código, nome, CPF/CNPJ), deriva Região a partir da UF,
e fornece todos os cálculos da aba "Severidade".

Observação: esta versão ignora valores em R$ (VL_PROCEDIMENTO / VL_FRANQUIA / VL_PAGO)
em todos os rankings, índices e alertas. Tudo é calculado a partir de duas métricas de uso:

  - uso_por_procedimento = soma da qtde de uso ÷ qtde de procedimentos
  - uso_por_vida         = soma da qtde de uso ÷ qtde de vidas (usuários distintos)
"""
import glob
import os
import unicodedata
import numpy as np
import pandas as pd
import streamlit as st
UF_PARA_REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
    "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}
# Colunas esperadas na relação de prestadores (ex.: BASE.csv), buscadas por nome
# normalizado — o arquivo pode ter outras colunas (TIPO PRESTADOR, STATUS etc.),
# só estas três são usadas.
COLUNAS_PRESTADORES = ["CODIGO", "CREDENCIADO", "CNPJ_CPF"]
# Especialidades completamente fora da análise de severidade (não representam
# atendimento clínico de fato) — comparação por texto normalizado, então
# funciona com ou sem acento/maiúsculas.
ESPECIALIDADES_EXCLUIDAS = {"RESPONSABILIDADE TECNICA"}
def normalizar_texto(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    texto = str(v).strip().upper()
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return texto
def _corrigir_mojibake(texto):
    if texto is None:
        return texto
    s = str(texto)
    if "Ã" not in s and "Â" not in s:
        return s
    try:
        return s.encode("latin1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s
COLUNAS_ESPERADAS = [
    "NU_GUIA", "DATA_SOL", "DATA_AUT", "DATA_ATEND", "CD_USUARIO", "CD_PLANO", "NR_PLANO",
    "ESPECIALIDADE", "CD_PROCEDIMENTO", "CD_TUSS", "NOME_PROCEDIMENTO",
    "VL_PROCEDIMENTO", "VL_FRANQUIA", "VL_PAGO", "STATUS_PROCED",
    "CD_PRESTADOR", "CIDADE_PRESTADOR", "UF", "EXECUCAO",
]
def _parse_valor_monetario(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
def _casar_colunas(colunas_reais, colunas_esperadas):
    mapa_normalizado = {}
    for c in colunas_reais:
        chave = normalizar_texto(_corrigir_mojibake(str(c).strip()))
        mapa_normalizado[chave] = c
    resultado = {}
    for esperado in colunas_esperadas:
        chave = normalizar_texto(esperado)
        if chave in mapa_normalizado:
            resultado[esperado] = mapa_normalizado[chave]
    return resultado
def _ler_csv_parte(caminho, colunas_esperadas):
    df = None
    for enc in ["utf-8", "latin1"]:
        try:
            df = pd.read_csv(caminho, sep=";", encoding=enc, dtype=str, low_memory=False)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if df is None:
        raise ValueError(f"Não consegui ler {caminho}")
    mapa_colunas = _casar_colunas(df.columns, colunas_esperadas)
    faltando = [c for c in colunas_esperadas if c not in mapa_colunas]
    if faltando:
        raise ValueError(f"Colunas faltando em {os.path.basename(caminho)}: {faltando}")
    df = df[[mapa_colunas[c] for c in colunas_esperadas]].copy()
    df.columns = colunas_esperadas
    for c in ["DATA_SOL", "DATA_AUT", "DATA_ATEND"]:
        df[c] = pd.to_datetime(df[c], dayfirst=True, errors="coerce")
    for c in ["CD_PLANO", "CD_PROCEDIMENTO", "CD_TUSS", "CD_PRESTADOR"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["NU_GUIA"] = df["NU_GUIA"].astype(str).str.strip()
    df["CD_USUARIO"] = df["CD_USUARIO"].astype(str).str.strip()
    for c in ["VL_PROCEDIMENTO", "VL_FRANQUIA", "VL_PAGO"]:
        df[c] = df[c].apply(_parse_valor_monetario)
    for c in ["ESPECIALIDADE", "NR_PLANO", "NOME_PROCEDIMENTO", "STATUS_PROCED", "CIDADE_PRESTADOR", "UF", "EXECUCAO"]:
        df[c] = df[c].apply(_corrigir_mojibake)
    df["UF"] = df["UF"].astype(str).str.strip().str.upper()
    df = df.drop_duplicates()
    return df
def _chave_mes(caminho):
    nome = os.path.splitext(os.path.basename(caminho))[0]
    if "_parte_" in nome:
        nome = nome.split("_parte_")[0]
    return nome
def _numero_parte(caminho):
    nome = os.path.basename(caminho)
    if "_parte_" in nome:
        try:
            return int(nome.split("_parte_")[1].split(".")[0])
        except ValueError:
            return 0
    return 0
def _localizar_arquivo(pasta, prefixo):
    candidatos = glob.glob(os.path.join(pasta, f"{prefixo}*.xlsx"))
    if not candidatos:
        candidatos = glob.glob(os.path.join(pasta, f"{prefixo.replace('_', ' ')}*.xlsx"))
    if not candidatos:
        raise FileNotFoundError(f"Não encontrei '{prefixo}' (.xlsx) na pasta {pasta!r}.")
    return candidatos[0]
def _ler_amostra_csv(caminho, nrows=3):
    for enc in ["utf-8", "latin1"]:
        try:
            return pd.read_csv(caminho, sep=";", encoding=enc, nrows=nrows, dtype=str)
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            return None
    return None
def _localizar_csv_prestadores(pasta):
    """
    Procura, entre todos os .csv da pasta, um arquivo com as colunas de uma
    relação de prestadores (código, nome/credenciado, CPF/CNPJ) — identificado
    pelo cabeçalho, não pelo nome do arquivo (ex.: BASE.csv).
    """
    exigidas = {normalizar_texto(c) for c in COLUNAS_PRESTADORES}
    candidatos = sorted(glob.glob(os.path.join(pasta, "*.csv")))
    for c in candidatos:
        amostra = _ler_amostra_csv(c)
        if amostra is None:
            continue
        colunas_norm = {normalizar_texto(_corrigir_mojibake(str(col).strip())) for col in amostra.columns}
        if exigidas.issubset(colunas_norm):
            return c
    return None
def _ler_csv_prestadores(caminho):
    df = None
    for enc in ["utf-8", "latin1"]:
        try:
            df = pd.read_csv(caminho, sep=";", encoding=enc, dtype=str, low_memory=False)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if df is None:
        raise ValueError(f"Não consegui ler {caminho}")
    mapa = _casar_colunas(df.columns, COLUNAS_PRESTADORES)
    faltando = [c for c in COLUNAS_PRESTADORES if c not in mapa]
    if faltando:
        raise ValueError(f"Colunas faltando em {os.path.basename(caminho)}: {faltando}")
    df = df[[mapa["CODIGO"], mapa["CREDENCIADO"], mapa["CNPJ_CPF"]]].copy()
    df.columns = ["CD_PRESTADOR", "NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR"]
    df["CD_PRESTADOR"] = pd.to_numeric(df["CD_PRESTADOR"], errors="coerce")
    df["NOME_PRESTADOR"] = df["NOME_PRESTADOR"].apply(_corrigir_mojibake)
    df["CNPJ_CPF_PRESTADOR"] = df["CNPJ_CPF_PRESTADOR"].astype(str).str.strip()
    df = df.dropna(subset=["CD_PRESTADOR"]).drop_duplicates(subset="CD_PRESTADOR", keep="first")
    return df
@st.cache_data(show_spinner="Carregando dados de severidade...")
def carregar_base_severidade(pasta="."):
    candidatos = sorted(
        glob.glob(os.path.join(pasta, "*4016R.csv"))
        + glob.glob(os.path.join(pasta, "*4016R_parte_*.csv"))
    )
    if not candidatos:
        return None, "Nenhum arquivo .csv encontrado."
    grupos_arquivo = {}
    for c in candidatos:
        grupos_arquivo.setdefault(_chave_mes(c), []).append(c)
    for chave in grupos_arquivo:
        grupos_arquivo[chave].sort(key=_numero_parte)
    partes = []
    for chave_grupo, arquivos_do_grupo in grupos_arquivo.items():
        for arq in arquivos_do_grupo:
            try:
                df = _ler_csv_parte(arq, COLUNAS_ESPERADAS)
            except Exception as e:
                return None, f"Erro ao ler {os.path.basename(arq)}: {e}"
            df["ARQUIVO_ORIGEM"] = chave_grupo
            partes.append(df)
    dados = pd.concat(partes, ignore_index=True)
    dados["DATA_REF"] = dados["DATA_SOL"]
    sem_atend = dados["DATA_REF"].isna()
    dados.loc[sem_atend, "DATA_REF"] = dados.loc[sem_atend, "DATA_SOL"]
    dados["MES"] = dados["DATA_REF"].dt.strftime("%Y-%m")
    tabela_1004 = pd.read_excel(_localizar_arquivo(pasta, "1004"), sheet_name=0)
    mapa_1004 = _casar_colunas(tabela_1004.columns, ["CODIGO", "USO"])
    tabela_1004 = tabela_1004[[mapa_1004["CODIGO"], mapa_1004["USO"]]].copy()
    tabela_1004.columns = ["CD_PROCEDIMENTO", "USO_PROCEDIMENTO"]
    tabela_1004["CD_PROCEDIMENTO"] = pd.to_numeric(tabela_1004["CD_PROCEDIMENTO"], errors="coerce")
    dados = dados.merge(tabela_1004, on="CD_PROCEDIMENTO", how="left")
    dados["USO_PROCEDIMENTO"] = dados["USO_PROCEDIMENTO"].fillna(0)
    dados["QTD_USO"] = dados["USO_PROCEDIMENTO"]
    cluster_bi = pd.read_excel(_localizar_arquivo(pasta, "cluster"), sheet_name=0)
    mapa_cluster = _casar_colunas(cluster_bi.columns, ["UF_MUN", "CLUSTER"])
    cluster_bi = cluster_bi[[mapa_cluster["UF_MUN"], mapa_cluster["CLUSTER"]]].copy()
    cluster_bi.columns = ["UF_MUN", "CLUSTER"]
    cluster_bi["CHAVE_CIDADE_UF"] = cluster_bi["UF_MUN"].apply(normalizar_texto)
    cluster_bi = cluster_bi[["CHAVE_CIDADE_UF", "CLUSTER"]].drop_duplicates("CHAVE_CIDADE_UF")
    dados["CHAVE_CIDADE_UF"] = (
        dados["CIDADE_PRESTADOR"].apply(normalizar_texto) + "-" + dados["UF"].apply(normalizar_texto)
    )
    dados = dados.merge(cluster_bi, on="CHAVE_CIDADE_UF", how="left")
    dados["REGIAO"] = dados["UF"].map(UF_PARA_REGIAO)
    sem_regiao = dados["REGIAO"].isna().sum()
    # Relação de prestadores (código, nome/credenciado, CPF/CNPJ) — opcional: se o
    # arquivo ainda não estiver na pasta, seguimos só com o código do prestador.
    caminho_prestadores = _localizar_csv_prestadores(pasta)
    if caminho_prestadores:
        try:
            prestadores = _ler_csv_prestadores(caminho_prestadores)
            dados = dados.merge(prestadores, on="CD_PRESTADOR", how="left")
        except Exception:
            dados["NOME_PRESTADOR"] = None
            dados["CNPJ_CPF_PRESTADOR"] = None
    else:
        dados["NOME_PRESTADOR"] = None
        dados["CNPJ_CPF_PRESTADOR"] = None
    grupos = [
        "MES", "UF", "REGIAO", "ESPECIALIDADE", "CD_PLANO", "NR_PLANO", "CLUSTER",
        "CD_PROCEDIMENTO", "NOME_PROCEDIMENTO", "CD_PRESTADOR", "NOME_PRESTADOR",
        "CNPJ_CPF_PRESTADOR", "CIDADE_PRESTADOR",
    ]
    # Nota: valores em R$ (VL_PROCEDIMENTO/VL_FRANQUIA/VL_PAGO) não entram mais no
    # agregado — a análise de severidade passa a ser 100% baseada em uso e volume.
    agregado = dados.groupby(grupos, dropna=False, observed=True).agg(
        qtd_procedimentos=("NU_GUIA", "nunique"),
        qtd_usuarios=("CD_USUARIO", "nunique"),
        soma_uso=("QTD_USO", "sum"),
    ).reset_index()
    # Descarta linhas cuja dimensão principal veio vazia/não identificada (nan) —
    # essas linhas não entram em nenhum ranking, gráfico ou resumo, em vez de
    # aparecer como uma categoria "nan".
    linhas_antes = len(agregado)
    colunas_chave = ["MES", "UF", "REGIAO", "ESPECIALIDADE", "CD_PRESTADOR", "NOME_PROCEDIMENTO", "CIDADE_PRESTADOR"]
    agregado = agregado.dropna(subset=colunas_chave).reset_index(drop=True)
    linhas_desconsideradas = linhas_antes - len(agregado)
    # Remove tudo que for "Responsabilidade Técnica" — tanto quando é a
    # ESPECIALIDADE da linha quanto quando é o NOME_PROCEDIMENTO (existe um
    # procedimento com esse nome, que não é um atendimento clínico de fato) —
    # comparação por texto normalizado, então funciona com ou sem acento/maiúsculas.
    linhas_antes_excl = len(agregado)
    esp_normalizada = agregado["ESPECIALIDADE"].apply(normalizar_texto)
    proc_normalizado = agregado["NOME_PROCEDIMENTO"].apply(normalizar_texto)
    agregado = agregado[
        ~esp_normalizada.isin(ESPECIALIDADES_EXCLUIDAS)
        & ~proc_normalizado.isin(ESPECIALIDADES_EXCLUIDAS)
    ].reset_index(drop=True)
    linhas_especialidade_excluida = linhas_antes_excl - len(agregado)
    avisos = []
    if linhas_desconsideradas > 0:
        avisos.append(
            f"{linhas_desconsideradas:,} linhas desconsideradas por terem mês, UF, região, "
            "especialidade, prestador, procedimento ou cidade não identificados (nan)."
        )
    if linhas_especialidade_excluida > 0:
        avisos.append(
            f"{linhas_especialidade_excluida:,} linhas de 'Responsabilidade Técnica' "
            "(especialidade ou procedimento) desconsideradas."
        )
    if caminho_prestadores is None:
        avisos.append(
            "Relação de prestadores (nome/CPF-CNPJ) não encontrada na pasta — "
            "mostrando apenas o código do prestador."
        )
    aviso = " | ".join(avisos) if avisos else None
    return agregado, aviso
def aplicar_filtros(agregado, meses=None, ufs=None, regioes=None, especialidades=None, planos=None, clusters=None):
    df = agregado
    if meses: df = df[df["MES"].isin(meses)]
    if ufs: df = df[df["UF"].isin(ufs)]
    if regioes: df = df[df["REGIAO"].isin(regioes)]
    if especialidades: df = df[df["ESPECIALIDADE"].isin(especialidades)]
    if planos: df = df[df["NR_PLANO"].isin(planos)]
    if clusters: df = df[df["CLUSTER"].isin(clusters)]
    return df
def _info_prestador(df):
    """Extrai Nome, CPF/CNPJ, UF, Cidade, Cluster e Especialidade mais frequente de cada prestador."""
    agregacoes = {
        "UF": ("UF", lambda x: x.mode().iloc[0] if not x.mode().empty else "—"),
        "CIDADE": ("CIDADE_PRESTADOR", lambda x: x.mode().iloc[0] if not x.mode().empty else "—"),
        "CLUSTER": ("CLUSTER", lambda x: x.mode().iloc[0] if not x.mode().empty else "—"),
        "ESPECIALIDADE": ("ESPECIALIDADE", lambda x: x.mode().iloc[0] if not x.mode().empty else "—"),
    }
    if "NOME_PRESTADOR" in df.columns:
        agregacoes["NOME_PRESTADOR"] = ("NOME_PRESTADOR", lambda x: x.mode().iloc[0] if not x.mode().empty else "—")
    if "CNPJ_CPF_PRESTADOR" in df.columns:
        agregacoes["CNPJ_CPF_PRESTADOR"] = ("CNPJ_CPF_PRESTADOR", lambda x: x.mode().iloc[0] if not x.mode().empty else "—")
    return df.groupby("CD_PRESTADOR", observed=True).agg(**agregacoes).reset_index()
def _indice_severidade(r):
    """
    Índice de Severidade Relativa (ISR) — média de duas relatividades, cada
    uma cruzando dois dos três parâmetros de uso e comparada à média da base:

        Frequência  = qtd_procedimentos ÷ qtd_usuarios     (procedimentos por vida)
        Intensidade = quantidade_uso ÷ qtd_procedimentos    (uso por procedimento)

        R_frequência  = Frequência do grupo  ÷ Frequência média da base
        R_intensidade = Intensidade do grupo ÷ Intensidade média da base
        ISR = (R_frequência + R_intensidade) ÷ 2

    ISR = 1,00 é a média da base; acima de 1,00 é mais severo (uso mais
    concentrado em poucas vidas/procedimentos ou mais intenso por
    procedimento); abaixo de 1,00 é menos severo. Ao contrário de uma taxa
    "por 100.000" fixa, esta versão se autoajusta à escala real dos dados —
    não explode para grupos de baixo volume, porque cada relatividade só
    divide por uma grandeza de cada vez (não pelo produto das duas). Não
    considera valores em R$.

    Recebe um DataFrame com as colunas quantidade_uso, qtd_usuarios e
    qtd_procedimentos e devolve uma Series (indice_severidade) alinhada ao
    índice de r.
    """
    total_proc = r["qtd_procedimentos"].sum()
    total_usuarios = r["qtd_usuarios"].sum()
    total_uso = r["quantidade_uso"].sum()
    freq_media = (total_proc / total_usuarios) if total_usuarios else np.nan
    intens_media = (total_uso / total_proc) if total_proc else np.nan
    freq_grupo = np.where(r["qtd_usuarios"] > 0, r["qtd_procedimentos"] / r["qtd_usuarios"], np.nan)
    intens_grupo = np.where(r["qtd_procedimentos"] > 0, r["quantidade_uso"] / r["qtd_procedimentos"], np.nan)
    if not freq_media or pd.isna(freq_media):
        r_freq = np.full(len(r), np.nan)
    else:
        r_freq = freq_grupo / freq_media
    if not intens_media or pd.isna(intens_media):
        r_intens = np.full(len(r), np.nan)
    else:
        r_intens = intens_grupo / intens_media
    indice = (r_freq + r_intens) / 2
    return pd.Series(indice, index=r.index).round(2)
def ranking_por(df, coluna, top_n=15):
    r = df.groupby(coluna, dropna=False, observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        qtd_usuarios=("qtd_usuarios", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    r = r[r[coluna].notna()]
    r["uso_por_procedimento"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    r["uso_por_vida"] = (r["quantidade_uso"] / r["qtd_usuarios"]).round(2)
    return r.sort_values("quantidade_uso", ascending=False).head(top_n)
def evolucao_mensal(df):
    r = df.groupby("MES", observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        qtd_usuarios=("qtd_usuarios", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index().sort_values("MES")
    r["uso_por_procedimento"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    r["uso_por_vida"] = (r["quantidade_uso"] / r["qtd_usuarios"]).round(2)
    r["indice_severidade"] = _indice_severidade(r)
    return r
def ranking_severidade(df, coluna, top_n=15):
    grupo_cols = [coluna]
    if coluna == "CD_PRESTADOR":
        for extra in ["NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR"]:
            if extra in df.columns:
                grupo_cols.append(extra)
    r = df.groupby(grupo_cols, dropna=False, observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        qtd_usuarios=("qtd_usuarios", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    r = r[r[coluna].notna()]
    r["uso_por_procedimento"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    r["uso_por_vida"] = (r["quantidade_uso"] / r["qtd_usuarios"]).round(2)
    r["indice_severidade"] = _indice_severidade(r)
    return r.sort_values("indice_severidade", ascending=False).head(top_n)
def calcular_media_nacional(agregado, coluna_dimensao):
    """Média de uso nacional (sem filtros) por dimensão."""
    r = agregado.groupby(coluna_dimensao, observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        qtd_usuarios=("qtd_usuarios", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    r["uso_por_procedimento_nacional"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    r["uso_por_vida_nacional"] = (r["quantidade_uso"] / r["qtd_usuarios"]).round(2)
    return r
def montar_watchlist(df, top_n=20):
    """
    Watchlist com Nome, CPF/CNPJ, UF, Cidade e Cluster de cada prestador.
    Pontuação 0-100 combinando uso por procedimento, uso por vida e volume.
    """
    info = _info_prestador(df)
    por_prestador = df.groupby("CD_PRESTADOR", observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        qtd_usuarios=("qtd_usuarios", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    if por_prestador.empty:
        return pd.DataFrame()
    por_prestador = por_prestador.merge(info, on="CD_PRESTADOR", how="left")
    por_prestador["uso_por_procedimento"] = (por_prestador["quantidade_uso"] / por_prestador["qtd_procedimentos"]).round(2)
    por_prestador["uso_por_vida"] = (por_prestador["quantidade_uso"] / por_prestador["qtd_usuarios"]).round(2)
    # Pontuação composta (0-100) — percentis de uso por procedimento, uso por vida e volume
    for c in ["uso_por_procedimento", "uso_por_vida", "qtd_procedimentos"]:
        por_prestador[f"pct_{c}"] = por_prestador[c].rank(pct=True).fillna(0)
    por_prestador["pontuacao"] = (
        (por_prestador["pct_uso_por_procedimento"] * 0.35
         + por_prestador["pct_uso_por_vida"] * 0.35
         + por_prestador["pct_qtd_procedimentos"] * 0.30) * 100
    ).round(0)
    por_prestador["indice_severidade"] = _indice_severidade(por_prestador)
    # Tendência percentual (variação do volume do mês mais recente vs anterior, se houver)
    if "MES" in df.columns and df["MES"].nunique() > 1:
        meses_ord = sorted(df["MES"].unique())
        ultimo = meses_ord[-1]
        penult = meses_ord[-2]
        df_ult = df[df["MES"] == ultimo]
        df_pen = df[df["MES"] == penult]
        agg_ult = df_ult.groupby("CD_PRESTADOR", observed=True)["qtd_procedimentos"].sum()
        agg_pen = df_pen.groupby("CD_PRESTADOR", observed=True)["qtd_procedimentos"].sum()
        tend = ((agg_ult - agg_pen) / agg_pen.replace(0, np.nan) * 100).round(1)
        por_prestador["tendencia_pct"] = por_prestador["CD_PRESTADOR"].map(tend).fillna(0)
    else:
        por_prestador["tendencia_pct"] = 0.0
    resultado = por_prestador.sort_values("pontuacao", ascending=False).head(top_n)
    cols = ["CD_PRESTADOR", "NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER", "ESPECIALIDADE",
            "qtd_procedimentos", "qtd_usuarios", "quantidade_uso", "uso_por_procedimento", "uso_por_vida",
            "indice_severidade", "tendencia_pct", "pontuacao"]
    cols = [c for c in cols if c in resultado.columns]
    return resultado[cols].reset_index(drop=True)
def identificar_ofensores(df, percentil=0.95):
    """
    Identifica ofensores com justificativa textual, baseado só em uso e volume.
    Um prestador é ofensor quando atende ≥ 2 de 3 critérios no top 5%:
    volume de procedimentos, uso por procedimento, uso por vida.
    """
    info = _info_prestador(df)
    por_prestador = df.groupby("CD_PRESTADOR", observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        qtd_usuarios=("qtd_usuarios", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    por_prestador = por_prestador.merge(info, on="CD_PRESTADOR", how="left")
    por_prestador["uso_por_procedimento"] = (por_prestador["quantidade_uso"] / por_prestador["qtd_procedimentos"]).round(2)
    por_prestador["uso_por_vida"] = (por_prestador["quantidade_uso"] / por_prestador["qtd_usuarios"]).round(2)
    if len(por_prestador) == 0:
        return por_prestador
    limiar_volume = por_prestador["qtd_procedimentos"].quantile(percentil)
    limiar_uso_procedimento = por_prestador["uso_por_procedimento"].quantile(percentil)
    limiar_uso_vida = por_prestador["uso_por_vida"].quantile(percentil)
    por_prestador["alerta_volume"] = por_prestador["qtd_procedimentos"] >= limiar_volume
    por_prestador["alerta_uso_procedimento"] = por_prestador["uso_por_procedimento"] >= limiar_uso_procedimento
    por_prestador["alerta_uso_vida"] = por_prestador["uso_por_vida"] >= limiar_uso_vida
    por_prestador["criterios_atingidos"] = (
        por_prestador["alerta_volume"].astype(int)
        + por_prestador["alerta_uso_procedimento"].astype(int)
        + por_prestador["alerta_uso_vida"].astype(int)
    )
    pct_str = f"top {int((1 - percentil) * 100)}%"
    justificativas = []
    for _, row in por_prestador.iterrows():
        motivos = []
        if row["alerta_volume"]:
            motivos.append(f"volume {int(row['qtd_procedimentos'])} procedimentos no {pct_str} (limiar {int(limiar_volume)})")
        if row["alerta_uso_procedimento"]:
            motivos.append(f"uso por procedimento {row['uso_por_procedimento']:.2f} no {pct_str} (limiar {limiar_uso_procedimento:.2f})")
        if row["alerta_uso_vida"]:
            motivos.append(f"uso por vida {row['uso_por_vida']:.2f} no {pct_str} (limiar {limiar_uso_vida:.2f})")
        just = "; ".join(motivos) if motivos else "sem alertas"
        justificativas.append(just)
    por_prestador["justificativa"] = justificativas
    por_prestador["relevante"] = por_prestador["criterios_atingidos"] >= 2
    por_prestador["indice_severidade"] = _indice_severidade(por_prestador)
    resultado = por_prestador.sort_values(
        ["indice_severidade", "criterios_atingidos"], ascending=[False, False], na_position="last"
    )
    cols = ["CD_PRESTADOR", "NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER", "ESPECIALIDADE",
            "qtd_procedimentos", "qtd_usuarios", "quantidade_uso", "uso_por_procedimento", "uso_por_vida",
            "indice_severidade", "alerta_volume", "alerta_uso_procedimento", "alerta_uso_vida",
            "criterios_atingidos", "relevante", "justificativa"]
    cols = [c for c in cols if c in resultado.columns]
    return resultado[cols].reset_index(drop=True)
def calcular_desvios(df):
    """Desvios de cada prestador vs média da própria especialidade (uso por procedimento e por vida)."""
    info = _info_prestador(df)
    por_prestador = df.groupby(["CD_PRESTADOR", "ESPECIALIDADE"], observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        qtd_usuarios=("qtd_usuarios", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    if por_prestador.empty:
        return por_prestador
    por_prestador["uso_por_procedimento"] = (por_prestador["quantidade_uso"] / por_prestador["qtd_procedimentos"]).round(2)
    por_prestador["uso_por_vida"] = (por_prestador["quantidade_uso"] / por_prestador["qtd_usuarios"]).round(2)
    media_esp = por_prestador.groupby("ESPECIALIDADE")[["uso_por_procedimento", "uso_por_vida"]].mean()
    media_esp.columns = ["uso_por_procedimento_esp", "uso_por_vida_esp"]
    por_prestador = por_prestador.merge(media_esp, on="ESPECIALIDADE", how="left")
    por_prestador["desvio_uso_procedimento_pct"] = (
        (por_prestador["uso_por_procedimento"] - por_prestador["uso_por_procedimento_esp"]) / por_prestador["uso_por_procedimento_esp"] * 100
    ).round(1)
    por_prestador["desvio_uso_vida_pct"] = (
        (por_prestador["uso_por_vida"] - por_prestador["uso_por_vida_esp"]) / por_prestador["uso_por_vida_esp"] * 100
    ).round(1)
    colunas_info = [c for c in ["CD_PRESTADOR", "NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER"] if c in info.columns]
    por_prestador = por_prestador.merge(info[colunas_info], on="CD_PRESTADOR", how="left")
    resultado = por_prestador.sort_values("desvio_uso_procedimento_pct", ascending=False)
    cols = ["CD_PRESTADOR", "NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER", "ESPECIALIDADE",
            "qtd_procedimentos", "uso_por_procedimento", "uso_por_procedimento_esp", "desvio_uso_procedimento_pct",
            "uso_por_vida", "uso_por_vida_esp", "desvio_uso_vida_pct"]
    cols = [c for c in cols if c in resultado.columns]
    return resultado[cols].reset_index(drop=True)
def comparacao_mensal(df, coluna, volume_minimo=30):
    """Compara o último mês vs o anterior por coluna (volume e uso), respeitando volume mínimo."""
    if "MES" not in df.columns or df["MES"].nunique() < 2:
        return pd.DataFrame(), "Dados insuficientes para comparação (necessário ≥ 2 meses)."
    meses_ord = sorted(df["MES"].unique())
    ultimo = meses_ord[-1]
    penult = meses_ord[-2]
    df_ult = df[df["MES"] == ultimo]
    df_pen = df[df["MES"] == penult]
    agg_ult = df_ult.groupby(coluna, observed=True).agg(
        qtd_atual=("qtd_procedimentos", "sum"),
        usuarios_atual=("qtd_usuarios", "sum"),
        uso_atual=("soma_uso", "sum"),
    )
    agg_pen = df_pen.groupby(coluna, observed=True).agg(
        qtd_anterior=("qtd_procedimentos", "sum"),
        usuarios_anterior=("qtd_usuarios", "sum"),
        uso_anterior=("soma_uso", "sum"),
    )
    comp = agg_ult.join(agg_pen, how="outer").fillna(0)
    comp["delta_qtd"] = comp["qtd_atual"] - comp["qtd_anterior"]
    comp["variacao_pct"] = np.where(
        comp["qtd_anterior"] > 0,
        (comp["qtd_atual"] - comp["qtd_anterior"]) / comp["qtd_anterior"] * 100,
        np.nan
    )
    comp["relevante"] = comp["qtd_atual"] >= volume_minimo
    comp = comp.sort_values("variacao_pct", ascending=False, na_position="last").reset_index()
    msg = (f"Comparando {ultimo} vs {penult} por {coluna}. "
           f"Relevante = volume atual ≥ {volume_minimo} procedimentos.")
    return comp, msg
def _variacao_pct_uso(df, coluna, volume_minimo, top_n):
    """
    Variação % de uso (mês atual vs anterior) agrupada por `coluna`. Só entram
    grupos com volume (qtd_procedimentos) ≥ volume_minimo em AMBOS os meses e
    uso > 0 no mês anterior — evita que um grupo minúsculo mostre uma
    variação % gigante e sem significado.
    """
    meses_ord = sorted(df["MES"].dropna().unique())
    ultimo, penult = meses_ord[-1], meses_ord[-2]
    atual = df[df["MES"] == ultimo].groupby(coluna, dropna=False, observed=True).agg(
        qtd_procedimentos_atual=("qtd_procedimentos", "sum"),
        soma_uso_atual=("soma_uso", "sum"),
    ).reset_index()
    anterior = df[df["MES"] == penult].groupby(coluna, dropna=False, observed=True).agg(
        qtd_procedimentos_anterior=("qtd_procedimentos", "sum"),
        soma_uso_anterior=("soma_uso", "sum"),
    ).reset_index()
    comp = atual.merge(anterior, on=coluna, how="inner")
    comp = comp[comp[coluna].notna()]
    comp = comp[
        (comp["qtd_procedimentos_atual"] >= volume_minimo)
        & (comp["qtd_procedimentos_anterior"] >= volume_minimo)
        & (comp["soma_uso_anterior"] > 0)
    ]
    comp["variacao_pct"] = (
        (comp["soma_uso_atual"] - comp["soma_uso_anterior"]) / comp["soma_uso_anterior"] * 100
    ).round(1)
    return comp.sort_values("variacao_pct", ascending=False).head(top_n).reset_index(drop=True)
def resumo_comparativo(df, volume_minimo=30, top_especialidades=5, top_ufs=10, top_prestadores=20, top_detalhe=5):
    """
    Resumo do mês vs o anterior, baseado na variação % de USO (não em números
    absolutos): 5 especialidades que mais subiram, os procedimentos que
    causaram essa subida; 10 UFs que mais subiram, as cidades (com cluster)
    que causaram essa subida; 20 prestadores que mais subiram, com
    cidade/UF/cluster/especialidade e os procedimentos responsáveis.
    """
    if "MES" not in df.columns or df["MES"].dropna().nunique() < 2:
        return None, "Dados insuficientes para comparação (necessário ≥ 2 meses)."
    meses_ord = sorted(df["MES"].dropna().unique())
    ultimo, penult = meses_ord[-1], meses_ord[-2]

    especialidades = _variacao_pct_uso(df, "ESPECIALIDADE", volume_minimo, top_especialidades)
    detalhes_especialidade = {
        esp: _variacao_pct_uso(df[df["ESPECIALIDADE"] == esp], "NOME_PROCEDIMENTO", volume_minimo, top_detalhe)
        for esp in especialidades["ESPECIALIDADE"]
    }

    ufs = _variacao_pct_uso(df, "UF", volume_minimo, top_ufs)
    detalhes_uf = {}
    for uf in ufs["UF"]:
        sub = df[df["UF"] == uf]
        cidades = _variacao_pct_uso(sub, "CIDADE_PRESTADOR", volume_minimo, top_detalhe)
        if not cidades.empty and "CLUSTER" in sub.columns:
            mapa_cluster = sub.groupby("CIDADE_PRESTADOR", observed=True)["CLUSTER"].agg(
                lambda x: x.mode().iloc[0] if not x.mode().empty else "—"
            )
            cidades["CLUSTER"] = cidades["CIDADE_PRESTADOR"].map(mapa_cluster)
        detalhes_uf[uf] = cidades

    prestadores = _variacao_pct_uso(df, "CD_PRESTADOR", volume_minimo, top_prestadores)
    info = _info_prestador(df)
    colunas_info = [c for c in ["CD_PRESTADOR", "NOME_PRESTADOR", "CNPJ_CPF_PRESTADOR", "UF", "CIDADE", "CLUSTER", "ESPECIALIDADE"] if c in info.columns]
    prestadores = prestadores.merge(info[colunas_info], on="CD_PRESTADOR", how="left")
    detalhes_prestador = {
        cd: _variacao_pct_uso(df[df["CD_PRESTADOR"] == cd], "NOME_PROCEDIMENTO", volume_minimo, top_detalhe)
        for cd in prestadores["CD_PRESTADOR"]
    }

    resultado = {
        "ultimo": ultimo, "penultimo": penult,
        "especialidades": especialidades, "detalhes_especialidade": detalhes_especialidade,
        "ufs": ufs, "detalhes_uf": detalhes_uf,
        "prestadores": prestadores, "detalhes_prestador": detalhes_prestador,
    }
    msg = (f"Comparando {ultimo} vs {penult}, por variação % de uso. "
           f"Só entram grupos com volume ≥ {volume_minimo} procedimentos em ambos os meses.")
    return resultado, msg
