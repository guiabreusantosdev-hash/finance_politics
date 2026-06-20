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
    raw, obs = TesouroFetcher().fetch(_ind(), client)
    assert "data" in raw  # API envelope preserved
    assert obs[0].data == datetime.date(2023, 12, 1)
    assert obs[1].valor == 76.1


# --- I4: null valor in a row must be skipped (no TypeError from float(None)) ---

FIXTURE_WITH_NULL = {
    "data": [
        {"referencia": "2023-12-01", "valor": 74.3},
        {"referencia": "2024-06-01", "valor": None},   # null row — must be skipped
        {"referencia": "2024-12-01", "valor": 76.1},
    ]
}


def test_tesouro_skips_null_valor():
    """Rows where valor is None must be skipped without raising TypeError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE_WITH_NULL)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    raw, obs = TesouroFetcher().fetch(_ind(), client)
    # Only 2 rows should be returned (the null row is skipped)
    assert len(obs) == 2
    dates = [o.data for o in obs]
    assert datetime.date(2024, 6, 1) not in dates
