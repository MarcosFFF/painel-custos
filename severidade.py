"""
Módulo de Severidade — carrega os CSVs (guias, separador ';'), cruza com 1004_claude.xlsx
(USO por procedimento) e cluster_claude.xlsx (cidade -> cluster), deriva a Região a partir
da UF, e fornece todos os cálculos usados na aba "Severidade" do painel.

ARQUIVOS ESPERADOS (na mesma pasta do app.py, no repositório):
  - *4016R.csv ou *4016R_parte_N.csv  (um (ou várias partes) por mês, separador ';',
    decimal ',', colunas: NU_GUIA, DATA_SOL, DATA_AUT, DATA_ATEND, CD_USUARIO, CD_PLANO,
    ESPECIALIDADE, CD_PROCEDIMENTO, CD_TUSS, NOME_PROCEDIMENTO, VL_PROCEDIMENTO,
    VL_FRANQUIA, VL_PAGO, STATUS_PROCED, CD_PRESTADOR, CIDADE_PRESTADOR, UF, EXECUCAO)
  - 1004_claude.xlsx   (CODIGO, USO)
  - cluster_claude.xlsx (aba "cluster_claude": UF_MUN, UF, NOME DO MUNICÍPIO, CLUSTER)

A "Região" NÃO vem de nenhum arquivo — é derivada da UF (mapeamento fixo, os 27
estados brasileiros só podem pertencer a uma das 5 regiões).
"""

import glob
import os
import unicodedata
import numpy as np
import pandas as pd
import streamlit as st


# ============================================================
# UF -> REGIÃO (mapeamento fixo e conhecido — não depende de nenhum arquivo)
# ============================================================
UF_PARA_REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
    "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}


