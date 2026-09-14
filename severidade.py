# ============================================================
# ABA TEMPORÁRIA — Códigos 9040, 110, 2035, 5314
# ============================================================
# Onde colar:
#
# 1) Na página Severidade, troque a linha que cria as abas
#
#        tab_rank, tab_evolucao, tab_ofensores, tab_desvios, tab_resumo = st.tabs(
#            ["Ranking de Severidade", "Evolução mensal", "Ofensores", "Desvios de Solicitações", "Resumo"]
#        )
#
#    por:
#
#        tab_rank, tab_evolucao, tab_ofensores, tab_desvios, tab_resumo, tab_temp = st.tabs(
#            ["Ranking de Severidade", "Evolução mensal", "Ofensores", "Desvios de Solicitações", "Resumo",
#             "🧪 Temp: 9040/110/2035/5314"]
#        )
#
# 2) Cole o bloco "with tab_temp:" abaixo em QUALQUER ponto depois da definição
#    da função _grafico_severidade (ela é reaproveitada aqui) — o mais simples é
#    colar logo depois do bloco "with tab_resumo:" já existente, mantendo a
#    mesma indentação (dentro do "elif st.session_state.pagina == 'severidade':").
#
# Como é temporária, deixei tudo dentro de um único bloco "with tab_temp:" —
# pra remover depois, basta apagar esse bloco e voltar a linha do st.tabs(...)
# ao estado original (tirando "tab_temp" e o rótulo "🧪 Temp: ...").
# ============================================================

