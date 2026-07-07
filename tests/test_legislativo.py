import datetime

from app.db import conectar, criar_schema, upsert_lei_temas, upsert_leis, upsert_vetos
from app.legislativo import (
    agregar_por_tema,
    agregar_por_tipo,
    agregar_vetos_por_tipo,
    filtrar_leis,
    leis_no_mandato,
    vetos_no_mandato,
)
from app.models import Lei, Mandato, Veto


def _mandato() -> Mandato:
    return Mandato(nome="Lula 3", inicio=datetime.date(2023, 1, 1), fim=datetime.date(2026, 12, 31))


def test_atribuicao_por_data_e_agregacoes():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [
        Lei(id="a", tipo="LO", numero="1", ano=2023, data=datetime.date(2023, 1, 1),
            ementa="e", url="u"),                                     # borda inicial: dentro
        Lei(id="b", tipo="MP", numero="2", ano=2024, data=datetime.date(2024, 5, 1),
            ementa="e", url="u"),
        Lei(id="c", tipo="LO", numero="3", ano=2022, data=datetime.date(2022, 12, 31),
            ementa="e", url="u"),                                     # fora (mandato anterior)
    ])
    upsert_lei_temas(conn, "a", ["Saúde"])
    upsert_lei_temas(conn, "b", ["Saúde", "Economia"])
    upsert_vetos(conn, [
        Veto(id="v1", data=datetime.date(2023, 3, 1), tipo="parcial",
             descricao="d", materia="m", url="u"),
    ])
    m = _mandato()
    leis = leis_no_mandato(conn, m)
    assert {x.id for x in leis} == {"a", "b"}
    assert agregar_por_tipo(leis) == {"LO": 1, "MP": 1}
    assert agregar_por_tema(conn, leis) == {"Saúde": 2, "Economia": 1}
    assert agregar_vetos_por_tipo(vetos_no_mandato(conn, m)) == {"parcial": 1}


def _leis():
    return [
        Lei(id="a", tipo="LO", numero="1", ano=2023, data=datetime.date(2023, 1, 1), ementa="e", url="u"),
        Lei(id="b", tipo="MP", numero="2", ano=2023, data=datetime.date(2023, 2, 1), ementa="e", url="u"),
        Lei(id="c", tipo="EC", numero="3", ano=2023, data=datetime.date(2023, 3, 1), ementa="e", url="u"),
    ]


_TEMAS = {"a": ["Saúde"], "b": ["Trabalho e Emprego", "Economia"], "c": []}


def test_filtrar_leis_sem_filtros_retorna_tudo():
    assert len(filtrar_leis(_leis(), _TEMAS, [], [])) == 3


def test_filtrar_leis_por_tipo():
    r = filtrar_leis(_leis(), _TEMAS, ["LO", "EC"], [])
    assert [x.id for x in r] == ["a", "c"]


def test_filtrar_leis_por_tema():
    r = filtrar_leis(_leis(), _TEMAS, [], ["Saúde"])
    assert [x.id for x in r] == ["a"]


def test_filtrar_leis_tipo_e_tema_intersecao():
    r = filtrar_leis(_leis(), _TEMAS, ["MP"], ["Economia"])
    assert [x.id for x in r] == ["b"]


def test_filtrar_leis_tema_sem_correspondencia_exclui_lei_sem_temas():
    r = filtrar_leis(_leis(), _TEMAS, [], ["Saúde"])
    assert all(x.id != "c" for x in r)
