"""Streamlit UI: three tabs (por ano / por mandato / comparação)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from app.models import Observacao


def serie_para_df(obs: list[Observacao]) -> pd.DataFrame:
    return pd.DataFrame({"data": [o.data for o in obs], "valor": [o.valor for o in obs]})


def grafico_serie(obs: list[Observacao], titulo: str, unidade: str, fonte: str) -> go.Figure:
    df = serie_para_df(obs)
    fig = go.Figure(go.Scatter(x=df["data"], y=df["valor"], mode="lines+markers"))
    fig.update_layout(title=f"{titulo} ({unidade}) — fonte: {fonte}")
    return fig


def main() -> None:  # pragma: no cover - exercised by the manual smoke run
    import streamlit as st

    from app.config_loader import carregar_indicadores, carregar_mandatos
    from app.db import conectar, criar_schema, observacoes_da_serie
    from app.llm import ClaudeCodeClient
    from app.payload import construir_payload_ano, construir_payload_comparacao

    st.set_page_config(page_title="finance_politics", layout="wide")
    indicadores = carregar_indicadores()
    mandatos = carregar_mandatos()
    conn = conectar()
    criar_schema(conn)

    aba_ano, aba_mandato, aba_comp = st.tabs(["Por ano", "Por mandato", "Comparação"])

    with aba_ano:
        ano = st.number_input("Ano", min_value=2003, max_value=2026, value=2024, step=1)
        for ind in indicadores:
            obs = observacoes_da_serie(conn, ind.id)
            if obs:
                st.plotly_chart(grafico_serie(obs, ind.nome, ind.unidade, ind.fonte),
                                use_container_width=True)
        payload = construir_payload_ano(conn, indicadores, int(ano))
        if st.button("Gerar resumo do ano"):
            _mostrar_resumo(st, ClaudeCodeClient(), payload)

    with aba_mandato:
        nome = st.selectbox("Mandato", [m.nome for m in mandatos])
        st.write(f"Mandato selecionado: {nome}")

    with aba_comp:
        nomes = [m.nome for m in mandatos]
        col_a, col_b = st.columns(2)
        a = col_a.selectbox("Mandato A", nomes, index=0)
        b = col_b.selectbox("Mandato B", nomes, index=len(nomes) - 1)
        ma = next(m for m in mandatos if m.nome == a)
        mb = next(m for m in mandatos if m.nome == b)
        payload_c = construir_payload_comparacao(conn, indicadores, ma, mb)
        st.dataframe(pd.DataFrame([d.model_dump() for d in payload_c.deltas]))
        if st.button("Gerar resumo comparativo"):
            _mostrar_resumo(st, ClaudeCodeClient(), payload_c)


def _mostrar_resumo(st, client, payload) -> None:  # pragma: no cover
    from app.resumo import gerar_resumo

    try:
        resumo = gerar_resumo(client, payload)
        st.info("Resumo gerado por IA a partir dos dados acima:")
        for eixo, txt in resumo.paragrafos_por_eixo.items():
            st.markdown(f"**{eixo}** — {txt}")
    except ValueError as exc:
        st.error(f"Não foi possível gerar o resumo: {exc}")
