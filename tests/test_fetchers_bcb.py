import datetime
import json
import pathlib

import httpx

from app.fetchers.bcb import BCBFetcher
from app.models import Indicador

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "bcb_432.json").read_text())


def _ind() -> Indicador:
    return Indicador(
        id="bcb_432_selic", fonte="BCB", codigo_fonte="432", nome="Meta Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )


def test_bcb_parses_brazilian_dates_and_floats():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    obs = BCBFetcher().fetch(_ind(), client)
    assert obs[0].data == datetime.date(2024, 1, 1)
    assert obs[0].valor == 11.75
    assert obs[1].valor == 11.25
    assert all(o.serie_id == "bcb_432_selic" for o in obs)
