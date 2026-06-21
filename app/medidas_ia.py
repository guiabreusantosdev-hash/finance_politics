"""Assistente de IA: rascunha medidas de um ministro (sempre com fonte)."""
from __future__ import annotations

import json

from app.llm import LLMClient
from app.models import Medida, Ministro

_REGRAS = (
    "Liste até {n} principais medidas/políticas do ministro abaixo. Para CADA medida "
    "forneça: titulo (curto), descricao (factual e neutra) e fonte_url (link verificável). "
    "NUNCA invente fontes; se não houver fonte confiável, OMITA a medida. "
    'Responda APENAS JSON no schema: {{"medidas": [{{"titulo": str, "descricao": str, '
    '"fonte_url": str}}]}}.'
)


def rascunhar_medidas(client: LLMClient, ministro: Ministro, n: int = 3) -> list[Medida]:
    prompt = (
        _REGRAS.format(n=n)
        + f"\n\nMINISTRO: {ministro.nome} — pasta {ministro.pasta} "
        + f"(governo {ministro.governo})."
    )
    dados = json.loads(client.gerar(prompt))
    medidas: list[Medida] = []
    for item in dados.get("medidas", []):
        fonte = (item.get("fonte_url") or "").strip()
        if not fonte:
            continue
        medidas.append(
            Medida(
                governo=ministro.governo,
                pasta=ministro.pasta,
                ministro=ministro.nome,
                titulo=item["titulo"],
                descricao=item["descricao"],
                fonte_url=fonte,
                status="rascunho",
                origem="ia",
            )
        )
    return medidas
