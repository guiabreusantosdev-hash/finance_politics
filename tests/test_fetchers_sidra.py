import datetime
import json
import pathlib

import httpx

from app.fetchers.sidra import SIDRAFetcher
from app.models import Indicador

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "sidra_6468.json").read_text())


def _ind() -> Indicador:
    return Indicador(
        id="sidra_6468_desemprego", fonte="IBGE", codigo_fonte="6468",
        nome="Taxa de desocupação", unidade="%", periodicidade="trimestral",
        eixo="macro", metodo_anual="media",
    )


def test_sidra_skips_header_and_parses_quarter():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    raw, obs = SIDRAFetcher().fetch(_ind(), client)
    assert raw[0]["D2C"] == "Trimestre"  # header row still present in raw
    assert len(obs) == 2  # header row skipped
    assert obs[0].data == datetime.date(2024, 1, 1)   # 2024 Q1 -> Jan
    assert obs[0].valor == 7.9
    assert obs[1].data == datetime.date(2024, 4, 1)   # 2024 Q2 -> Apr