# ============================================================
# NORMALIZAÇÃO DE TEXTO (para cruzar CIDADE_PRESTADOR com o Cluster,
# e para casar nomes de colunas sem depender de acento/maiúscula exatos)
# ============================================================
def normalizar_texto(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    texto = str(v).strip().upper()
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return texto


def _corrigir_mojibake(texto):
    """Desfaz texto que passou por um encoding errado (UTF-8 lido como Latin-1),
    que transforma 'Execução' em 'ExecuÃ§Ã£o', 'São Paulo' em 'SÃ£o Paulo', etc."""
    if texto is None:
        return texto
    s = str(texto)
    if "Ã" not in s and "Â" not in s:
        return s
    try:
        return s.encode("latin1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


# Nomes de coluna esperados no CSV, na forma "canônica" que o resto do código usa.
COLUNAS_ESPERADAS = [
    "NU_GUIA", "DATA_SOL", "DATA_AUT", "DATA_ATEND", "CD_USUARIO", "CD_PLANO", "NR_PLANO",
    "ESPECIALIDADE", "CD_PROCEDIMENTO", "CD_TUSS", "NOME_PROCEDIMENTO",
    "VL_PROCEDIMENTO", "VL_FRANQUIA", "VL_PAGO", "STATUS_PROCED",
    "CD_PRESTADOR", "CIDADE_PRESTADOR", "UF", "EXECUCAO",
]


def _parse_valor_monetario(v):
    """
    Aceita os dois formatos possíveis:
      - "32.12"     (ponto já é o decimal — não mexe)
      - "1.234,56"  (formato BR — ponto é milhar, vírgula é decimal)
    """
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
    """
    Casa os nomes de coluna do arquivo com os nomes esperados, ignorando
    diferenças de acento e maiúscula/minúscula (ex.: 'Execução', 'EXECUÇÃO' e
    'EXECUCAO' são todos reconhecidos como a mesma coluna).
    Retorna um dict {nome_esperado: nome_real_no_arquivo}.
    """
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


# ============================================================
# LEITURA DE CSV (separador ';', decimal ',' — padrão brasileiro).
# Tenta UTF-8 primeiro; se der erro de acentuação, cai para latin1 (cp1252).
# ============================================================
def _ler_csv_parte(caminho, colunas_esperadas):
    tentativas_encoding = ["utf-8", "latin1"]
    df = None
    ultimo_erro = None
    for enc in tentativas_encoding:
        try:
            df = pd.read_csv(
                caminho, sep=";", encoding=enc,
                dtype=str,  # lê tudo como texto primeiro; convertemos depois com controle
                low_memory=False,
            )
            break
        except (UnicodeDecodeError, UnicodeError) as e:
            ultimo_erro = e
            continue
    if df is None:
        raise ValueError(f"Não consegui ler {caminho} nem em UTF-8 nem em latin1: {ultimo_erro}")

    mapa_colunas = _casar_colunas(df.columns, colunas_esperadas)
    faltando = [c for c in colunas_esperadas if c not in mapa_colunas]
    if faltando:
        raise ValueError(
            f"Colunas faltando em {os.path.basename(caminho)}: {faltando}. "
            f"Colunas encontradas: {list(df.columns)}"
        )

    # renomeia para os nomes canônicos e seleciona só o necessário
    df = df[[mapa_colunas[c] for c in colunas_esperadas]].copy()
    df.columns = colunas_esperadas

    # datas: formato brasileiro (dia primeiro)
    for c in ["DATA_SOL", "DATA_AUT", "DATA_ATEND"]:
        df[c] = pd.to_datetime(df[c], dayfirst=True, errors="coerce")

    # numéricos simples (NU_GUIA e CD_USUARIO são identificadores tipo hash — ficam como texto)
    for c in ["CD_PLANO", "CD_PROCEDIMENTO", "CD_TUSS", "CD_PRESTADOR"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["NU_GUIA"] = df["NU_GUIA"].astype(str).str.strip()
    df["CD_USUARIO"] = df["CD_USUARIO"].astype(str).str.strip()

    # valores monetários: aceita tanto "32.12" (ponto decimal) quanto "1.234,56" (formato BR)
    for c in ["VL_PROCEDIMENTO", "VL_FRANQUIA", "VL_PAGO"]:
        df[c] = df[c].apply(_parse_valor_monetario)

    # corrige mojibake nos valores de texto (ex.: cidade com acento quebrado)
    for c in ["ESPECIALIDADE", "NR_PLANO", "NOME_PROCEDIMENTO", "STATUS_PROCED", "CIDADE_PRESTADOR", "UF", "EXECUCAO"]:
        df[c] = df[c].apply(_corrigir_mojibake)

    df["UF"] = df["UF"].astype(str).str.strip().str.upper()

    # remove linhas 100% duplicadas — a mesma guia/procedimento pode aparecer repetida
    # várias vezes por artefato de exportação; cada ocorrência real deve contar 1 vez só
    df = df.drop_duplicates()

    return df


# ============================================================
# AGRUPAMENTO DE ARQUIVOS EM PARTES (um mês pode vir dividido em várias
# partes, por causa do limite de 25MB do upload pelo navegador do GitHub)
# ============================================================
def _chave_mes(caminho):
    """Agrupa partes do mesmo mês: '01 2026 4016R_parte_2.csv' -> '01 2026 4016R'."""
    nome = os.path.basename(caminho)
    nome_sem_ext = os.path.splitext(nome)[0]
    if "_parte_" in nome_sem_ext:
        nome_sem_ext = nome_sem_ext.split("_parte_")[0]
    return nome_sem_ext


def _numero_parte(caminho):
    nome = os.path.basename(caminho)
    if "_parte_" in nome:
        try:
            return int(nome.split("_parte_")[1].split(".")[0])
        except ValueError:
            return 0
    return 0


# ============================================================
# CARREGAMENTO E CRUZAMENTO DOS DADOS (cacheado — só recalcula quando pedido)
# ============================================================
@st.cache_data(show_spinner="Carregando dados de severidade...")
def carregar_base_severidade(pasta="."):
    # ---------- 1) csvs (aceita arquivos inteiros OU divididos em partes) ----------
    candidatos = sorted(
        glob.glob(os.path.join(pasta, "*4016R.csv"))
        + glob.glob(os.path.join(pasta, "*4016R_parte_*.csv"))
    )
    if not candidatos:
        return None, "Nenhum arquivo .csv encontrado (padrão *4016R.csv ou *4016R_parte_N.csv)."

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

    # ---------- 2) mês de referência (usa DATA_ATEND; se vazio, cai para DATA_SOL) ----------
    dados["DATA_REF"] = dados["DATA_ATEND"]
    sem_atend = dados["DATA_REF"].isna()
    dados.loc[sem_atend, "DATA_REF"] = dados.loc[sem_atend, "DATA_SOL"]
    dados["MES"] = dados["DATA_REF"].dt.strftime("%Y-%m")

    # ---------- 3) cruzamento com 1004 (USO por procedimento) ----------
    tabela_1004 = pd.read_excel(os.path.join(pasta, "1004_claude.xlsx"), sheet_name=0)
    mapa_1004 = _casar_colunas(tabela_1004.columns, ["CODIGO", "USO"])
    tabela_1004 = tabela_1004[[mapa_1004["CODIGO"], mapa_1004["USO"]]].copy()
    tabela_1004.columns = ["CD_PROCEDIMENTO", "USO_PROCEDIMENTO"]
    tabela_1004["CD_PROCEDIMENTO"] = pd.to_numeric(tabela_1004["CD_PROCEDIMENTO"], errors="coerce")
    dados = dados.merge(tabela_1004, on="CD_PROCEDIMENTO", how="left")
    dados["USO_PROCEDIMENTO"] = dados["USO_PROCEDIMENTO"].fillna(0)
    dados["QTD_USO"] = dados["USO_PROCEDIMENTO"]  # cada linha = 1 procedimento; soma por grupo dá a "quantidade de uso"

    # ---------- 4) cruzamento com Cluster (cidade -> cluster) ----------
    cluster_bi = pd.read_excel(os.path.join(pasta, "cluster_claude.xlsx"), sheet_name=0)
    mapa_cluster = _casar_colunas(cluster_bi.columns, ["UF_MUN", "CLUSTER"])
    cluster_bi = cluster_bi[[mapa_cluster["UF_MUN"], mapa_cluster["CLUSTER"]]].copy()
    cluster_bi.columns = ["UF_MUN", "CLUSTER"]
    cluster_bi["CHAVE_CIDADE_UF"] = cluster_bi["UF_MUN"].apply(normalizar_texto)
    cluster_bi = cluster_bi[["CHAVE_CIDADE_UF", "CLUSTER"]].drop_duplicates("CHAVE_CIDADE_UF")

    dados["CHAVE_CIDADE_UF"] = (
        dados["CIDADE_PRESTADOR"].apply(normalizar_texto) + "-" + dados["UF"].apply(normalizar_texto)
    )
    dados = dados.merge(cluster_bi, on="CHAVE_CIDADE_UF", how="left")

    # ---------- 5) Região derivada da UF (sem depender de arquivo) ----------
    dados["REGIAO"] = dados["UF"].map(UF_PARA_REGIAO)

    sem_cluster = dados["CLUSTER"].isna().sum()
    sem_regiao = dados["REGIAO"].isna().sum()

    # ---------- 6) agregação (reduz de milhões de linhas para uma tabela bem menor) ----------
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
    if sem_cluster > 0:
        avisos.append(f"{sem_cluster:,} linhas ({sem_cluster/len(dados)*100:.1f}%) não encontraram cidade correspondente no Cluster.")
    if sem_regiao > 0:
        avisos.append(f"{sem_regiao:,} linhas ({sem_regiao/len(dados)*100:.1f}%) têm UF não reconhecida (sem Região).")
    aviso = " | ".join(avisos) if avisos else None

    return agregado, aviso


def aplicar_filtros(agregado, meses=None, ufs=None, regioes=None, especialidades=None, planos=None, clusters=None):
    df = agregado
    if meses:
        df = df[df["MES"].isin(meses)]
    if ufs:
        df = df[df["UF"].isin(ufs)]
    if regioes:
        df = df[df["REGIAO"].isin(regioes)]
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