import datetime
import json
import pathlib

import httpx

from app.fetchers.ipea import IPEAFetcher
from app.models import Indicador

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "ipea_gini.json").read_text())


def _ind() -> Indicador:
    return Indicador(
        id="ipea_gini", fonte="IPEA", codigo_fonte="GINI", nome="Índice de Gini",
        unidade="índice", periodicidade="anual", eixo="social", metodo_anual="fim_periodo",
    )


def test_ipea_odata_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    obs = IPEAFetcher().fetch(_ind(), client)
    assert obs[0].data == datetime.date(2014, 1, 1)
    assert obs[0].valor == 0.518
    assert obs[1].valor == 0.524
