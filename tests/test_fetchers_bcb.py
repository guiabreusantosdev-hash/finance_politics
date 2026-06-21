import datetime
import json
import pathlib

import httpx

from app.fetchers.bcb import BCBFetcher, INICIO_PADRAO, janelas
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
    raw, obs = BCBFetcher().fetch(_ind(), client)
    assert raw[0]["data"] == "01/01/2024"
    assert obs[0].data == datetime.date(2024, 1, 1)
    assert obs[0].valor == 11.75
    assert obs[1].valor == 11.25
    assert all(o.serie_id == "bcb_432_selic" for o in obs)


def test_janelas_fatia_em_blocos_de_10_anos():
    js = janelas(datetime.date(2003, 1, 1), datetime.date(2026, 1, 1))
    assert len(js) == 3
    assert js[0][0] == datetime.date(2003, 1, 1)
    assert js[0][1] == datetime.date(2012, 12, 31)
    assert js[1][0] == datetime.date(2013, 1, 1)
    assert js[-1][1] == datetime.date(2026, 1, 1)


def test_bcb_url_inclui_intervalo_de_datas():
    cap = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap.setdefault("urls", []).append(str(request.url))
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    BCBFetcher().fetch(_ind(), client)  # _ind() é mensal
    assert len(cap["urls"]) == 1
    assert "dataInicial=" in cap["urls"][0]
    assert "dataFinal=" in cap["urls"][0]


def test_bcb_serie_diaria_faz_varias_janelas_e_concatena():
    chamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(200, json=[{"data": "01/01/2024", "valor": "5.0"}])

    ind = Indicador(
        id="bcb_1_cambio", fonte="BCB", codigo_fonte="1", nome="Câmbio",
        unidade="R$/US$", periodicidade="diaria", eixo="macro",
        metodo_anual="fim_periodo",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    raw, obs = BCBFetcher().fetch(ind, client)
    esperado = len(janelas(INICIO_PADRAO, datetime.date.today()))
    assert chamadas["n"] == esperado
    assert chamadas["n"] >= 2          # 2003→hoje sempre dá ≥ 2 janelas
    assert len(obs) == esperado        # 1 obs por janela na fixture
