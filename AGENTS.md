# AGENTS.md — guia operacional (carregado TODO loop, mantenha < ~60 linhas)

> Este é o "coração do loop": COMO buildar/rodar/testar, não um diário de progresso.

## Projeto
- Nome: finance_politics — ferramenta pessoal de análise da performance de governos (BR)
- Stack: Python 3.12 + uv + pytest + ruff + pyright + streamlit + plotly
- Dados: SQLite (long format). Fontes: BCB, IBGE/SIDRA, IPEA, Tesouro
- IA: assinatura do Claude Code (Agent SDK / `claude -p`) atrás da interface `LLMClient`
- Fonte da verdade do QUE construir: `specs/*.md` (ativa: `specs/2026-06-20-nucleo-economico.md`)
- Plano de tarefas detalhado: `docs/superpowers/plans/2026-06-20-nucleo-economico.md`
- Rastreador de progresso: `IMPLEMENTATION_PLAN.md`

## Comandos (backpressure)
- Instalar deps:   `uv sync`
- Rodar testes:    `uv run pytest -q`
- Um teste só:     `uv run pytest caminho::nome -v`
- Typecheck:       `uv run pyright`
- Lint:            `uv run ruff check .`
- Format:          `uv run ruff format .`
- Rodar o app:     `uv run streamlit run app/ui.py`
- Ingerir dados:   `uv run python -m app.ingest`

## Convenções
- Commits pequenos, um por tarefa. Mensagem descreve a tarefa concluída. TDD: teste antes.
- Busque com ripgrep ANTES de criar arquivos/funções novos (evite duplicar).
- Não introduza dependências novas sem registrar o motivo no commit.
- **O LLM nunca calcula números** — o backend computa, o modelo só redige. Ver spec.
- Nos testes, `LLMClient` e chamadas HTTP são SEMPRE mockados (zero rede no loop).

## Skills (superpowers) usadas por modo
- plan  → `superpowers:writing-plans`, `superpowers:dispatching-parallel-agents`
- build → `superpowers:test-driven-development`, `superpowers:systematic-debugging`,
          `superpowers:verification-before-completion`

## Placas (guardrails que fui aprendendo) — adicione quando o Ralph descarrilar
- Códigos de série do BCB / tabelas SIDRA podem mudar de versão: confirme no portal
  oficial antes de codar (refs em `compass_artifact_*.md`, Eixo 1).
- APIs públicas BR são instáveis (sobretudo SIDRA): assuma falhas; use retry + cache `raw/`.
