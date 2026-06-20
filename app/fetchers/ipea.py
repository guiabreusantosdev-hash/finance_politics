"""IPEADATA OData v4 adapter."""
from __future__ import annotations

import datetime
from typing import Any

import httpx

from app.models import Indicador, Observacao

URL_IPEA = "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"


class IPEAFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> tuple[Any, list[Observacao]]:
        resp = client.get(URL_IPEA.format(codigo=ind.codigo_fonte), timeout=60)
        resp.raise_for_status()
        raw = resp.json()
        out: list[Observacao] = []
        for row in raw["value"]:
            if row.get("VALVALOR") is None:
                continue
            data = datetime.date.fromisoformat(row["VALDATA"][:10])
            out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["VALVALOR"])))
        return raw, out
