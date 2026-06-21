"""Tests for senado_vetos normalizar_vetos using frozen fixture."""
import datetime
import json
import pathlib

from app.fetchers.senado_vetos import normalizar_vetos

FIX = pathlib.Path("tests/fixtures/legislativo")


def test_normalizar_vetos_basic_invariants():
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    assert len(vetos) >= 1
    assert all(v.tipo in {"total", "parcial"} for v in vetos)
    assert all(v.id for v in vetos)


def test_normalizar_vetos_fixture_has_4_vetos():
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    assert len(vetos) == 4


def test_normalizar_vetos_all_parcial():
    """All 4 fixture vetos have Total='Não' → tipo must be 'parcial'."""
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    assert all(v.tipo == "parcial" for v in vetos)


def test_normalizar_vetos_known_id():
    """First veto in fixture has Codigo='16269' → id must be 'senado_16269'."""
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    ids = {v.id for v in vetos}
    assert "senado_16269" in ids


def test_normalizar_vetos_data_is_date():
    """Every veto must have a valid date object."""
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    for v in vetos:
        assert isinstance(v.data, datetime.date)
        # DataRecebimentoCongresso values in fixture are all in 2023 or 2024
        assert v.data.year in {2023, 2024}


def test_normalizar_vetos_materia_format():
    """materia field must be formatted as 'SIGLA NUMERO/ANO'."""
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    # First veto: MateriaVetada.Sigla=PL, Numero=3626, Ano=2023 → "PL 3626/2023"
    v_16269 = next(v for v in vetos if v.id == "senado_16269")
    assert v_16269.materia == "PL 3626/2023"


def test_normalizar_vetos_descricao_from_assunto():
    """descricao comes from Assunto field."""
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    v_16269 = next(v for v in vetos if v.id == "senado_16269")
    assert v_16269.descricao == "Apostas de quota fixa"


def test_normalizar_vetos_url_from_materia():
    """url comes from Materia.UrlMovimentacoes."""
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    v_16269 = next(v for v in vetos if v.id == "senado_16269")
    assert v_16269.url == "https://legis.senado.leg.br/dadosabertos/materia/movimentacoes/161861"


def test_normalizar_vetos_skips_entries_with_no_date():
    """A veto with both DataRecebimentoCongresso and DataPublicacao absent must be skipped."""
    raw = {
        "ListaVetosAnoCN": {
            "Vetos": {
                "Veto": [
                    {
                        "Codigo": "99001",
                        # no DataRecebimentoCongresso, no DataPublicacao
                        "Total": "Não",
                        "Assunto": "Sem data",
                    },
                    {
                        "Codigo": "99002",
                        "DataRecebimentoCongresso": "2023-05-10",
                        "Total": "Sim",
                        "Assunto": "Com data",
                    },
                ]
            }
        }
    }
    vetos = normalizar_vetos(raw)
    ids = {v.id for v in vetos}
    assert "senado_99001" not in ids, "veto sem data não deve ser incluído"
    assert "senado_99002" in ids, "veto com data deve ser incluído"
