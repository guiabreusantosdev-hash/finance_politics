import datetime

from app.db import conectar, criar_schema, upsert_observacoes, upsert_serie
from app.models import Indicador, Mandato, Observacao
from app.payload import construir_payload_ano, construir_payload_comparacao


def _ind() -> Indicador:
    return Indicador(
        id="bcb_432_selic", fonte="BCB", codigo_fonte="432", nome="Meta Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )


def _conn_com_dados():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_serie(conn, _ind())
    upsert_observacoes(conn, [
        Observacao(serie_id="bcb_432_selic", data=datetime.date(2014, 12, 1), valor=11.75),
        Observacao(serie_id="bcb_432_selic", data=datetime.date(2018, 12, 1), valor=6.5),
    ])
    return conn


def test_payload_ano_marca_faltante():
    conn = _conn_com_dados()
    p = construir_payload_ano(conn, [_ind()], 2014)
    assert p.indicadores[0].valor == 11.75
    assert p.indicadores[0].fonte == "BCB"
    p_vazio = construir_payload_ano(conn, [_ind()], 2099)
    assert "Meta Selic" in p_vazio.faltantes


def test_payload_comparacao_calcula_delta():
    conn = _conn_com_dados()
    a = Mandato(nome="Dilma 1", inicio=datetime.date(2011, 1, 1), fim=datetime.date(2014, 12, 31))
    b = Mandato(nome="Dilma/Temer", inicio=datetime.date(2015, 1, 1), fim=datetime.date(2018, 12, 31))
    p = construir_payload_comparacao(conn, [_ind()], a, b)
    d = p.deltas[0]
    assert d.valor_a == 11.75
    assert d.valor_b == 6.5
    assert d.delta is not None
    assert abs(d.delta - (-5.25)) < 1e-9
