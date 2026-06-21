"""LLM-as-judge: a subagent checks grounding + neutrality of a generated summary."""
from __future__ import annotations

import json

from pydantic import BaseModel

from app.llm import LLMClient
from app.models import PayloadAno, PayloadComparacao, PayloadMandato, PayloadMinisterialGoverno, ResumoFactual

_INSTRUCAO = (
    "Você é um JUIZ rigoroso. Dado um PAYLOAD de dados e um RESUMO, verifique: "
    "(a) toda afirmação do resumo está ancorada em valores do payload; "
    "(b) o tom é neutro (sem juízo de valor, sem causação especulativa); "
    "(c) liste números citados que NÃO existem no payload. Responda APENAS JSON: "
    '{"ancorado": bool, "neutro": bool, "numeros_fora_do_payload": [number], "observacoes": str}.'
)


class Veredito(BaseModel):
    ancorado: bool
    neutro: bool
    numeros_fora_do_payload: list[float]
    observacoes: str


def julgar(
    client: LLMClient,
    payload: PayloadAno | PayloadComparacao | PayloadMandato | PayloadMinisterialGoverno,
    resumo: ResumoFactual,
) -> Veredito:
    prompt = (
        f"{_INSTRUCAO}\n\nPAYLOAD:\n{payload.model_dump_json(indent=2)}"
        f"\n\nRESUMO:\n{resumo.model_dump_json(indent=2)}"
    )
    bruto = client.gerar(prompt)
    return Veredito.model_validate(json.loads(bruto))
