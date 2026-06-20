"""BCB/SGS REST adapter."""
from __future__ import annotations

import datetime

import httpx

from app.models import Indicador, Observacao

URL_BCB = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"


class BCBFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> list[Observacao]:
        resp = client.get(URL_BCB.format(codigo=ind.codigo_fonte), timeout=30)
        resp.raise_for_status()
        out: list[Observacao] = []
        for row in resp.json():
            data = datetime.datetime.strptime(row["data"], "%d/%m/%Y").date()
            out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["valor"])))
        return out
