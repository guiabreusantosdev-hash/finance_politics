import datetime

from app.db import (
    conectar,
    criar_schema,
    observacoes_da_serie,
    upsert_observacoes,
    upsert_serie,
)
from app.models import Indicador, Observacao


def _ind() -> Indicador:
    return Indicador(
        id="bcb_432_selic",
        fonte="BCB",
        codigo_fonte="432",
        nome="Meta Selic",
        unidade="% a.a.",
        periodicidade="mensal",
        eixo="macro",
        metodo_anual="fim_periodo",
    )


def test_upsert_is_idempotent():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_serie(conn, _ind())
    obs = [
        Observacao(
            serie_id="bcb_432_selic", data=datetime.date(2024, 1, 1), valor=11.75
        )
    ]
    upsert_observacoes(conn, obs)
    upsert_observacoes(conn, obs)  # second time must not duplicate
    stored = observacoes_da_serie(conn, "bcb_432_selic")
    assert len(stored) == 1
    assert stored[0].valor == 11.75


def test_upsert_updates_value():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_serie(conn, _ind())
    d = datetime.date(2024, 1, 1)
    upsert_observacoes(
        conn, [Observacao(serie_id="bcb_432_selic", data=d, valor=10.0)]
    )
    upsert_observacoes(
        conn, [Observacao(serie_id="bcb_432_selic", data=d, valor=11.0)]
    )
    stored = observacoes_da_serie(conn, "bcb_432_selic")
    assert len(stored) == 1
    assert stored[0].valor == 11.0
