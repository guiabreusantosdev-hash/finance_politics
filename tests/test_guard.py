import pytest

from app.guard import GuardError, extrair_numeros, numeros_permitidos, verificar, _extrair_numeros_com_tipo
from app.models import (
    Afirmacao,
    DeltaIndicador,
    PayloadAno,
    PayloadComparacao,
    PayloadMandato,
    ResumoFactual,
    ValorIndicador,
    ValorIndicadorMandato,
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


# --- Rate-like vs bare-integer free-text enforcement ---

def test_bare_integers_in_prose_pass():
    """Bare integers (no decimal, no %) are not rate-like and pass freely."""
    resumo = ResumoFactual(
        paragrafos_por_eixo={
            "macro": "No 1º mandato os 3 eixos melhoraram; em 2024 a Selic foi de 11,75%."
        },
        afirmacoes=[Afirmacao(texto="Selic 11,75%", valor_citado=11.75, fonte="BCB")],
    )
    # 1, 3, 2024 are bare integers → ignored; 11,75 is decimal → enforced but is in payload
    verificar(resumo, _payload())  # must not raise


def test_decimal_hallucination_raises():
    """A decimal number not in payload triggers GuardError."""
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic foi de 9,30%."},
        afirmacoes=[],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())


def test_percent_suffixed_integer_hallucination_raises():
    """A bare integer immediately followed by % is rate-like and enforced."""
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic foi de 8%."},
        afirmacoes=[],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())


def test_bare_integer_not_in_payload_passes():
    """A bare integer not present in payload passes (not rate-like)."""
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "os 5 indicadores foram analisados."},
        afirmacoes=[],
    )
    verificar(resumo, _payload())  # must not raise


def test_structured_strictness_restored():
    """valor_citado=8.0 must raise when payload only has Selic=11.75 (no 0-8 allowlist)."""
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "texto sem números relevantes"},
        afirmacoes=[Afirmacao(texto="Selic", valor_citado=8.0, fonte="BCB")],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())


def test_is_rate_like_decimal():
    """_extrair_numeros_com_tipo marks decimal numbers as rate-like."""
    results = dict(_extrair_numeros_com_tipo("valor de 11,75 por cento"))
    assert results[11.75] is True


def test_is_rate_like_percent_suffix():
    """_extrair_numeros_com_tipo marks %-suffixed integers as rate-like."""
    results = dict(_extrair_numeros_com_tipo("cresceu 8%"))
    assert results[8.0] is True


def test_is_not_rate_like_bare_integer():
    """_extrair_numeros_com_tipo marks bare integers as NOT rate-like."""
    results = dict(_extrair_numeros_com_tipo("os 3 eixos"))
    assert results[3.0] is False


def test_hallucinated_value_still_raises():
    """Decimal hallucination in prose must still raise GuardError."""
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic foi de 9,00% no período."},
        afirmacoes=[],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())


# --- I3: PayloadMandato in guard ---

def _payload_mandato() -> PayloadMandato:
    return PayloadMandato(
        mandato="Dilma 1",
        ano_inicio=2011,
        ano_fim=2014,
        indicadores=[
            ValorIndicadorMandato(
                nome="Meta Selic",
                valor_inicio=11.75,
                valor_fim=10.9,
                variacao=-7.23,
                unidade="% a.a.",
                fonte="BCB",
            )
        ],
        faltantes=[],
    )


def test_mandato_anos_em_permitidos():
    """Mandate years must appear in numeros_permitidos for PayloadMandato."""
    p = _payload_mandato()
    permitidos = numeros_permitidos(p)
    assert 2011.0 in permitidos
    assert 2014.0 in permitidos


def test_mandato_valores_em_permitidos():
    """Indicator values (inicio, fim, variacao) must be in numeros_permitidos."""
    p = _payload_mandato()
    permitidos = numeros_permitidos(p)
    assert 11.75 in permitidos
    assert 10.9 in permitidos
    assert -7.23 in permitidos


def test_resumo_mandato_fiel_passa():
    """A mandate summary citing only payload numbers must not raise."""
    p = _payload_mandato()
    resumo = ResumoFactual(
        paragrafos_por_eixo={
            "macro": "No mandato Dilma 1 (2011-2014) a Selic caiu de 11,75% para 10,9%."
        },
        afirmacoes=[
            Afirmacao(texto="Selic início", valor_citado=11.75, fonte="BCB"),
            Afirmacao(texto="Selic fim", valor_citado=10.9, fonte="BCB"),
        ],
    )
    verificar(resumo, p)  # must not raise


def test_resumo_mandato_alucinado_falha():
    """A mandate summary with an invented number must raise GuardError."""
    p = _payload_mandato()
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic estava em 15,00% no mandato."},
        afirmacoes=[],
    )
    with pytest.raises(GuardError):
        verificar(resumo, p)
