import datetime
import datetime as _dt

from app.db import conectar, criar_schema, salvar_medida, upsert_observacoes, upsert_serie
from app.models import Indicador, Mandato, Medida, Ministro, Observacao, PayloadAno, PayloadComparacao, PayloadMandato, PayloadMinisterialGoverno
from app.payload import (
    construir_payload_ano,
    construir_payload_comparacao,
    construir_payload_mandato,
    construir_payload_ministerial,
    descrever_payload,
    hash_payload,
)


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


def _payload_ano(ano: int = 2024) -> PayloadAno:
    return PayloadAno(ano=ano, indicadores=[], faltantes=[])


def test_hash_payload_deterministico():
    p = _payload_ano()
    assert hash_payload(p) == hash_payload(_payload_ano())


def test_hash_payload_muda_com_os_dados():
    assert hash_payload(_payload_ano(2024)) != hash_payload(_payload_ano(2023))


def test_descrever_payload_ano():
    assert descrever_payload(_payload_ano(2024)) == ("ano", "2024")


def test_descrever_payload_mandato():
    p = PayloadMandato(
        mandato="Lula 3", ano_inicio=2023, ano_fim=2026, indicadores=[], faltantes=[]
    )
    assert descrever_payload(p) == ("mandato", "Lula 3")


def test_descrever_payload_comparacao():
    p = PayloadComparacao(
        mandato_a="Lula 3", mandato_b="Bolsonaro",
        ano_inicio_a=2023, ano_fim_a=2026, ano_inicio_b=2019, ano_fim_b=2022,
        deltas=[],
    )
    assert descrever_payload(p) == ("comparacao", "Lula 3 × Bolsonaro")


def _mandato_lula3() -> Mandato:
    return Mandato(nome="Lula 3", inicio=_dt.date(2023, 1, 1), fim=_dt.date(2026, 12, 31))


def _ministro_haddad() -> Ministro:
    return Ministro(governo="Lula 3", pasta="Fazenda", nome="Haddad",
                    inicio=_dt.date(2023, 1, 1), fim=None, fonte="x")


def test_payload_ministerial_so_aprovadas():
    conn = conectar(":memory:")
    criar_schema(conn)
    salvar_medida(conn, Medida(governo="Lula 3", pasta="Fazenda", ministro="Haddad",
                               titulo="aprov", descricao="d", fonte_url="https://a",
                               status="aprovada", origem="curada"))
    salvar_medida(conn, Medida(governo="Lula 3", pasta="Fazenda", ministro="Haddad",
                               titulo="rasc", descricao="d", fonte_url="https://b",
                               status="rascunho", origem="ia"))
    payload = construir_payload_ministerial(conn, [_ministro_haddad()], _mandato_lula3())
    assert isinstance(payload, PayloadMinisterialGoverno)
    assert payload.governo == "Lula 3"
    assert payload.ano_inicio == 2023 and payload.ano_fim == 2026
    assert payload.ministros == ["Fazenda — Haddad"]
    assert [m.titulo for m in payload.medidas] == ["aprov"]


def test_descrever_payload_ministerial():
    from app.models import PayloadMinisterialGoverno
    from app.payload import descrever_payload

    p = PayloadMinisterialGoverno(governo="Lula 3", ano_inicio=2023, ano_fim=2026,
                                  ministros=[], medidas=[])
    assert descrever_payload(p) == ("ministerial", "Lula 3")


def test_payload_legislativo_e_descricao():
    import datetime as d

    from app.db import conectar, criar_schema, upsert_lei_temas, upsert_leis, upsert_vetos
    from app.models import Lei, Mandato, PayloadLegislativoMandato, Veto
    from app.payload import construir_payload_legislativo, descrever_payload

    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [Lei(id="a", tipo="LO", numero="1", ano=2023,
                           data=d.date(2023, 2, 1), ementa="e", url="u")])
    upsert_lei_temas(conn, "a", ["Saúde"])
    upsert_vetos(conn, [Veto(id="v", data=d.date(2023, 3, 1), tipo="total",
                             descricao="x", materia="m", url="u")])
    m = Mandato(nome="Lula 3", inicio=d.date(2023, 1, 1), fim=d.date(2026, 12, 31))
    p = construir_payload_legislativo(conn, m)
    assert isinstance(p, PayloadLegislativoMandato)
    assert p.total_leis == 1 and p.por_tipo == {"LO": 1}
    assert p.por_tema == {"Saúde": 1}
    assert p.total_vetos == 1 and p.vetos_por_tipo == {"total": 1}
    assert descrever_payload(p) == ("legislativo", "Lula 3")
