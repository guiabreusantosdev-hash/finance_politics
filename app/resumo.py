"""Generate factual summaries: prompt -> LLM -> validate schema -> factuality guard."""
from __future__ import annotations

import json

from app.guard import GuardError, verificar
from app.llm import LLMClient
from app.models import PayloadAno, PayloadComparacao, PayloadMandato, PayloadMinisterialGoverno, ResumoFactual

_REGRAS = (
    "Você redige um resumo FACTUAL e NEUTRO sobre indicadores de um governo. "
    "REGRAS: (1) use SOMENTE os números fornecidos no payload; NUNCA invente ou calcule "
    "valores. (2) Cite a fonte de cada afirmação. (3) Sem juízo de valor, sem dizer qual "
    "governo foi melhor, sem causação especulativa. (4) Para itens em 'faltantes', diga "
    "'sem dado disponível'. Responda APENAS com JSON no schema: "
    '{"paragrafos_por_eixo": {"macro": str, "fiscal": str, "social": str}, '
    '"afirmacoes": [{"texto": str, "valor_citado": number, "fonte": str}]}.'
)

_REGRAS_MINISTERIAL = (
    "Você redige um resumo FACTUAL e NEUTRO sobre os ministros de um governo e suas "
    "medidas. REGRAS: (1) use SOMENTE as medidas fornecidas no payload; NUNCA invente "
    "medidas, números ou fontes. (2) Cite a fonte (fonte_url) de cada afirmação. (3) Sem "
    "juízo de valor, sem dizer se foi bom ou ruim, sem causação especulativa. (4) Emenda "
    "Constitucional é promulgada pelo Congresso, não sancionada — não atribua ao ministro. "
    "(5) Deixe 'afirmacoes' como lista vazia (não há números a citar). Responda APENAS com "
    'JSON no schema: {"paragrafos_por_eixo": {<pasta>: str}, "afirmacoes": []}.'
)


def montar_prompt(payload: PayloadAno | PayloadComparacao | PayloadMandato | PayloadMinisterialGoverno, regras: str = _REGRAS) -> str:
    return f"{regras}\n\nPAYLOAD:\n{payload.model_dump_json(indent=2)}"


def gerar_resumo(
    client: LLMClient,
    payload: PayloadAno | PayloadComparacao | PayloadMandato | PayloadMinisterialGoverno,
    tentativas: int = 3,
    regras: str = _REGRAS,
) -> ResumoFactual:
    prompt = montar_prompt(payload, regras)
    erro: Exception | None = None
    for _ in range(tentativas):
        bruto = client.gerar(prompt)
        try:
            resumo = ResumoFactual.model_validate(json.loads(bruto))
            verificar(resumo, payload)
            return resumo
        except (json.JSONDecodeError, ValueError, GuardError) as exc:
            erro = exc
    raise ValueError(f"não foi possível gerar resumo válido em {tentativas} tentativas: {erro}")
