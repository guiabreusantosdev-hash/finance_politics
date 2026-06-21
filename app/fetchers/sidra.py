"""IBGE/SIDRA aggregate-table adapter (quarterly headline series)."""
from __future__ import annotations

import datetime
import re
from typing import Any

import httpx

from app.models import Indicador, Observacao

URL_SIDRA = (
    "https://apisidra.ibge.gov.br/values/t/{tabela}/n1/all/v/{variavel}/p/all{classif}?formato=json"
)

_ROTULOS_PERIODO = ("Trimestre", "Ano", "Mês", "Semestre", "Período")


def _periodo_para_data(p: str) -> datetime.date:
    ano = int(p[:4])
    if len(p) == 6:  # YYYYNN quarter or month code
        nn = int(p[4:])
        mes = (nn - 1) * 3 + 1 if nn <= 4 else nn  # treat as quarter
        return datetime.date(ano, mes, 1)
    return datetime.date(ano, 1, 1)


def _coluna_periodo(header: dict) -> str:
    """Find the response column holding the period code, via its header label.

    SIDRA numbers dimensions (D1C, D2C, ...) and their position shifts with the
    query (variable in path, classifications), so the period column cannot be
    hardcoded. The header row labels each column; the period one is labelled
    'Ano', 'Trimestre', 'Mês', etc.
    """
    for chave, rotulo in header.items():
        if (
            chave.startswith("D")
            and chave.endswith("C")
            and any(re.search(rf"\b{r}\b", rotulo) for r in _ROTULOS_PERIODO)
        ):
            return chave
    raise ValueError(f"coluna de período não encontrada no cabeçalho SIDRA: {header}")


class SIDRAFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> tuple[Any, list[Observacao]]:
        variavel = ind.variavel or "allxp"
        classif = f"/{ind.classificacao}" if ind.classificacao else ""
        url = URL_SIDRA.format(tabela=ind.codigo_fonte, variavel=variavel, classif=classif)
        resp = client.get(url, timeout=60)
        resp.raise_for_status()
        raw = resp.json()
        col = _coluna_periodo(raw[0])
        out: list[Observacao] = []
        for row in raw[1:]:
            try:
                valor = float(row["V"])
            except (TypeError, ValueError):
                continue  # "..." / "-" -> missing, skip
            out.append(
                Observacao(
                    serie_id=ind.id,
                    data=_periodo_para_data(row[col]),
                    valor=valor,
                )
            )
        return raw, out
