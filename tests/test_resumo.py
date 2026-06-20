import json

import pytest

from app.models import PayloadAno, ValorIndicador
from app.resumo import gerar_resumo, montar_prompt


def _payload() -> PayloadAno:
    return PayloadAno(
        ano=2024,
        indicadores=[ValorIndicador(nome="Selic", valor=11.75, unidade="% a.a.",
                                    fonte="BCB", data_ref=None)],
        faltantes=[],
    )


class _ClientFixo:
    def __init__(self, resposta: str):
        self.resposta = resposta
        self.chamadas = 0

    def gerar(self, prompt: str) -> str:
        self.chamadas += 1
        return self.resposta


def test_prompt_inclui_valores_e_regra():
    p = montar_prompt(_payload())
    assert "11.75" in p or "11,75" in p
    assert "Selic" in p


def test_gerar_resumo_valido():
    resposta = json.dumps({
        "paragrafos_por_eixo": {"macro": "A Selic encerrou 2024 em 11,75% (fonte: BCB)."},
        "afirmacoes": [{"texto": "Selic", "valor_citado": 11.75, "fonte": "BCB"}],
    })
    r = gerar_resumo(_ClientFixo(resposta), _payload())
    assert r.afirmacoes[0].valor_citado == 11.75


def test_gerar_resumo_rejeita_alucinacao_e_esgota_tentativas():
    resposta = json.dumps({
        "paragrafos_por_eixo": {"macro": "A Selic foi de 9,00%."},
        "afirmacoes": [],
    })
    client = _ClientFixo(resposta)
    with pytest.raises(ValueError):
        gerar_resumo(client, _payload(), tentativas=2)
    assert client.chamadas == 2
