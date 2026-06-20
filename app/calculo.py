"""Deterministic indicator math. The LLM never runs anything here."""
from __future__ import annotations

from typing import Literal

from app.models import Indicador, Mandato, Observacao


def _do_ano(obs: list[Observacao], ano: int) -> list[Observacao]:
    return sorted((o for o in obs if o.data.year == ano), key=lambda o: o.data)


def valor_no_periodo(
    obs: list[Observacao], ind: Indicador, ano: int
) -> float | None:
    do_ano = _do_ano(obs, ano)
    if not do_ano:
        return None
    if ind.metodo_anual == "fim_periodo":
        return do_ano[-1].valor
    if ind.metodo_anual == "media":
        return sum(o.valor for o in do_ano) / len(do_ano)
    if ind.metodo_anual == "acumulado_12m":
        acc = 1.0
        for o in do_ano:
            acc *= 1 + o.valor / 100
        return (acc - 1) * 100
    return None


def variacao(de: float | None, ate: float | None) -> float | None:
    if de is None or ate is None or de == 0:
        return None
    return (ate - de) / de * 100


def valor_no_mandato(
    obs: list[Observacao],
    ind: Indicador,
    mandato: Mandato,
    ponta: Literal["inicio", "fim"],
) -> float | None:
    ano = mandato.inicio.year if ponta == "inicio" else mandato.fim.year
    return valor_no_periodo(obs, ind, ano)
