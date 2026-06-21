"""Build structured payloads the LLM will narrate (never compute)."""
from __future__ import annotations

import datetime
import hashlib

from app.calculo import valor_no_mandato, valor_no_periodo, variacao
from app.db import observacoes_da_serie
from app.models import (
    DeltaIndicador,
    Indicador,
    Mandato,
    PayloadAno,
    PayloadComparacao,
    PayloadLegislativoMandato,
    PayloadMandato,
    PayloadMinisterialGoverno,
    ValorIndicador,
    ValorIndicadorMandato,
)


def _data_ref_do_ano(obs, ano: int) -> datetime.date | None:
    do_ano = sorted((o.data for o in obs if o.data.year == ano))
    return do_ano[-1] if do_ano else None


def construir_payload_ano(conn, indicadores: list[Indicador], ano: int) -> PayloadAno:
    valores: list[ValorIndicador] = []
    faltantes: list[str] = []
    for ind in indicadores:
        obs = observacoes_da_serie(conn, ind.id)
        v = valor_no_periodo(obs, ind, ano)
        if v is None:
            faltantes.append(ind.nome)
        valores.append(ValorIndicador(
            nome=ind.nome, valor=v, unidade=ind.unidade, fonte=ind.fonte,
            data_ref=_data_ref_do_ano(obs, ano),
        ))
    return PayloadAno(ano=ano, indicadores=valores, faltantes=faltantes)


def construir_payload_mandato(
    conn, indicadores: list[Indicador], mandato: Mandato
) -> PayloadMandato:
    valores: list[ValorIndicadorMandato] = []
    faltantes: list[str] = []
    for ind in indicadores:
        obs = observacoes_da_serie(conn, ind.id)
        v_inicio = valor_no_mandato(obs, ind, mandato, "inicio")
        v_fim = valor_no_mandato(obs, ind, mandato, "fim")
        var = variacao(v_inicio, v_fim)
        if v_inicio is None and v_fim is None:
            faltantes.append(ind.nome)
        valores.append(ValorIndicadorMandato(
            nome=ind.nome,
            valor_inicio=v_inicio,
            valor_fim=v_fim,
            variacao=var,
            unidade=ind.unidade,
            fonte=ind.fonte,
        ))
    return PayloadMandato(
        mandato=mandato.nome,
        ano_inicio=mandato.inicio.year,
        ano_fim=mandato.fim.year,
        indicadores=valores,
        faltantes=faltantes,
    )


def construir_payload_comparacao(
    conn, indicadores: list[Indicador], mand_a: Mandato, mand_b: Mandato
) -> PayloadComparacao:
    deltas: list[DeltaIndicador] = []
    for ind in indicadores:
        obs = observacoes_da_serie(conn, ind.id)
        va = valor_no_mandato(obs, ind, mand_a, "fim")
        vb = valor_no_mandato(obs, ind, mand_b, "fim")
        delta = vb - va if va is not None and vb is not None else None
        deltas.append(DeltaIndicador(
            nome=ind.nome, valor_a=va, valor_b=vb, delta=delta,
            unidade=ind.unidade, fonte=ind.fonte,
        ))
    return PayloadComparacao(
        mandato_a=mand_a.nome,
        mandato_b=mand_b.nome,
        ano_inicio_a=mand_a.inicio.year,
        ano_fim_a=mand_a.fim.year,
        ano_inicio_b=mand_b.inicio.year,
        ano_fim_b=mand_b.fim.year,
        deltas=deltas,
    )


def hash_payload(
    payload: PayloadAno | PayloadMandato | PayloadComparacao | PayloadMinisterialGoverno | PayloadLegislativoMandato,
) -> str:
    return hashlib.sha256(payload.model_dump_json().encode("utf-8")).hexdigest()


def descrever_payload(
    payload: PayloadAno | PayloadMandato | PayloadComparacao | PayloadMinisterialGoverno | PayloadLegislativoMandato,
) -> tuple[str, str]:
    if isinstance(payload, PayloadAno):
        return ("ano", str(payload.ano))
    if isinstance(payload, PayloadMandato):
        return ("mandato", payload.mandato)
    if isinstance(payload, PayloadMinisterialGoverno):
        return ("ministerial", payload.governo)
    if isinstance(payload, PayloadLegislativoMandato):
        return ("legislativo", payload.mandato)
    return ("comparacao", f"{payload.mandato_a} × {payload.mandato_b}")


def construir_payload_ministerial(conn, ministros, mandato):
    from app.db import medidas_do_governo
    from app.ministros import ministros_do_governo
    from app.models import MedidaResumo, PayloadMinisterialGoverno

    do_gov = ministros_do_governo(ministros, mandato.nome)
    aprovadas = medidas_do_governo(conn, mandato.nome, apenas_aprovadas=True)
    return PayloadMinisterialGoverno(
        governo=mandato.nome,
        ano_inicio=mandato.inicio.year,
        ano_fim=mandato.fim.year,
        ministros=[f"{m.pasta} — {m.nome}" for m in do_gov],
        medidas=[
            MedidaResumo(
                pasta=m.pasta, ministro=m.ministro, titulo=m.titulo,
                descricao=m.descricao, fonte_url=m.fonte_url,
            )
            for m in aprovadas
        ],
    )


def construir_payload_legislativo(conn, mandato) -> PayloadLegislativoMandato:
    from app.legislativo import (
        agregar_por_tema,
        agregar_por_tipo,
        agregar_vetos_por_tipo,
        leis_no_mandato,
        vetos_no_mandato,
    )

    leis = leis_no_mandato(conn, mandato)
    vetos = vetos_no_mandato(conn, mandato)
    return PayloadLegislativoMandato(
        mandato=mandato.nome,
        ano_inicio=mandato.inicio.year,
        ano_fim=mandato.fim.year,
        total_leis=len(leis),
        por_tipo=agregar_por_tipo(leis),
        por_tema=agregar_por_tema(conn, leis),
        total_vetos=len(vetos),
        vetos_por_tipo=agregar_vetos_por_tipo(vetos),
    )
