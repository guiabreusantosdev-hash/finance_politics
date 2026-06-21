"""IBGE/SIDRA aggregate-table adapter (quarterly headline series)."""
from __future__ import annotations

import datetime
from typing import Any

import httpx

from app.models import Indicador, Observacao

URL_SIDRA = (
    "https://apisidra.ibge.gov.br/values/t/{tabela}/n1/all/v/{variavel}/p/all{classif}?"
    "formato=json"
)


def _periodo_para_data(p: str) -> datetime.date:
    ano = int(p[:4])
    if len(p) == 6:  # YYYYNN quarter or month code
        nn = int(p[4:])
        mes = (nn - 1) * 3 + 1 if nn <= 4 else nn  # treat as quarter
        return datetime.date(ano, mes, 1)
    return datetime.date(ano, 1, 1)


class SIDRAFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> tuple[Any, list[Observacao]]:
        variavel = ind.variavel or "allxp"
        classif = f"/{ind.classificacao}" if ind.classificacao else ""
        url = URL_SIDRA.format(
            tabela=ind.codigo_fonte, variavel=variavel, classif=classif
        )
        resp = client.get(url, timeout=60)
        resp.raise_for_status()
        raw = resp.json()
        out: list[Observacao] = []
        for row in raw[1:]:  # first row is the header / labels
            try:
                valor = float(row["V"])
            except (TypeError, ValueError):
                continue  # "..." / "-" -> missing, skip
            out.append(
                Observacao(
                    serie_id=ind.id,
                    data=_periodo_para_data(row["D2C"]),
                    valor=valor,
                )
            )
        return raw, out
