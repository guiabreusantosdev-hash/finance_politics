import pytest

from app.guard import GuardError, extrair_numeros, verificar
from app.models import Afirmacao, PayloadAno, ResumoFactual, ValorIndicador


def _payload() -> PayloadAno:
    return PayloadAno(
        ano=2024,
        indicadores=[ValorIndicador(nome="Selic", valor=11.75, unidade="% a.a.",
                                    fonte="BCB", data_ref=None)],
        faltantes=[],
    )


def test_extrai_numeros_pt_br():
    assert 11.75 in extrair_numeros("A Selic foi de 11,75% ao ano.")
    assert 11.75 in extrair_numeros("A Selic foi de 11.75%.")


def test_resumo_fiel_passa():
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic encerrou 2024 em 11,75% (fonte: BCB)."},
        afirmacoes=[Afirmacao(texto="Selic 11,75%", valor_citado=11.75, fonte="BCB")],
    )
    verificar(resumo, _payload())  # não levanta


def test_numero_alucinado_no_texto_falha():
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic encerrou 2024 em 9,00%."},
        afirmacoes=[],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())


def test_valor_citado_fora_do_payload_falha():
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "texto sem números"},
        afirmacoes=[Afirmacao(texto="Selic", valor_citado=9.0, fonte="BCB")],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())
