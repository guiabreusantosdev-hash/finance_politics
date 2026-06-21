import datetime

from app.db import conectar, criar_schema, upsert_lei_temas, upsert_leis, upsert_vetos
from app.legislativo import (
    agregar_por_tema,
    agregar_por_tipo,
    agregar_vetos_por_tipo,
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
