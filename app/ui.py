"""Streamlit UI: five tabs (por ano / por mandato / comparação / ministros / legislativo)."""
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

    aba_ano, aba_mandato, aba_comp, aba_min, aba_leg = st.tabs(
        ["Por ano", "Por mandato", "Comparação", "Ministros", "Legislativo"]
    )

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

    with aba_min:
        from app.db import (
            aprovar_medida,
            descartar_medida,
            medidas_do_governo,
            salvar_medida,
        )
        from app.medidas_ia import rascunhar_medidas
        from app.ministros import carregar_ministros, ministros_do_governo
        from app.payload import construir_payload_ministerial

        ministros = carregar_ministros()
        nome_g = st.selectbox("Governo", [m.nome for m in mandatos], key="gov_min")
        mandato_g = next(m for m in mandatos if m.nome == nome_g)
        do_gov = ministros_do_governo(ministros, nome_g)

        st.subheader("Ministros")
        st.dataframe(pd.DataFrame([
            {"pasta": m.pasta, "nome": m.nome, "início": m.inicio,
             "fim": m.fim, "fonte": m.fonte}
            for m in do_gov
        ]))

        st.subheader("Medidas aprovadas")
        aprovadas = medidas_do_governo(conn, nome_g, apenas_aprovadas=True)
        if aprovadas:
            st.dataframe(pd.DataFrame([
                {"pasta": m.pasta, "ministro": m.ministro, "título": m.titulo,
                 "descrição": m.descricao, "fonte": m.fonte_url}
                for m in aprovadas
            ]))
        else:
            st.caption("Nenhuma medida aprovada ainda.")

        st.subheader("Sugerir medidas (IA)")
        nomes_min = [f"{m.pasta} — {m.nome}" for m in do_gov]
        if nomes_min:
            escolha = st.selectbox("Ministro", nomes_min, key="min_ia")
            ministro_sel = do_gov[nomes_min.index(escolha)]
            if st.button("Sugerir medidas (IA)", key="btn_ia"):
                try:
                    rascunhos = rascunhar_medidas(ClaudeCodeClient(), ministro_sel)
                    for r in rascunhos:
                        st.warning(f"RASCUNHO (não verificado): {r.titulo}")
                        st.write(r.descricao)
                        st.write(r.fonte_url)
                        novo_id = salvar_medida(conn, r)
                        if st.button(f"Aprovar #{novo_id}", key=f"apr_{novo_id}"):
                            aprovar_medida(conn, novo_id)
                        if st.button(f"Descartar #{novo_id}", key=f"desc_{novo_id}"):
                            descartar_medida(conn, novo_id)
                except Exception as exc:
                    st.error(f"Não foi possível sugerir medidas: {exc}")

        st.subheader("Resumo do governo")
        payload_min = construir_payload_ministerial(conn, ministros, mandato_g)
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_min)

    with aba_leg:
        from app.legislativo import leis_no_mandato, vetos_no_mandato
        from app.payload import construir_payload_legislativo

        nome_l = st.selectbox("Mandato", [m.nome for m in mandatos], key="mand_leg")
        mandato_l = next(m for m in mandatos if m.nome == nome_l)
        payload_l = construir_payload_legislativo(conn, mandato_l)

        c1, c2 = st.columns(2)
        c1.metric("Leis sancionadas", payload_l.total_leis)
        c2.metric("Vetos", payload_l.total_vetos)
        if payload_l.por_tipo:
            st.bar_chart(pd.DataFrame(
                {"tipo": list(payload_l.por_tipo), "n": list(payload_l.por_tipo.values())}
            ).set_index("tipo"))
        if payload_l.por_tema:
            st.bar_chart(pd.DataFrame(
                {"tema": list(payload_l.por_tema), "n": list(payload_l.por_tema.values())}
            ).set_index("tema"))

        st.subheader("Leis")
        st.dataframe(pd.DataFrame([
            {"tipo": x.tipo, "número": x.numero, "data": x.data, "ementa": x.ementa, "url": x.url}
            for x in leis_no_mandato(conn, mandato_l)
        ]))
        st.subheader("Vetos")
        st.dataframe(pd.DataFrame([
            {"data": v.data, "tipo": v.tipo, "matéria": v.materia, "descrição": v.descricao}
            for v in vetos_no_mandato(conn, mandato_l)
        ]))

        st.subheader("Resumo legislativo")
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_l)


def _mostrar_resumo(st, conn, client, payload) -> None:  # pragma: no cover
    from app.db import buscar_resumo_cache, historico_resumos, salvar_resumo
    from app.judge import julgar
    from app.models import PayloadLegislativoMandato, PayloadMinisterialGoverno
    from app.payload import descrever_payload, hash_payload
    from app.resumo import _REGRAS_LEGISLATIVO, _REGRAS_MINISTERIAL, gerar_resumo

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
            if isinstance(payload, PayloadLegislativoMandato):
                resumo = gerar_resumo(client, payload, regras=_REGRAS_LEGISLATIVO)
            elif isinstance(payload, PayloadMinisterialGoverno):
                resumo = gerar_resumo(client, payload, regras=_REGRAS_MINISTERIAL)
            else:
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
