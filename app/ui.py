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
    from app.payload import construir_payload_ano, construir_payload_comparacao, construir_payload_mandato

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
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload)

    with aba_mandato:
        nome = st.selectbox("Mandato", [m.nome for m in mandatos])
        mandato_sel = next(m for m in mandatos if m.nome == nome)
        payload_m = construir_payload_mandato(conn, indicadores, mandato_sel)
        for ind in indicadores:
            obs = observacoes_da_serie(conn, ind.id)
            if obs:
                st.plotly_chart(
                    grafico_serie(obs, ind.nome, ind.unidade, ind.fonte),
                    use_container_width=True,
                )
        st.dataframe(pd.DataFrame([v.model_dump() for v in payload_m.indicadores]))
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_m)

    with aba_comp:
        nomes = [m.nome for m in mandatos]
        col_a, col_b = st.columns(2)
        a = col_a.selectbox("Mandato A", nomes, index=0)
        b = col_b.selectbox("Mandato B", nomes, index=len(nomes) - 1)
        ma = next(m for m in mandatos if m.nome == a)
        mb = next(m for m in mandatos if m.nome == b)
        payload_c = construir_payload_comparacao(conn, indicadores, ma, mb)
        st.dataframe(pd.DataFrame([d.model_dump() for d in payload_c.deltas]))
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_c)


def _mostrar_resumo(st, conn, client, payload) -> None:  # pragma: no cover
    from app.db import buscar_resumo_cache, historico_resumos, salvar_resumo
    from app.judge import julgar
    from app.payload import descrever_payload, hash_payload
    from app.resumo import gerar_resumo

    ph = hash_payload(payload)
    tipo, identificador = descrever_payload(payload)
    cache = buscar_resumo_cache(conn, ph)

    if cache is not None:
        st.success(f"✅ Em cache (gerado em {cache.criado_em} · {cache.modelo})")
        for eixo, txt in cache.resumo.paragrafos_por_eixo.items():
            st.markdown(f"**{eixo}** — {txt}")
    label = "Regerar resumo" if cache is not None else "Gerar resumo"

    if st.button(label, key=f"btn_{tipo}_{identificador}"):
        try:
            resumo = gerar_resumo(client, payload)
            veredito = None
            try:
                veredito = julgar(client, payload, resumo)
                if not veredito.ancorado or not veredito.neutro:
                    aviso = f"⚠️ O juiz de IA detectou problemas: {veredito.observacoes}"
                    if veredito.numeros_fora_do_payload:
                        aviso += f" Números fora do payload: {veredito.numeros_fora_do_payload}"
                    st.warning(aviso)
            except Exception:
                pass  # juiz é não-fatal
            salvar_resumo(
                conn,
                payload=payload,
                resumo=resumo,
                veredito=veredito,
                modelo=client.modelo or "claude-code-default",
            )
            st.info("Resumo gerado e salvo:")
            for eixo, txt in resumo.paragrafos_por_eixo.items():
                st.markdown(f"**{eixo}** — {txt}")
        except ValueError as exc:
            st.error(f"Não foi possível gerar o resumo: {exc}")

    hist = historico_resumos(conn, tipo, identificador)
    if hist:
        with st.expander(f"Histórico ({len(hist)})"):
            for reg in hist:
                flag = ""
                if reg.veredito is not None:
                    ok = reg.veredito.get("ancorado") and reg.veredito.get("neutro")
                    flag = " ✅" if ok else " ⚠️"
                st.markdown(f"- **{reg.criado_em}** · {reg.modelo}{flag}")
