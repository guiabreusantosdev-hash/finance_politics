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


GINI_FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "sidra_7435_gini.json").read_text())

def test_sidra_le_periodo_da_coluna_certa_quando_ha_variavel():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=GINI_FIXTURE)
    ind = Indicador(
        id="ibge_gini", fonte="IBGE", codigo_fonte="7435", nome="Gini",
        unidade="índice", periodicidade="anual", eixo="social",
        metodo_anual="fim_periodo", variavel="10681",
    )
    raw, obs = SIDRAFetcher().fetch(ind, httpx.Client(transport=httpx.MockTransport(handler)))
    assert [o.data for o in obs] == [datetime.date(2012, 1, 1), datetime.date(2013, 1, 1)]
    assert obs[0].valor == 0.540


def test_sidra_mesorregia_nao_confundida_com_periodo():
    """A 'Mesorregião (Código)' column placed BEFORE 'Ano (Código)' must NOT be
    picked as the period column. The bare substring 'Mes' used to match it; the
    word-boundary regex must NOT match."""
    _MESO_FIXTURE = [
        # header row: D1C=Mesorregião, D2C=Variável, D3C=Ano
        {"D1C": "Mesorregião (Código)", "D2C": "Variável (Código)", "D3C": "Ano (Código)", "V": "V"},
        # data row: mesoregion code=3101, variable code=99, year=2020
        {"D1C": "3101", "D2C": "99", "D3C": "2020", "V": "0.5"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_MESO_FIXTURE)

    ind = Indicador(
        id="ibge_meso_test", fonte="IBGE", codigo_fonte="9999", nome="Teste Mesorregião",
        unidade="índice", periodicidade="anual", eixo="macro", metodo_anual="fim_periodo",
    )
    raw, obs = SIDRAFetcher().fetch(ind, httpx.Client(transport=httpx.MockTransport(handler)))
    # Must resolve to Ano column (D3C="2020"), NOT the mesoregion code (D1C="3101")
    assert len(obs) == 1
    assert obs[0].data == datetime.date(2020, 1, 1)
