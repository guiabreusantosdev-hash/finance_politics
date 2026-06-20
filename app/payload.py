"""Build structured payloads the LLM will narrate (never compute)."""
from __future__ import annotations

import datetime

from app.calculo import valor_no_mandato, valor_no_periodo
from app.db import observacoes_da_serie
from app.models import (
    DeltaIndicador,
    Indicador,
    Mandato,
    PayloadAno,
    PayloadComparacao,
    ValorIndicador,
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
