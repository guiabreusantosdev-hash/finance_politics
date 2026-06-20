import pytest

from app.guard import GuardError, extrair_numeros, numeros_permitidos, verificar
from app.models import (
    Afirmacao,
    DeltaIndicador,
    PayloadAno,
    PayloadComparacao,
    ResumoFactual,
    ValorIndicador,
)


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


# --- C2: regex must not consume minus in year range like "2019-2022" ---

def test_extrai_numeros_year_range_positive():
    """'entre 2019-2022' must yield 2019.0 and 2022.0 (both positive)."""
    nums = extrair_numeros("entre 2019-2022")
    assert 2019.0 in nums
    assert 2022.0 in nums
    assert -2022.0 not in nums


# --- C1: PayloadComparacao must include mandate years in permitted set ---

def _comparacao_payload() -> PayloadComparacao:
    return PayloadComparacao(
        mandato_a="Lula 1",
        mandato_b="Lula 2",
        ano_inicio_a=2003,
        ano_fim_a=2006,
        ano_inicio_b=2007,
        ano_fim_b=2010,
        deltas=[
            DeltaIndicador(
                nome="PIB", valor_a=2.7, valor_b=4.0, delta=1.3,
                unidade="%", fonte="IBGE",
            )
        ],
    )


def test_comparacao_anos_em_permitidos():
    """Mandate years must appear in numeros_permitidos for PayloadComparacao."""
    p = _comparacao_payload()
    permitidos = numeros_permitidos(p)
    assert 2003.0 in permitidos
    assert 2006.0 in permitidos
    assert 2007.0 in permitidos
    assert 2010.0 in permitidos


def test_resumo_comparacao_com_anos_passa():
    """A comparison summary that mentions the mandate years must not raise."""
    p = _comparacao_payload()
    resumo = ResumoFactual(
        paragrafos_por_eixo={
            "macro": "No período 2003-2006 o PIB cresceu 2,7% e em 2007-2010 cresceu 4,0%."
        },
        afirmacoes=[
            Afirmacao(texto="PIB Lula 1", valor_citado=2.7, fonte="IBGE"),
            Afirmacao(texto="PIB Lula 2", valor_citado=4.0, fonte="IBGE"),
        ],
    )
    verificar(resumo, p)  # must not raise


# --- I1: small integers (0-12) must always be permitted ---

def test_small_integers_always_permitted():
    """Ordinals/counts 0-12 must not cause GuardError even if not in payload."""
    resumo = ResumoFactual(
        paragrafos_por_eixo={
            "macro": "Lula 1 governou por 1 mandato com 3 eixos principais no 1º trimestre."
        },
        afirmacoes=[],
    )
    # Payload has only Selic 11.75 and year 2024 — small ints 1, 3 are not in payload values
    verificar(resumo, _payload())  # must not raise


def test_hallucinated_value_still_raises_with_small_int_fix():
    """Small int fix must NOT allow real hallucinated indicator values (e.g. 9.0)."""
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic foi de 9,00% no período."},
        afirmacoes=[],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())
