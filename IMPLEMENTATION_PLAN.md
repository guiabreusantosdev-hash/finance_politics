# IMPLEMENTATION_PLAN.md

> Rastreador dinâmico de tarefas. GERADO/ATUALIZADO pelo Ralph no modo `plan`.
> É descartável: regenere (rode `./loop.sh plan`) quando ficar obsoleto ou o
> Ralph descarrilar. NÃO é a fonte da verdade — `specs/*.md` é.

> Plano detalhado (fonte da verdade das tarefas): `docs/superpowers/plans/2026-06-20-nucleo-economico.md`

## Pendente
- [x] T1: Scaffold uv (pyproject, ruff, pyright, pytest)
- [x] T2: DTOs Pydantic (`app/models.py`)
- [x] T3: Config registry + loader (`config/*.yaml`, `app/config_loader.py`)
- [x] T4: Camada SQLite (`app/db.py`)
- [x] T5: Fetcher base + BCB (`app/fetchers/`)
- [x] T6: Fetcher SIDRA
- [x] T7: Fetchers IPEA + Tesouro
- [x] T8: Orquestração de ingestão (`app/ingest.py`)
- [x] T9: Cálculo determinístico (`app/calculo.py`)
- [x] T10: Payload builders (`app/payload.py`)
- [x] T11: Guard de factualidade (`app/guard.py`)
- [x] T12: LLMClient + ClaudeCodeClient (`app/llm.py`)
- [x] T13: Geração de resumo + retry (`app/resumo.py`)
- [x] T14: LLM-as-judge (`app/judge.py`)
- [x] T15: UI Streamlit + verificação da suíte (`app/ui.py`)

## Em progresso
- (nada)

## Feito
- Specs + plano detalhado escritos e commitados.
- Persistência de resumos (cache + histórico) — spec+plano 2026-06-21.

## Bugs / dívidas descobertas
- (nada)
