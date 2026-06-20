import datetime

from app.models import Indicador, Observacao, PayloadAno, ResumoFactual, ValorIndicador


def test_observacao_roundtrip():
    o = Observacao(serie_id="bcb_432_selic", data=datetime.date(2024, 1, 1), valor=11.75)
    assert o.valor == 11.75


def test_indicador_rejects_bad_eixo():
    import pytest

    with pytest.raises(ValueError):
        Indicador(
            id="x", fonte="BCB", codigo_fonte="1", nome="X", unidade="%",
            periodicidade="mensal", eixo="invalido", metodo_anual="media",  # type: ignore[arg-type]
        )


def test_payload_ano_holds_faltantes():
    p = PayloadAno(
        ano=2024,
        indicadores=[ValorIndicador(nome="Selic", valor=11.75, unidade="% a.a.",
                                    fonte="BCB", data_ref=datetime.date(2024, 12, 1))],
        faltantes=["IDH-M"],
    )
    assert p.faltantes == ["IDH-M"]


def test_resumo_factual_structure():
    r = ResumoFactual(paragrafos_por_eixo={"macro": "txt"}, afirmacoes=[])
    assert r.paragrafos_por_eixo["macro"] == "txt"
