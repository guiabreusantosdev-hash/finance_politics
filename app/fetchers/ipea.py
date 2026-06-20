"""IPEADATA OData v4 adapter."""
from __future__ import annotations

import datetime

import httpx

from app.models import Indicador, Observacao

URL_IPEA = "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"


class IPEAFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> list[Observacao]:
        resp = client.get(URL_IPEA.format(codigo=ind.codigo_fonte), timeout=60)
        resp.raise_for_status()
        out: list[Observacao] = []
        for row in resp.json()["value"]:
            if row.get("VALVALOR") is None:
                continue
            data = datetime.date.fromisoformat(row["VALDATA"][:10])
            out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["VALVALOR"])))
        return out
