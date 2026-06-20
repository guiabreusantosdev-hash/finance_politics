import datetime

from app.db import conectar, criar_schema, upsert_observacoes, upsert_serie
from app.models import Indicador, Mandato, Observacao
from app.payload import construir_payload_ano, construir_payload_comparacao, construir_payload_mandato


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


# --- I3: construir_payload_mandato ---

def _mandato_dilma1() -> Mandato:
    return Mandato(
        nome="Dilma 1",
        inicio=datetime.date(2011, 1, 1),
        fim=datetime.date(2014, 12, 31),
    )


def test_payload_mandato_com_dados():
    """Mandate with data at both endpoints yields valores and variacao."""
    conn = _conn_com_dados()
    # _conn_com_dados has data for 2014 (11.75) but not 2011;
    # use a mandate whose endpoints have data.
    mandato = Mandato(
        nome="Dilma 1",
        inicio=datetime.date(2014, 1, 1),
        fim=datetime.date(2018, 12, 31),
    )
    p = construir_payload_mandato(conn, [_ind()], mandato)
    assert p.mandato == "Dilma 1"
    assert p.ano_inicio == 2014
    assert p.ano_fim == 2018
    ind_val = p.indicadores[0]
    assert ind_val.nome == "Meta Selic"
    assert ind_val.valor_inicio == 11.75
    assert ind_val.valor_fim == 6.5
    assert ind_val.variacao is not None
    # variacao = (6.5 - 11.75) / 11.75 * 100
    assert abs(ind_val.variacao - (-44.680851063829795)) < 1e-6
    assert "Meta Selic" not in p.faltantes


def test_payload_mandato_sem_dados_marca_faltante():
    """Mandate with no data at either endpoint adds nome to faltantes."""
    conn = _conn_com_dados()
    mandato = Mandato(
        nome="Futuro",
        inicio=datetime.date(2050, 1, 1),
        fim=datetime.date(2054, 12, 31),
    )
    p = construir_payload_mandato(conn, [_ind()], mandato)
    assert "Meta Selic" in p.faltantes
    ind_val = p.indicadores[0]
    assert ind_val.valor_inicio is None
    assert ind_val.valor_fim is None
    assert ind_val.variacao is None
