"""Tesouro Nacional CKAN/datalake adapter (generic referencia/valor shape)."""
from __future__ import annotations

import datetime
from typing import Any

import httpx

from app.models import Indicador, Observacao

URL_TESOURO = "https://apidatalake.tesouro.gov.br/ords/custom/{codigo}"


class TesouroFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> tuple[Any, list[Observacao]]:
        resp = client.get(URL_TESOURO.format(codigo=ind.codigo_fonte), timeout=60)
        resp.raise_for_status()
        raw = resp.json()
        out: list[Observacao] = []
        for row in raw["data"]:
            if row.get("valor") is None:
                continue
            data = datetime.date.fromisoformat(row["referencia"][:10])
            out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["valor"])))
        return raw, out
