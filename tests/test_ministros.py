import datetime

import pytest

from app.ministros import carregar_ministros, ministros_do_governo


def _escrever(tmp_path, ministros_yaml: str):
    mandatos = tmp_path / "mandatos.yaml"
    mandatos.write_text(
        "- nome: Lula 3\n  inicio: 2023-01-01\n  fim: 2026-12-31\n", encoding="utf-8"
    )
    ministros = tmp_path / "ministros.yaml"
    ministros.write_text(ministros_yaml, encoding="utf-8")
    return str(ministros), str(mandatos)


def test_carregar_ministros_ok(tmp_path):
    mp, mdp = _escrever(
        tmp_path,
        "- governo: Lula 3\n"
        "  ministros:\n"
        "    - pasta: Fazenda\n"
        "      nome: Fernando Haddad\n"
        "      inicio: 2023-01-01\n"
        "      fim: null\n"
        "      fonte: https://exemplo\n",
    )
    ms = carregar_ministros(mp, mdp)
    assert len(ms) == 1
    assert ms[0].nome == "Fernando Haddad"
    assert ms[0].pasta == "Fazenda"
    assert ms[0].fim is None
    assert ms[0].inicio == datetime.date(2023, 1, 1)


def test_carregar_ministros_rejeita_governo_desconhecido(tmp_path):
    mp, mdp = _escrever(
        tmp_path,
        "- governo: Governo Inexistente\n"
        "  ministros:\n"
        "    - pasta: Fazenda\n"
        "      nome: X\n"
        "      inicio: 2023-01-01\n"
        "      fim: null\n"
        "      fonte: https://exemplo\n",
    )
    with pytest.raises(ValueError, match="Governo Inexistente"):
        carregar_ministros(mp, mdp)


def test_ministros_do_governo_filtra():
    from app.models import Ministro

    a = Ministro(governo="Lula 3", pasta="Fazenda", nome="A",
                 inicio=datetime.date(2023, 1, 1), fim=None, fonte="x")
    b = Ministro(governo="Bolsonaro", pasta="Economia", nome="B",
                 inicio=datetime.date(2019, 1, 1), fim=None, fonte="x")
    assert ministros_do_governo([a, b], "Lula 3") == [a]
