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


def _captura_url():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        return httpx.Response(200, json=FIXTURE)

    return capturado, httpx.MockTransport(handler)


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


def test_sidra_usa_variavel_quando_presente():
    cap, transport = _captura_url()
    ind = Indicador(
        id="ibge_pib", fonte="IBGE", codigo_fonte="6784", nome="PIB",
        unidade="%", periodicidade="anual", eixo="macro",
        metodo_anual="fim_periodo", variavel="9808",
    )
    SIDRAFetcher().fetch(ind, httpx.Client(transport=transport))
    assert "/v/9808/" in cap["url"]
    assert "allxp" not in cap["url"]


def test_sidra_injeta_classificacao_quando_presente():
    cap, transport = _captura_url()
    ind = Indicador(
        id="ibge_gini", fonte="IBGE", codigo_fonte="7435", nome="Gini",
        unidade="índice", periodicidade="anual", eixo="social",
        metodo_anual="fim_periodo", variavel="10681", classificacao="c11255/90707",
    )
    SIDRAFetcher().fetch(ind, httpx.Client(transport=transport))
    assert "/v/10681/" in cap["url"]
    assert "/c11255/90707" in cap["url"]


def test_sidra_mantem_allxp_sem_variavel():
    cap, transport = _captura_url()
    SIDRAFetcher().fetch(_ind(), httpx.Client(transport=transport))
    assert "/v/allxp/" in cap["url"]
