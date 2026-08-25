"""
Módulo de Severidade — carrega os CSVs, cruza com 1004_claude.xlsx e cluster_claude.xlsx,
deriva a Região a partir da UF, e fornece todos os cálculos da aba "Severidade".
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
    dados["DATA_REF"] = dados["DATA_ATEND"]
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
    grupos = [
        "MES", "UF", "REGIAO", "ESPECIALIDADE", "CD_PLANO", "NR_PLANO", "CLUSTER",
        "CD_PROCEDIMENTO", "NOME_PROCEDIMENTO", "CD_PRESTADOR", "CIDADE_PRESTADOR",
    ]
    agregado = dados.groupby(grupos, dropna=False, observed=True).agg(
        qtd_procedimentos=("NU_GUIA", "nunique"),
        qtd_usuarios=("CD_USUARIO", "nunique"),
        soma_vl_procedimento=("VL_PROCEDIMENTO", "sum"),
        soma_vl_franquia=("VL_FRANQUIA", "sum"),
        soma_vl_pago=("VL_PAGO", "sum"),
        soma_uso=("QTD_USO", "sum"),
    ).reset_index()
    avisos = []
    if sem_regiao > 0:
        avisos.append(f"{sem_regiao:,} linhas têm UF não reconhecida.")
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
    """Extrai UF, Cidade, Cluster e Especialidade mais frequente de cada prestador."""
    return df.groupby("CD_PRESTADOR", observed=True).agg(
        UF=("UF", lambda x: x.mode().iloc[0] if not x.mode().empty else "—"),
        CIDADE=("CIDADE_PRESTADOR", lambda x: x.mode().iloc[0] if not x.mode().empty else "—"),
        CLUSTER=("CLUSTER", lambda x: x.mode().iloc[0] if not x.mode().empty else "—"),
        ESPECIALIDADE=("ESPECIALIDADE", lambda x: x.mode().iloc[0] if not x.mode().empty else "—"),
    ).reset_index()

def ranking_por(df, coluna, top_n=15):
    r = df.groupby(coluna, dropna=False, observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_solicitado=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    r["media_uso"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    return r.sort_values("valor_solicitado", ascending=False).head(top_n)

def evolucao_mensal(df):
    r = df.groupby("MES", observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_solicitado=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index().sort_values("MES")
    r["media_uso"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    return r

def ranking_severidade(df, coluna, top_n=15):
    r = df.groupby(coluna, dropna=False, observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_solicitado=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    r["custo_medio"] = (r["valor_solicitado"] / r["qtd_procedimentos"]).round(2)
    r["media_uso"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    for c in ["custo_medio", "media_uso"]:
        media, desvio = r[c].mean(), r[c].std()
        r[f"z_{c}"] = 0.0 if desvio == 0 or pd.isna(desvio) else (r[c] - media) / desvio
    r["indice_severidade"] = (r["z_custo_medio"] + r["z_media_uso"]) / 2
    return r.sort_values("indice_severidade", ascending=False).head(top_n).drop(
        columns=["z_custo_medio", "z_media_uso"]
    )

def ranking_severidade_especialidade(df, top_n=15):
    """Ranking de severidade por especialidade — ordenado do mais severo ao menos severo."""
    return ranking_severidade(df, "ESPECIALIDADE", top_n)

def calcular_media_nacional(agregado, coluna_dimensao):
    """Média de uso e custo nacional (sem filtros) por dimensão — para comparar com regiões/UFs."""
    r = agregado.groupby(coluna_dimensao, observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_solicitado=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    r["media_uso_nacional"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    r["custo_medio_nacional"] = (r["valor_solicitado"] / r["qtd_procedimentos"]).round(2)
    return r

def identificar_ofensores(df, percentil=0.95):
    info = _info_prestador(df)
    por_prestador = df.groupby("CD_PRESTADOR", observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_solicitado=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    por_prestador = por_prestador.merge(info, on="CD_PRESTADOR", how="left")
    por_prestador["custo_medio"] = (por_prestador["valor_solicitado"] / por_prestador["qtd_procedimentos"]).round(2)
    por_prestador["media_uso"] = (por_prestador["quantidade_uso"] / por_prestador["qtd_procedimentos"]).round(2)
    if len(por_prestador) == 0:
        return por_prestador
    limiar_custo = por_prestador["custo_medio"].quantile(percentil)
    limiar_volume = por_prestador["qtd_procedimentos"].quantile(percentil)
    limiar_uso = por_prestador["media_uso"].quantile(percentil)
    por_prestador["alerta_custo"] = por_prestador["custo_medio"] >= limiar_custo
    por_prestador["alerta_volume"] = por_prestador["qtd_procedimentos"] >= limiar_volume
    por_prestador["alerta_uso"] = por_prestador["media_uso"] >= limiar_uso
    por_prestador["criterios_atingidos"] = (
        por_prestador["alerta_custo"].astype(int)
        + por_prestador["alerta_volume"].astype(int)
        + por_prestador["alerta_uso"].astype(int)
    )
    # Justificativa textual
    justificativas = []
    for _, row in por_prestador.iterrows():
        motivos = []
        if row["alerta_custo"]:
            motivos.append(f"custo médio R$ {row['custo_medio']:.2f} no top {int((1-percentil)*100)}% (limiar R$ {limiar_custo:.2f})")
        if row["alerta_volume"]:
            motivos.append(f"volume {int(row['qtd_procedimentos'])} procedimentos no top {int((1-percentil)*100)}% (limiar {int(limiar_volume)})")
        if row["alerta_uso"]:
           