with tab_temp:
    st.markdown("#### 🧪 Aba temporária — Procedimentos 9040, 110, 2035 e 5314")
    st.caption(
        "Aba temporária, só para consulta pontual desses 4 códigos — respeita os filtros ativos "
        "no topo da página (mês, UF, especialidade etc.), igual às demais abas. FASE calculado com "
        "o mesmo peso-do-grupo (denominador) da aba 'Ranking de Severidade', então os valores de FASE "
        "aqui são comparáveis com os de lá."
    )

    codigos_temp = [9040, 110, 2035, 5314]

    # Mapa código -> nome do procedimento, dentro dos filtros ativos (1 código = 1 nome,
    # assumindo que cada CD_PROCEDIMENTO tem uma única NOME_PROCEDIMENTO associada — é assim
    # que o resto do painel já trata "vidas" por procedimento, via NOME_PROCEDIMENTO).
    mapa_cod_nome_temp = (
        df_filtrado[df_filtrado["CD_PROCEDIMENTO"].isin(codigos_temp)]
        .drop_duplicates("CD_PROCEDIMENTO")
        .set_index("CD_PROCEDIMENTO")["NOME_PROCEDIMENTO"]
        .to_dict()
    )
    codigos_ausentes_temp = [c for c in codigos_temp if c not in mapa_cod_nome_temp]
    if codigos_ausentes_temp:
        st.caption(f"Códigos sem ocorrência nos filtros atuais: {', '.join(str(c) for c in codigos_ausentes_temp)}.")

    nomes_temp = list(mapa_cod_nome_temp.values())

    if not nomes_temp:
        st.info("Nenhum dos 4 códigos apareceu nos filtros atuais.")
    else:
        df_temp = df_filtrado[df_filtrado["CD_PROCEDIMENTO"].isin(codigos_temp)]
        usuarios_temp = usuarios_filtrado[usuarios_filtrado["NOME_PROCEDIMENTO"].isin(nomes_temp)]

        # ---- métricas gerais (os 4 códigos somados, sem contar a mesma vida 2x) ----
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

        st.divider()

        # ---- ranking por código (com FASE) ----
        # Calcula o FASE sobre TODA a base filtrada (mesmo denominador/peso-do-grupo da aba
        # "Ranking de Severidade") e só depois recorta para os 4 códigos — assim o FASE daqui
        # é comparável com o da outra aba, em vez de inflado por comparar só entre eles 4.
        rank_geral_temp = ranking_severidade(
            df_filtrado, "NOME_PROCEDIMENTO", top_n=1_000_000, usuarios=usuarios_filtrado
        )
        rank_temp = rank_geral_temp[rank_geral_temp["NOME_PROCEDIMENTO"].isin(nomes_temp)].copy()
        nome_para_codigo_temp = {v: k for k, v in mapa_cod_nome_temp.items()}
        rank_temp["CD_PROCEDIMENTO"] = rank_temp["NOME_PROCEDIMENTO"].map(nome_para_codigo_temp)
        rank_temp["rotulo"] = (
            rank_temp["CD_PROCEDIMENTO"].astype(int).astype(str) + " — " + rank_temp["NOME_PROCEDIMENTO"]
        )

        exib_rank_temp = rank_temp.copy()
        exib_rank_temp["qtd_procedimentos"] = exib_rank_temp["qtd_procedimentos"].map(fmt_int)
        exib_rank_temp["qtd_usuarios"] = exib_rank_temp["qtd_usuarios"].map(fmt_int)
        exib_rank_temp["quantidade_uso"] = exib_rank_temp["quantidade_uso"].map(fmt_int)
        exib_rank_temp["uso_por_procedimento"] = exib_rank_temp["uso_por_procedimento"].map(fmt_float2)
        exib_rank_temp["uso_por_vida"] = exib_rank_temp["uso_por_vida"].map(fmt_float2)
        exib_rank_temp["fase"] = exib_rank_temp["fase"].map(fmt_fase)
        exib_rank_temp = exib_rank_temp[[
            "rotulo", "qtd_procedimentos", "qtd_usuarios", "quantidade_uso",
            "uso_por_procedimento", "uso_por_vida", "fase",
        ]].rename(columns={
            "rotulo": "Procedimento",
            "qtd_procedimentos": "Qtd procedimentos",
            "qtd_usuarios": "Qtd vidas",
            "quantidade_uso": "Soma de uso",
            "uso_por_procedimento": "Uso/procedimento",
            "uso_por_vida": "Uso/vida",
            "fase": "FASE",
        })
        st.dataframe(exib_rank_temp, hide_index=True, use_container_width=True)

        # ---- gráficos interativos: qtd de procedimentos e qtd de vidas por código ----
        col_qtd_temp, col_vidas_temp = st.columns(2)
        with col_qtd_temp:
            fig_qtd_temp = px.bar(
                rank_temp.sort_values("qtd_procedimentos"),
                x="qtd_procedimentos", y="rotulo", orientation="h",
                text="qtd_procedimentos", title="Qtd de procedimentos por código",
                color="qtd_procedimentos", color_continuous_scale=["#87CEEB", "#1f6fb2"],
            )
            fig_qtd_temp.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False)
            fig_qtd_temp.update_layout(
                height=320, margin=dict(l=10, r=60, t=40, b=10),
                coloraxis_showscale=False, yaxis_title="",
            )
            st.plotly_chart(fig_qtd_temp, use_container_width=True)
        with col_vidas_temp:
            fig_vidas_temp = px.bar(
                rank_temp.sort_values("qtd_usuarios"),
                x="qtd_usuarios", y="rotulo", orientation="h",
                text="qtd_usuarios", title="Qtd de vidas por código",
                color="qtd_usuarios", color_continuous_scale=["#f6d186", "#e07b39"],
            )
            fig_vidas_temp.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False)
            fig_vidas_temp.update_layout(
                height=320, margin=dict(l=10, r=60, t=40, b=10),
                coloraxis_showscale=False, yaxis_title="",
            )
            st.plotly_chart(fig_vidas_temp, use_container_width=True)

        # ---- FASE por código (reaproveita o mesmo estilo de gráfico da aba "Ranking de Severidade") ----
        _grafico_severidade(rank_temp, "rotulo", "FASE por código de procedimento", altura=320)

        st.divider()
        st.markdown("**Evolução mensal por código**")

        evol_temp_frames = []
        for cod in codigos_temp:
            nome_cod = mapa_cod_nome_temp.get(cod)
            if nome_cod is None:
                continue
            sub_df = df_temp[df_temp["CD_PROCEDIMENTO"] == cod]
            sub_usu = usuarios_temp[usuarios_temp["NOME_PROCEDIMENTO"] == nome_cod]
            if sub_df.empty:
                continue
            evo = evolucao_mensal(sub_df, sub_usu)
            evo["Procedimento"] = f"{cod} — {nome_cod}"
            evol_temp_frames.append(evo)

        if evol_temp_frames:
            evol_temp = pd.concat(evol_temp_frames, ignore_index=True)

            fig_uso_mes_temp = px.line(
                evol_temp, x="MES", y="quantidade_uso", color="Procedimento", markers=True,
                title="Soma de uso por mês, por código",
            )
            fig_uso_mes_temp.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="Soma de uso")
            st.plotly_chart(fig_uso_mes_temp, use_container_width=True)

            col_qtd_mes_temp, col_vidas_mes_temp = st.columns(2)
            with col_qtd_mes_temp:
                fig_qtd_mes_temp = px.line(
                    evol_temp, x="MES", y="qtd_procedimentos", color="Procedimento", markers=True,
                    title="Qtd de procedimentos por mês",
                )
                fig_qtd_mes_temp.update_layout(
                    height=340, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="Qtd procedimentos"
                )
                st.plotly_chart(fig_qtd_mes_temp, use_container_width=True)
            with col_vidas_mes_temp:
                fig_vidas_mes_temp = px.line(
                    evol_temp, x="MES", y="qtd_usuarios", color="Procedimento", markers=True,
                    title="Qtd de vidas por mês",
                )
                fig_vidas_mes_temp.update_layout(
                    height=340, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="Qtd vidas"
                )
                st.plotly_chart(fig_vidas_mes_temp, use_container_width=True)

            fig_fase_mes_temp = px.line(
                evol_temp, x="MES", y="fase", color="Procedimento", markers=True,
                title="FASE por mês, por código",
            )
            fig_fase_mes_temp.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="FASE")
            st.plotly_chart(fig_fase_mes_temp, use_container_width=True)
        else:
            st.info("Sem dados mensais suficientes para montar a evolução.")
