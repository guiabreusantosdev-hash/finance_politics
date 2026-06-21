"""BCB/SGS REST adapter."""
from __future__ import annotations

import datetime
from typing import Any

import httpx

from app.models import Indicador, Observacao

URL_BCB = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    "?formato=json&dataInicial={di}&dataFinal={df}"
)
INICIO_PADRAO = datetime.date(2003, 1, 1)


def janelas(
    inicio: datetime.date, fim: datetime.date, max_anos: int = 10
) -> list[tuple[datetime.date, datetime.date]]:
    out: list[tuple[datetime.date, datetime.date]] = []
    ini = inicio
    while ini <= fim:
        try:
            prox = ini.replace(year=ini.year + max_anos)
        except ValueError:  # 29/02 em ano não bissexto
            prox = ini.replace(year=ini.year + max_anos, day=28)
        fim_janela = min(fim, prox - datetime.timedelta(days=1))
        out.append((ini, fim_janela))
        ini = fim_janela + datetime.timedelta(days=1)
    return out


class BCBFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> tuple[Any, list[Observacao]]:
        fim = datetime.date.today()
        if ind.periodicidade == "diaria":
            blocos = janelas(INICIO_PADRAO, fim)
        else:
            blocos = [(INICIO_PADRAO, fim)]
        raw_total: list[Any] = []
        out: list[Observacao] = []
        for di, df in blocos:
            url = URL_BCB.format(
                codigo=ind.codigo_fonte,
                di=di.strftime("%d/%m/%Y"),
                df=df.strftime("%d/%m/%Y"),
            )
            resp = client.get(url, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            raw_total.extend(raw)
            for row in raw:
                data = datetime.datetime.strptime(row["data"], "%d/%m/%Y").date()
                out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["valor"])))
        return raw_total, out
