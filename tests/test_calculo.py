import datetime

from typing import Literal

from app.calculo import tipo_grafico, valor_no_periodo, variacao
from app.models import Indicador, Observacao


def _ind(
    metodo: Literal["fim_periodo", "media", "acumulado_12m"],
    periodicidade: Literal["mensal", "trimestral", "anual", "diaria"] = "mensal",
) -> Indicador:
    return Indicador(
        id="s", fonte="BCB", codigo_fonte="1", nome="S", unidade="u",
        periodicidade=periodicidade, eixo="macro", metodo_anual=metodo,
    )


def _serie(pares):
    return [Observacao(serie_id="s", data=d, valor=v) for d, v in pares]


def test_fim_periodo_pega_ultimo_do_ano():
    obs = _serie([
        (datetime.date(2024, 1, 1), 10.0),
        (datetime.date(2024, 12, 1), 12.0),
        (datetime.date(2025, 1, 1), 13.0),
    ])
    assert valor_no_periodo(obs, _ind("fim_periodo"), 2024) == 12.0


def test_media_calcula_media_do_ano():
    obs = _serie([
        (datetime.date(2024, 3, 1), 8.0),
        (datetime.date(2024, 6, 1), 6.0),
    ])
    assert valor_no_periodo(obs, _ind("media"), 2024) == 7.0


def test_acumulado_12m_compoe_variacoes_mensais():
    # dois meses de 1% cada -> (1.01*1.01 - 1) ~ 2.01%
    obs = _serie([(datetime.date(2024, 11, 1), 1.0), (datetime.date(2024, 12, 1), 1.0)])
    got = valor_no_periodo(obs, _ind("acumulado_12m"), 2024)
    assert got is not None
    assert abs(got - 2.01) < 1e-6


def test_valor_no_periodo_sem_dado_retorna_none():
    assert valor_no_periodo([], _ind("media"), 2024) is None


def test_variacao_percentual():
    assert variacao(100.0, 110.0) == 10.0
    assert variacao(None, 110.0) is None
    assert variacao(0.0, 5.0) is None  # evita divisão por zero


def test_tipo_grafico_anual_vira_barras():
    assert tipo_grafico(_ind("fim_periodo", "anual")) == "barras"


def test_tipo_grafico_mensal_vira_linha():
    assert tipo_grafico(_ind("media", "mensal")) == "linha"


def test_tipo_grafico_diaria_vira_linha():
    assert tipo_grafico(_ind("fim_periodo", "diaria")) == "linha"
