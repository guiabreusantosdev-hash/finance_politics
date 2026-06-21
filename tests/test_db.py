import datetime
import datetime as _dt

from app.db import (
    aprovar_medida,
    buscar_resumo_cache,
    conectar,
    criar_schema,
    descartar_medida,
    editar_medida,
    historico_resumos,
    leis_entre,
    medidas_do_governo,
    observacoes_da_serie,
    salvar_medida,
    salvar_resumo,
    temas_de,
    upsert_lei_temas,
    upsert_leis,
    upsert_observacoes,
    upsert_serie,
    upsert_vetos,
    vetos_entre,
)
from app.models import Indicador, Lei, Medida, Observacao, PayloadAno, ResumoFactual, Veto
from app.payload import hash_payload


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


def _payload(ano: int = 2024) -> PayloadAno:
    return PayloadAno(ano=ano, indicadores=[], faltantes=[])


def _resumo(txt: str = "x") -> ResumoFactual:
    return ResumoFactual(paragrafos_por_eixo={"macro": txt}, afirmacoes=[])


def test_salvar_e_buscar_cache_roundtrip():
    conn = conectar(":memory:")
    criar_schema(conn)
    p = _payload()
    rid = salvar_resumo(
        conn, payload=p, resumo=_resumo("v1"), veredito=None,
        modelo="claude-code-default", criado_em="2026-06-21T10:00:00",
    )
    assert isinstance(rid, int)
    reg = buscar_resumo_cache(conn, hash_payload(p))
    assert reg is not None
    assert reg.resumo.paragrafos_por_eixo["macro"] == "v1"
    assert reg.veredito is None
    assert reg.tipo == "ano" and reg.identificador == "2024"


def test_buscar_cache_retorna_o_mais_recente():
    conn = conectar(":memory:")
    criar_schema(conn)
    p = _payload()
    salvar_resumo(conn, payload=p, resumo=_resumo("v1"), veredito=None,
                  modelo="m", criado_em="2026-06-21T10:00:00")
    salvar_resumo(conn, payload=p, resumo=_resumo("v2"), veredito=None,
                  modelo="m", criado_em="2026-06-21T11:00:00")
    reg = buscar_resumo_cache(conn, hash_payload(p))
    assert reg is not None
    assert reg.resumo.paragrafos_por_eixo["macro"] == "v2"


def test_buscar_cache_miss_retorna_none():
    conn = conectar(":memory:")
    criar_schema(conn)
    assert buscar_resumo_cache(conn, "inexistente") is None


def test_historico_ordena_e_filtra():
    conn = conectar(":memory:")
    criar_schema(conn)
    p2024, p2023 = _payload(2024), _payload(2023)
    salvar_resumo(conn, payload=p2024, resumo=_resumo("a"), veredito=None,
                  modelo="m", criado_em="2026-06-21T10:00:00")
    salvar_resumo(conn, payload=p2024, resumo=_resumo("b"), veredito=None,
                  modelo="m", criado_em="2026-06-21T11:00:00")
    salvar_resumo(conn, payload=p2023, resumo=_resumo("c"), veredito=None,
                  modelo="m", criado_em="2026-06-21T12:00:00")
    hist = historico_resumos(conn, "ano", "2024")
    assert [r.resumo.paragrafos_por_eixo["macro"] for r in hist] == ["b", "a"]


def test_salvar_resumo_persiste_veredito_dict():
    conn = conectar(":memory:")
    criar_schema(conn)
    p = _payload()

    class _Vd:
        def model_dump_json(self) -> str:
            return '{"ancorado": true, "neutro": true, "numeros_fora_do_payload": [], "observacoes": "ok"}'

    salvar_resumo(conn, payload=p, resumo=_resumo(), veredito=_Vd(),
                  modelo="m", criado_em="2026-06-21T10:00:00")
    reg = buscar_resumo_cache(conn, hash_payload(p))
    assert reg is not None
    assert reg.veredito == {
        "ancorado": True, "neutro": True,
        "numeros_fora_do_payload": [], "observacoes": "ok",
    }


def _medida(status="rascunho", origem="curada", titulo="t") -> Medida:
    return Medida(
        governo="Lula 3", pasta="Fazenda", ministro="Haddad",
        titulo=titulo, descricao="d", fonte_url="https://x",
        status=status, origem=origem,
    )


