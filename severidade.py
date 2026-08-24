"""
Módulo de Severidade — carrega os parquets (guias), cruza com 1004 (USO) e
Cluster BI (cidade -> cluster/UF/região), e fornece todos os cálculos usados
na aba "Severidade" do painel.

ARQUIVOS ESPERADOS (na mesma pasta do app.py, no repositório):
  - *_2026_4016R.parquet  (um por mês — as 19 colunas reais, sem NOME_USUARIO,
    DS_PRESTADOR nem CPF_CNPJ_PRESTADOR; prestador identificado só por CD_PRESTADOR)
  - 1004.xlsx             (CODIGO, USO, e outras colunas de apoio)
  - cluster_BI.xlsx        (aba "Cluster": CIDADE, CLUSTER, UF_MUN, UF, CIDADE 5201, REGIÃO)
"""

import glob
import os
import unicodedata
import numpy as np
import pandas as pd
import streamlit as st


# ============================================================
# NORMALIZAÇÃO DE TEXTO (para cruzar CIDADE_PRESTADOR com o Cluster BI,
# que não tem acentos)
# ============================================================
def normalizar_texto(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    texto = str(v).strip().upper()
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return texto


# ============================================================
# CARREGAMENTO E CRUZAMENTO DOS DADOS (cacheado — só recalcula quando pedido)
# ============================================================
@st.cache_data(show_spinner="Carregando dados de severidade...")
def carregar_base_severidade(pasta="."):
    # ---------- 1) parquets (aceita arquivos inteiros OU divididos em partes) ----------
    # Um mês pode vir como "01_2026_4016R.parquet" (arquivo único) ou dividido em
    # "01_2026_4016R_parte_1.parquet", "01_2026_4016R_parte_2.parquet", etc.
    # (útil para caber no limite de 25MB do upload pelo navegador do GitHub).
    candidatos = sorted(
        glob.glob(os.path.join(pasta, "*4016R.parquet"))
        + glob.glob(os.path.join(pasta, "*4016R_parte_*.parquet"))
    )
    if not candidatos:
        return None, "Nenhum arquivo .parquet encontrado (padrão *4016R.parquet ou *4016R_parte_N.parquet)."

    def chave_mes(caminho):
        """Agrupa partes do mesmo mês: '01_2026_4016R_parte_2.parquet' -> '01_2026_4016R'."""
        nome = os.path.basename(caminho)
        nome_sem_ext = nome[:-len(".parquet")]
        if "_parte_" in nome_sem_ext:
            nome_sem_ext = nome_sem_ext.split("_parte_")[0]
        return nome_sem_ext

    def numero_parte(caminho):
        nome = os.path.basename(caminho)
        if "_parte_" in nome:
            try:
                return int(nome.split("_parte_")[1].split(".")[0])
            except ValueError:
                return 0
        return 0

    grupos_arquivo = {}
    for c in candidatos:
        grupos_arquivo.setdefault(chave_mes(c), []).append(c)
    for chave in grupos_arquivo:
        grupos_arquivo[chave].sort(key=numero_parte)

    colunas_uteis = [
        "NU_GUIA", "DATA_SOL", "DATA_AUT", "DATA_ATEND", "CD_USUARIO", "CD_PLANO", "NR_PLANO",
        "ESPECIALIDADE", "CD_PROCEDIMENTO", "CD_TUSS", "NOME_PROCEDIMENTO",
        "VL_PROCEDIMENTO", "VL_FRANQUIA", "VL_PAGO", "STATUS_PROCED",
        "CD_PRESTADOR", "CIDADE_PRESTADOR", "UF", "EXECUÇÃO",
    ]

    partes = []
    for chave_grupo, arquivos_do_grupo in grupos_arquivo.items():
        for arq in arquivos_do_grupo:
            try:
                df = pd.read_parquet(arq, engine="pyarrow", columns=colunas_uteis)
            except Exception as e:
                return None, f"Erro ao ler {os.path.basename(arq)}: {e}"
            df["ARQUIVO_ORIGEM"] = chave_grupo  # todas as partes do mesmo mês compartilham a mesma origem
            partes.append(df)
    dados = pd.concat(partes, ignore_index=True)

    # ---------- 2) mês de referência (usa DATA_ATEND; se vazio, cai para DATA_SOL) ----------
    dados["DATA_REF"] = pd.to_datetime(dados["DATA_ATEND"], errors="coerce")
    sem_atend = dados["DATA_REF"].isna()
    dados.loc[sem_atend, "DATA_REF"] = pd.to_datetime(dados.loc[sem_atend, "DATA_SOL"], errors="coerce")
    dados["MES"] = dados["DATA_REF"].dt.strftime("%Y-%m")

    # ---------- 3) cruzamento com 1004 (USO por procedimento) ----------
    tabela_1004 = pd.read_excel(os.path.join(pasta, "1004.xlsx"), sheet_name=0)
    tabela_1004 = tabela_1004[["CODIGO", "USO"]].rename(columns={"CODIGO": "CD_PROCEDIMENTO", "USO": "USO_PROCEDIMENTO"})
    dados = dados.merge(tabela_1004, on="CD_PROCEDIMENTO", how="left")
    dados["USO_PROCEDIMENTO"] = dados["USO_PROCEDIMENTO"].fillna(0)
    dados["QTD_USO"] = dados["USO_PROCEDIMENTO"]  # cada linha = 1 procedimento; a soma por grupo dá a "quantidade de uso"

    # ---------- 4) cruzamento com Cluster BI (cidade -> cluster/região) ----------
    cluster_bi = pd.read_excel(os.path.join(pasta, "cluster_BI.xlsx"), sheet_name="Cluster")
    cluster_bi["CHAVE_CIDADE_UF"] = cluster_bi["UF_MUN"].apply(normalizar_texto)
    cluster_bi = cluster_bi[["CHAVE_CIDADE_UF", "CLUSTER", "REGIÃO"]].drop_duplicates("CHAVE_CIDADE_UF")

    dados["CHAVE_CIDADE_UF"] = (
        dados["CIDADE_PRESTADOR"].apply(normalizar_texto) + "-" + dados["UF"].apply(normalizar_texto)
    )
    dados = dados.merge(cluster_bi, on="CHAVE_CIDADE_UF", how="left")

    sem_cluster = dados["CLUSTER"].isna().sum()

    # ---------- 5) agregação (reduz de milhões de linhas para uma tabela bem menor) ----------
    grupos = [
        "MES", "UF", "REGIÃO", "ESPECIALIDADE", "CD_PLANO", "NR_PLANO", "CLUSTER",
        "CD_PROCEDIMENTO", "NOME_PROCEDIMENTO", "CD_PRESTADOR", "CIDADE_PRESTADOR",
    ]
    agregado = dados.groupby(grupos, dropna=False, observed=True).agg(
        qtd_procedimentos=("NU_GUIA", "count"),
        soma_vl_procedimento=("VL_PROCEDIMENTO", "sum"),
        soma_vl_franquia=("VL_FRANQUIA", "sum"),
        soma_vl_pago=("VL_PAGO", "sum"),
        soma_uso=("QTD_USO", "sum"),
    ).reset_index()

    aviso = None
    if sem_cluster > 0:
        pct = sem_cluster / len(dados) * 100
        aviso = f"{sem_cluster:,} linhas ({pct:.1f}%) não encontraram cidade correspondente no Cluster BI."

    return agregado, aviso


def aplicar_filtros(agregado, meses=None, ufs=None, regioes=None, especialidades=None, planos=None, clusters=None):
    df = agregado
    if meses:
        df = df[df["MES"].isin(meses)]
    if ufs:
        df = df[df["UF"].isin(ufs)]
    if regioes:
        df = df[df["REGIÃO"].isin(regioes)]
    if especialidades:
        df = df[df["ESPECIALIDADE"].isin(especialidades)]
    if planos:
        df = df[df["NR_PLANO"].isin(planos)]
    if clusters:
        df = df[df["CLUSTER"].isin(clusters)]
    return df


# ============================================================
# RANKINGS
# ============================================================
def ranking_por(df, coluna, top_n=15):
    r = df.groupby(coluna, dropna=False, observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_pago=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    r["media_uso"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    return r.sort_values("valor_pago", ascending=False).head(top_n)


# ============================================================
# EVOLUÇÃO MENSAL
# ============================================================
def evolucao_mensal(df):
    r = df.groupby("MES", observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_pago=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index().sort_values("MES")
    r["media_uso"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    return r


# ============================================================
# SEVERIDADE POR DIMENSÃO (região, cidade, prestador, procedimento, especialidade, cluster)
# ============================================================
def ranking_severidade(df, coluna, top_n=15):
    r = df.groupby(coluna, dropna=False, observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_pago=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    r["custo_medio"] = (r["valor_pago"] / r["qtd_procedimentos"]).round(2)
    r["media_uso"] = (r["quantidade_uso"] / r["qtd_procedimentos"]).round(2)
    # severidade = combinação normalizada (z-score) de custo médio + média de uso
    for c in ["custo_medio", "media_uso"]:
        media, desvio = r[c].mean(), r[c].std()
        r[f"z_{c}"] = 0.0 if desvio == 0 or pd.isna(desvio) else (r[c] - media) / desvio
    r["indice_severidade"] = (r["z_custo_medio"] + r["z_media_uso"]) / 2
    return r.sort_values("indice_severidade", ascending=False).head(top_n).drop(
        columns=["z_custo_medio", "z_media_uso"]
    )


# ============================================================
# OFENSORES (prestadores que se destacam em 2 de 3 critérios)
# ============================================================
def identificar_ofensores(df, percentil=0.95):
    por_prestador = df.groupby("CD_PRESTADOR", observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_pago=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    por_prestador["custo_medio"] = (por_prestador["valor_pago"] / por_prestador["qtd_procedimentos"]).round(2)
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
    ofensores = por_prestador[por_prestador["criterios_atingidos"] >= 2].sort_values(
        "criterios_atingidos", ascending=False
    )
    return ofensores


# ============================================================
# DESVIOS (o quanto cada prestador foge da média da própria especialidade)
# ============================================================
def calcular_desvios(df):
    por_prestador_esp = df.groupby(["CD_PRESTADOR", "ESPECIALIDADE"], observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_pago=("soma_vl_pago", "sum"),
    ).reset_index()
    por_prestador_esp["custo_medio"] = (por_prestador_esp["valor_pago"] / por_prestador_esp["qtd_procedimentos"])

    media_especialidade = por_prestador_esp.groupby("ESPECIALIDADE")["custo_medio"].transform("mean")
    por_prestador_esp["desvio_pct"] = ((por_prestador_esp["custo_medio"] - media_especialidade) / media_especialidade * 100).round(1)
    return por_prestador_esp.sort_values("desvio_pct", ascending=False)


# ============================================================
# WATCHLIST — combina custo, uso e tendência de crescimento por prestador
# ============================================================
def montar_watchlist(df, top_n=20):
    por_prestador = df.groupby("CD_PRESTADOR", observed=True).agg(
        qtd_procedimentos=("qtd_procedimentos", "sum"),
        valor_pago=("soma_vl_pago", "sum"),
        quantidade_uso=("soma_uso", "sum"),
    ).reset_index()
    if len(por_prestador) == 0:
        return por_prestador
    por_prestador["custo_medio"] = por_prestador["valor_pago"] / por_prestador["qtd_procedimentos"]
    por_prestador["media_uso"] = por_prestador["quantidade_uso"] / por_prestador["qtd_procedimentos"]

    # tendência: variação do valor pago entre os 2 meses mais recentes disponíveis no recorte filtrado
    meses_disp = sorted(df["MES"].dropna().unique())
    tendencia = pd.Series(0.0, index=por_prestador["CD_PRESTADOR"])
    if len(meses_disp) >= 2:
        mes_atual, mes_anterior = meses_disp[-1], meses_disp[-2]
        atual = df[df["MES"] == mes_atual].groupby("CD_PRESTADOR", observed=True)["soma_vl_pago"].sum()
        anterior = df[df["MES"] == mes_anterior].groupby("CD_PRESTADOR", observed=True)["soma_vl_pago"].sum()
        variacao = ((atual - anterior) / anterior.replace(0, np.nan) * 100).fillna(0)
        tendencia = variacao.reindex(por_prestador["CD_PRESTADOR"]).fillna(0)

    por_prestador["tendencia_pct"] = tendencia.values

    for c in ["custo_medio", "media_uso", "tendencia_pct"]:
        media, desvio = por_prestador[c].mean(), por_prestador[c].std()
        por_prestador[f"z_{c}"] = 0.0 if desvio == 0 or pd.isna(desvio) else (por_prestador[c] - media) / desvio

    # pondera pelo volume (log para não deixar 1 prestador gigante dominar sozinho)
    peso_volume = np.log1p(por_prestador["qtd_procedimentos"])
    por_prestador["pontuacao_bruta"] = (
        por_prestador["z_custo_medio"] + por_prestador["z_media_uso"] + por_prestador["z_tendencia_pct"]
    ) * peso_volume

    minimo, maximo = por_prestador["pontuacao_bruta"].min(), por_prestador["pontuacao_bruta"].max()
    if maximo > minimo:
        por_prestador["pontuacao"] = ((por_prestador["pontuacao_bruta"] - minimo) / (maximo - minimo) * 100).round(1)
    else:
        por_prestador["pontuacao"] = 50.0

    colunas_finais = ["CD_PRESTADOR", "qtd_procedimentos", "valor_pago", "custo_medio", "media_uso", "tendencia_pct", "pontuacao"]
    return por_prestador[colunas_finais].sort_values("pontuacao", ascending=False).head(top_n)


# ============================================================
# COMPARAÇÃO MÊS A MÊS (com filtro de volume mínimo)
# ============================================================
def comparacao_mensal(df, coluna_dimensao, volume_minimo=30):
    meses_disp = sorted(df["MES"].dropna().unique())
    if len(meses_disp) < 2:
        return pd.DataFrame(), "Só há 1 mês disponível no recorte atual — não dá para comparar."

    mes_atual, mes_anterior = meses_disp[-1], meses_disp[-2]
    atual = df[df["MES"] == mes_atual].groupby(coluna_dimensao, observed=True).agg(
        qtd_atual=("qtd_procedimentos", "sum"), valor_atual=("soma_vl_pago", "sum")
    )
    anterior = df[df["MES"] == mes_anterior].groupby(coluna_dimensao, observed=True).agg(
        qtd_anterior=("qtd_procedimentos", "sum"), valor_anterior=("soma_vl_pago", "sum")
    )
    comp = atual.join(anterior, how="outer").fillna(0).reset_index()
    comp["variacao_pct"] = np.where(
        comp["valor_anterior"] > 0,
        (comp["valor_atual"] - comp["valor_anterior"]) / comp["valor_anterior"] * 100,
        np.nan,
    )
    comp["relevante"] = comp["qtd_atual"] >= volume_minimo
    comp = comp.sort_values("variacao_pct", ascending=False)
    return comp, f"Comparando {mes_atual} vs {mes_anterior}"
