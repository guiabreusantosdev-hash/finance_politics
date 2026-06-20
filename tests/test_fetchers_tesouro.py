import datetime
import json
import pathlib

import httpx

from app.fetchers.tesouro import TesouroFetcher
from app.models import Indicador

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "tesouro_sample.json").read_text())


def _ind() -> Indicador:
    return Indicador(
        id="tesouro_dpf", fonte="TESOURO", codigo_fonte="dpf", nome="DPF",
        unidade="% do PIB", periodicidade="mensal", eixo="fiscal", metodo_anual="fim_periodo",
    )


def test_tesouro_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    obs = TesouroFetcher().fetch(_ind(), client)
    assert obs[0].data == datetime.date(2023, 12, 1)
    assert obs[1].valor == 76.1