def test_salvar_e_listar_medida():
    conn = conectar(":memory:")
    criar_schema(conn)
    mid = salvar_medida(conn, _medida())
    assert isinstance(mid, int)
    todas = medidas_do_governo(conn, "Lula 3")
    assert len(todas) == 1
    assert todas[0].titulo == "t"
    assert todas[0].id == mid


def test_filtro_apenas_aprovadas():
    conn = conectar(":memory:")
    criar_schema(conn)
    salvar_medida(conn, _medida(status="rascunho", titulo="rasc"))
    salvar_medida(conn, _medida(status="aprovada", titulo="aprov"))
    aprovadas = medidas_do_governo(conn, "Lula 3", apenas_aprovadas=True)
    assert [m.titulo for m in aprovadas] == ["aprov"]


def test_aprovar_medida():
    conn = conectar(":memory:")
    criar_schema(conn)
    mid = salvar_medida(conn, _medida(status="rascunho"))
    aprovar_medida(conn, mid)
    assert medidas_do_governo(conn, "Lula 3", apenas_aprovadas=True)[0].id == mid


def test_editar_medida():
    conn = conectar(":memory:")
    criar_schema(conn)
    mid = salvar_medida(conn, _medida())
    editar_medida(conn, mid, titulo="novo", descricao="nd", fonte_url="https://y")
    m = medidas_do_governo(conn, "Lula 3")[0]
    assert m.titulo == "novo" and m.fonte_url == "https://y"


def test_descartar_medida():
    conn = conectar(":memory:")
    criar_schema(conn)
    mid = salvar_medida(conn, _medida())
    descartar_medida(conn, mid)
    assert medidas_do_governo(conn, "Lula 3") == []


def _lei(id="camara_1", ano=2023, mes=6) -> Lei:
    return Lei(id=id, tipo="LO", numero="14.500", ano=ano,
               data=_dt.date(ano, mes, 1), ementa="e", url="https://x")


def test_upsert_e_consulta_leis_por_intervalo():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [_lei("a", 2023), _lei("b", 2019)])
    dentro = leis_entre(conn, _dt.date(2023, 1, 1), _dt.date(2026, 12, 31))
    assert [x.id for x in dentro] == ["a"]


def test_upsert_leis_idempotente():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [_lei("a")])
    upsert_leis(conn, [_lei("a")])
    assert len(leis_entre(conn, _dt.date(2023, 1, 1), _dt.date(2023, 12, 31))) == 1


def test_temas_roundtrip():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [_lei("a")])
    upsert_lei_temas(conn, "a", ["Saúde", "Economia"])
    upsert_lei_temas(conn, "a", ["Saúde", "Economia"])  # idempotente
    assert sorted(temas_de(conn, "a")) == ["Economia", "Saúde"]


def test_vetos_por_intervalo():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_vetos(conn, [
        Veto(id="v1", data=_dt.date(2023, 5, 1), tipo="parcial",
             descricao="d", materia="Lei X", url="https://x"),
        Veto(id="v2", data=_dt.date(2018, 5, 1), tipo="total",
             descricao="d", materia="Lei Y", url="https://y"),
    ])
    dentro = vetos_entre(conn, _dt.date(2023, 1, 1), _dt.date(2026, 12, 31))
    assert [v.id for v in dentro] == ["v1"]


def test_observacoes_entre_filtra_por_data():
    import datetime

    from app.db import conectar, criar_schema, observacoes_entre, upsert_observacoes, upsert_serie
    from app.models import Indicador, Observacao

    conn = conectar(":memory:")
    criar_schema(conn)
    ind = Indicador(
        id="s", fonte="BCB", codigo_fonte="1", nome="n", unidade="u",
        periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )
    upsert_serie(conn, ind)
    upsert_observacoes(conn, [
        Observacao(serie_id="s", data=datetime.date(2021, 6, 1), valor=1.0),
        Observacao(serie_id="s", data=datetime.date(2023, 6, 1), valor=2.0),
        Observacao(serie_id="s", data=datetime.date(2026, 6, 1), valor=3.0),
    ])
    res = observacoes_entre(conn, "s", datetime.date(2022, 1, 1), datetime.date(2025, 12, 31))
    assert [o.valor for o in res] == [2.0]
