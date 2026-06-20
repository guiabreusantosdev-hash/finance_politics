import json

from app.judge import Veredito, julgar
from app.models import Afirmacao, PayloadAno, ResumoFactual, ValorIndicador


class _ClientFixo:
    def __init__(self, resposta: str):
        self.resposta = resposta

    def gerar(self, prompt: str) -> str:
        return self.resposta


def _payload() -> PayloadAno:
    return PayloadAno(ano=2024, indicadores=[ValorIndicador(
        nome="Selic", valor=11.75, unidade="% a.a.", fonte="BCB", data_ref=None)], faltantes=[])


def _resumo() -> ResumoFactual:
    return ResumoFactual(
        paragrafos_por_eixo={"macro": "Selic 11,75% (fonte: BCB)."},
        afirmacoes=[Afirmacao(texto="Selic", valor_citado=11.75, fonte="BCB")],
    )


def test_julgar_retorna_veredito():
    resposta = json.dumps({
        "ancorado": True, "neutro": True, "numeros_fora_do_payload": [], "observacoes": "ok"
    })
    v = julgar(_ClientFixo(resposta), _payload(), _resumo())
    assert isinstance(v, Veredito)
    assert v.ancorado is True
    assert v.numeros_fora_do_payload == []
