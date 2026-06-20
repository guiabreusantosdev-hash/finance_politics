# AGENTS.md — guia operacional (carregado TODO loop, mantenha < ~60 linhas)

> Este é o "coração do loop": COMO buildar/rodar/testar, não um diário de progresso.
> É aqui que a backpressure fica específica do projeto. Edite os comandos abaixo
> para os REAIS do seu projeto antes do primeiro `./loop.sh build`.

## Projeto
- Nome: <preencha>
- Stack: <ex.: Python 3.12 + pytest + ruff>  /  <ex.: Node 20 + vitest + tsc>
- Fonte da verdade do QUE construir: `specs/*.md`
- Rastreador de tarefas: `IMPLEMENTATION_PLAN.md`

## Comandos (backpressure) — ajuste para o seu projeto
- Instalar deps:   `<ex.: uv sync>`  /  `<ex.: npm ci>`
- Rodar testes:    `<ex.: pytest -q>`  /  `<ex.: npm test>`
- Typecheck:       `<ex.: pyright>`  /  `<ex.: npx tsc --noEmit>`
- Lint:            `<ex.: ruff check .>`  /  `<ex.: npm run lint>`
- Rodar o app:     `<ex.: python -m app>`  /  `<ex.: npm run dev>`

## Convenções
- Commits pequenos, um por tarefa. Mensagem descreve a tarefa concluída.
- Busque com ripgrep ANTES de criar arquivos/funções novos (evite duplicar).
- Não introduza dependências novas sem registrar o motivo no commit.

## Skills (superpowers) usadas por modo
- plan  → `superpowers:writing-plans`, `superpowers:dispatching-parallel-agents`
- build → `superpowers:test-driven-development`, `superpowers:systematic-debugging`,
          `superpowers:verification-before-completion`

## Placas (guardrails que fui aprendendo) — adicione quando o Ralph descarrilar
- (ex.: "Os testes de integração precisam do Postgres rodando: `docker compose up -d db`")
- (ex.: "NÃO edite arquivos gerados em src/generated/")
