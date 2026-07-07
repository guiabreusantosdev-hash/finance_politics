"""Streamlit UI: five tabs (por período / por mandato / comparação / ministros / legislativo)."""
from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run app/ui.py` coloca a pasta app/ no sys.path, não a raiz do projeto.
# Garantimos a raiz para que `import app...` funcione independentemente do entrypoint.
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from app.models import Observacao  # noqa: E402


def serie_para_df(obs: list[Observacao]) -> pd.DataFrame:
    return pd.DataFrame({"data": [o.data for o in obs], "valor": [o.valor for o in obs]})


def grafico_serie(obs: list[Observacao], titulo: str, unidade: str, fonte: str) -> go.Figure:
    df = serie_para_df(obs)
    fig = go.Figure(go.Scatter(x=df["data"], y=df["valor"], mode="lines+markers"))
    fig.update_layout(title=f"{titulo} ({unidade}) — fonte: {fonte}")
    return fig


def grafico_barras(obs: list[Observacao], titulo: str, unidade: str, fonte: str) -> go.Figure:
    df = serie_para_df(obs)
    fig = go.Figure(go.Bar(x=df["data"], y=df["valor"]))
    fig.update_layout(title=f"{titulo} ({unidade}) — fonte: {fonte}")
    return fig


def grafico_comparacao_indicador(
    nome: str, unidade: str, valor_a: float, valor_b: float, rotulo_a: str, rotulo_b: str
) -> go.Figure:
    fig = go.Figure(go.Bar(x=[rotulo_a, rotulo_b], y=[valor_a, valor_b]))
    fig.update_layout(title=f"{nome} ({unidade})")
    return fig


def main() -> None:  # pragma: no cover - exercised by the manual smoke run
    import streamlit as st

    from app.calculo import tipo_grafico
    from app.config_loader import carregar_indicadores, carregar_mandatos
    from app.db import conectar, criar_schema, observacoes_da_serie, observacoes_entre
    from app.llm import ClaudeCodeClient
    from app.payload import (
        construir_payload_comparacao,
        construir_payload_mandato,
        construir_payload_periodo,
    )

    st.set_page_config(page_title="finance_politics", layout="wide")
    indicadores = carregar_indicadores()
    mandatos = carregar_mandatos()
    conn = conectar()
    criar_schema(conn)

    aba_ano, aba_mandato, aba_comp, aba_min, aba_leg = st.tabs(
        ["Por período", "Por mandato", "Comparação", "Ministros", "Legislativo"]
    )

    with aba_ano:
        import datetime as _dt

        anos = [m.inicio.year for m in mandatos] + [m.fim.year for m in mandatos]
        ano_min, ano_max = min(anos), max(anos)
        ano_ini, ano_fim = st.slider(
            "Período", min_value=ano_min, max_value=ano_max,
            value=(max(ano_min, ano_max - 3), ano_max),
        )
        data_ini = _dt.date(ano_ini, 1, 1)
        data_fim = _dt.date(ano_fim, 12, 31)
        for ind in indicadores:
            obs = observacoes_entre(conn, ind.id, data_ini, data_fim)
            if not obs:
                st.info(f"{ind.nome}: sem dados no período selecionado")
                continue
            fabrica = grafico_barras if tipo_grafico(ind) == "barras" else grafico_serie
            st.plotly_chart(
                fabrica(obs, ind.nome, ind.unidade, ind.fonte),
                width="stretch", key=f"periodo_{ind.id}",
            )
        payload = construir_payload_periodo(conn, indicadores, int(ano_ini), int(ano_fim))
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
                    width="stretch",
                    key=f"mandato_{ind.id}",
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

        comparaveis = [
            d for d in payload_c.deltas if d.valor_a is not None and d.valor_b is not None
        ]
        for i in range(0, len(comparaveis), 2):
            cols = st.columns(2)
            for col, d in zip(cols, comparaveis[i : i + 2]):
                col.plotly_chart(
                    grafico_comparacao_indicador(
                        d.nome, d.unidade, d.valor_a, d.valor_b,
                        payload_c.mandato_a, payload_c.mandato_b,
                    ),
                    width="stretch",
                    key=f"comp_{d.nome}",
                )

        st.dataframe(pd.DataFrame([d.model_dump() for d in payload_c.deltas]))
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_c)

    with aba_min:
        from app.db import (
            aprovar_medida,
            medidas_do_governo,
            salvar_medida,
        )
        from app.medidas_ia import rascunhar_medidas
        from app.ministros import carregar_ministros, ministros_do_governo
        from app.pastas import carregar_pastas
        from app.payload import construir_payload_ministerial

        try:
            ministros = carregar_ministros()
        except Exception as e:  # noqa: BLE001 - captura ampla de propósito: mostra erro e interrompe a renderização
            st.error(f"Falha ao carregar ministros: {e}")
            st.stop()
        nome_g = st.selectbox("Governo", [m.nome for m in mandatos], key="gov_min")
        mandato_g = next(m for m in mandatos if m.nome == nome_g)
        do_gov = ministros_do_governo(ministros, nome_g)

        st.subheader("Ministros")
        st.dataframe(pd.DataFrame([
            {"pasta": m.pasta, "nome": m.nome, "início": m.inicio,
             "fim": m.fim, "fonte": m.fonte}
            for m in do_gov
        ]))

        try:
            descricoes = carregar_pastas()
        except Exception:  # noqa: BLE001 - descrição das pastas é opcional; não derruba a aba
            descricoes = {}
        with st.expander("O que faz cada pasta"):
            for pasta in sorted({m.pasta for m in do_gov}):
                desc = descricoes.get(pasta)
                if desc:
                    st.markdown(f"**{pasta}** — {desc}")

        st.subheader("Medidas aprovadas")
        aprovadas = medidas_do_governo(conn, nome_g, apenas_aprovadas=True)
        if aprovadas:
            st.dataframe(pd.DataFrame([
                {"pasta": m.pasta, "ministro": m.ministro, "título": m.titulo,
                 "descrição": m.descricao, "fonte": m.fonte_url}
                for m in aprovadas
            ]))
        else:
            st.info(
                "Nenhuma medida aprovada ainda. Use **Sugerir medidas (IA)** abaixo para "
                "gerar rascunhos com fonte e aprovar os que quiser — eles aparecerão aqui."
            )

        st.subheader("Sugerir medidas (IA)")
        nomes_min = [f"{m.pasta} — {m.nome}" for m in do_gov]
        if nomes_min:
            escolha = st.selectbox("Ministro", nomes_min, key="min_ia")
            ministro_sel = do_gov[nomes_min.index(escolha)]
            if st.button("Sugerir medidas (IA)", key="btn_ia"):
                try:
                    st.session_state["rascunhos_ia"] = rascunhar_medidas(
                        ClaudeCodeClient(), ministro_sel
                    )
                except Exception as exc:
                    st.error(f"Não foi possível sugerir medidas: {exc}")

        # Render pending drafts OUTSIDE the generate button so they survive reruns
        rascunhos_pendentes: list = list(st.session_state.get("rascunhos_ia", []))
        for i, r in enumerate(rascunhos_pendentes):
            st.warning(f"RASCUNHO (não verificado): {r.titulo}")
            st.write(r.descricao)
            st.write(r.fonte_url)
            col_apr, col_desc = st.columns(2)
            if col_apr.button("Aprovar", key=f"apr_{i}"):
                novo_id = salvar_medida(conn, r)
                aprovar_medida(conn, novo_id)
                st.session_state["rascunhos_ia"].pop(i)
                st.rerun()
            if col_desc.button("Descartar", key=f"desc_{i}"):
                st.session_state["rascunhos_ia"].pop(i)
                st.rerun()

        st.subheader("Resumo do governo")
        payload_min = construir_payload_ministerial(conn, ministros, mandato_g)
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_min)

    with aba_leg:
        from app.db import temas_de
        from app.legislativo import (
            filtrar_leis,
            leis_no_mandato,
            vetos_no_mandato,
        )
        from app.payload import construir_payload_legislativo

        nome_l = st.selectbox("Mandato", [m.nome for m in mandatos], key="mand_leg")
        mandato_l = next(m for m in mandatos if m.nome == nome_l)
        payload_l = construir_payload_legislativo(conn, mandato_l)

        with st.expander("O que significam EC, LC, LO e MP?"):
            st.markdown(
                "- **EC** — Emenda Constitucional (altera a Constituição; quórum de 3/5).\n"
                "- **LC** — Lei Complementar (regula matéria que a Constituição exige; maioria absoluta).\n"
                "- **LO** — Lei Ordinária (lei comum; maioria simples).\n"
                "- **MP** — Medida Provisória (editada pelo Executivo com força de lei imediata; "
                "precisa ser convertida em lei pelo Congresso)."
            )

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
        leis = leis_no_mandato(conn, mandato_l)
        temas_por_lei = {x.id: temas_de(conn, x.id) for x in leis}
        tipos_sel = st.multiselect("Tipo", ["EC", "LC", "LO", "MP"], key="filtro_tipo")
        temas_sel = st.multiselect(
            "Tema", sorted(payload_l.por_tema.keys()), key="filtro_tema"
        )
        leis_f = filtrar_leis(leis, temas_por_lei, tipos_sel, temas_sel)
        if leis_f:
            st.dataframe(pd.DataFrame([
                {
                    "tipo": x.tipo, "número": x.numero, "data": x.data,
                    "temas": ", ".join(temas_por_lei.get(x.id, [])),
                    "ementa": x.ementa, "url": x.url,
                }
                for x in leis_f
            ]))
        else:
            st.info("Nenhuma lei para os filtros selecionados.")

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


if __name__ == "__main__":
    main()
