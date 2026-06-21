"""Tests for app/fetchers/camara.py — pure normalizar_leis function only."""
import json
import pathlib

import pytest

from app.fetchers.camara import normalizar_leis

FIX = pathlib.Path("tests/fixtures/legislativo")


@pytest.fixture()
def fixture_data():
    prop = json.loads((FIX / "camara_proposicoes_2023.json").read_text(encoding="utf-8"))
    temas = json.loads((FIX / "camara_temas_2023.json").read_text(encoding="utf-8"))
    return prop, temas


def test_normalizar_leis_filtra_e_mapeia(fixture_data):
    """Invariants: every lei has mapped tipo and camara_ prefix; non-transformed excluded."""
    prop, temas = fixture_data
    leis, temas_por_lei = normalizar_leis(prop, temas)

    # All returned leis must have a mapped tipo
    assert all(x.tipo in {"LO", "LC", "MP", "EC"} for x in leis)
    # All ids must be prefixed
    assert all(x.id.startswith("camara_") for x in leis)
    # At least one lei must be returned
    assert len(leis) >= 1
    # temas_por_lei keys must all reference returned lei ids
    ids = {x.id for x in leis}
    assert set(temas_por_lei).issubset(ids)


def test_normalizar_leis_conta_exata(fixture_data):
    """Fixture has 4 leis with mapped tipos: 1 PL→LO, 1 MPV→MP, 1 PEC→EC, 1 PLP→LC."""
    prop, temas = fixture_data
    leis, _ = normalizar_leis(prop, temas)

    assert len(leis) == 4
    tipos = {x.tipo for x in leis}
    assert tipos == {"LO", "MP", "EC", "LC"}


def test_normalizar_leis_exclui_nao_mapeados(fixture_data):
    """PDL, PRC, PLV, REQ, PLN must be discarded even when transformed."""
    prop, temas = fixture_data
    leis, _ = normalizar_leis(prop, temas)

    ids = {x.id for x in leis}
    # Non-mapped transformed types
    for excluded_camara_id in ["camara_2345508", "camara_2345652", "camara_2349774",
                                "camara_2351066", "camara_2354717"]:
        assert excluded_camara_id not in ids


def test_normalizar_leis_exclui_nao_transformadas(fixture_data):
    """PLs with non-transformed status must not appear."""
    prop, temas = fixture_data
    leis, _ = normalizar_leis(prop, temas)

    ids = {x.id for x in leis}
    assert "camara_369205" not in ids
    assert "camara_618609" not in ids


def test_normalizar_leis_temas_corretos(fixture_data):
    """Temas must only appear for the 4 kept leis; check specific tema assignments."""
    prop, temas = fixture_data
    _, temas_por_lei = normalizar_leis(prop, temas)

    # PL 1197773 has 1 tema
    assert "camara_1197773" in temas_por_lei
    assert "Direito Penal e Processual Penal" in temas_por_lei["camara_1197773"]

    # MPV 2349947 has 2 temas
    assert "camara_2349947" in temas_por_lei
    assert set(temas_por_lei["camara_2349947"]) == {
        "Direitos Humanos e Minorias",
        "Previdência e Assistência Social",
    }

    # PEC 2352476 has 3 temas
    assert "camara_2352476" in temas_por_lei
    assert set(temas_por_lei["camara_2352476"]) == {
        "Direitos Humanos e Minorias",
        "Finanças Públicas e Orçamento",
        "Política, Partidos e Eleições",
    }

    # PLP 2357053 has 1 tema
    assert "camara_2357053" in temas_por_lei
    assert temas_por_lei["camara_2357053"] == ["Finanças Públicas e Orçamento"]

    # Non-mapped types (PDL 2345508) must not appear in temas_por_lei
    assert "camara_2345508" not in temas_por_lei


def test_normalizar_leis_usa_campo_data_correto(fixture_data):
    """Status date comes from ultimoStatus['data'], not 'dataHora'."""
    prop, temas = fixture_data
    leis, _ = normalizar_leis(prop, temas)

    # PL 1197773 has ultimoStatus.data = "2025-05-06T00:00:00"
    pl_lei = next(x for x in leis if x.id == "camara_1197773")
    import datetime
    assert pl_lei.data == datetime.date(2025, 5, 6)
