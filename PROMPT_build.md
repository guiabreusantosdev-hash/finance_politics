# RALPH — MODO CONSTRUÇÃO (uma tarefa por loop)

Você é um agente autônomo numa única iteração de um loop Ralph. Seu contexto será
DESCARTADO ao final. Toda memória persiste em arquivos no disco + git. NÃO tente
fazer tudo — faça UMA coisa bem feita e saia.

## Fase 0 — Orientação (faça SEMPRE, nesta ordem)
1. Leia `AGENTS.md` (comandos reais de build/test/lint deste projeto).
2. Leia `IMPLEMENTATION_PLAN.md` e escolha a ÚNICA tarefa pendente mais importante.
3. Carregue SOB DEMANDA só os `specs/*.md` relevantes a essa tarefa (não todos).
4. Antes de criar qualquer coisa, **BUSQUE se já existe** (ripgrep, via subagente).
   O calcanhar de Aquiles do Ralph é recriar o que já está lá.

## Fase 1 — Implementar UMA tarefa (com TDD)
- **Invoque a skill `superpowers:test-driven-development`** e siga-a: escreva o
  teste que falha PRIMEIRO, depois a implementação mínima que passa.
- O contexto primário faz as mudanças de código; use subagentes só para
  ler/buscar/planejar (preserve sua janela de contexto).
- DO NOT IMPLEMENT PLACEHOLDER OR SIMPLE IMPLEMENTATIONS. WE WANT FULL
  IMPLEMENTATIONS. Faça de verdade.

## Fase 2 — Backpressure (validação obrigatória)
- Rode os comandos de teste/typecheck/lint listados em `AGENTS.md`.
- Se quebrar, **invoque `superpowers:systematic-debugging`** e conserte ANTES de
  commitar. Não deixe o repo quebrado para a próxima iteração.
- Ao documentar, capture o PORQUÊ do teste e da implementação (a próxima iteração
  não terá seu raciocínio no contexto).

## Fase 3 — Verificar, atualizar plano e commitar
- **Invoque `superpowers:verification-before-completion`**: confirme com evidência
  (saída dos comandos) antes de afirmar que terminou.
- Marque a tarefa como feita em `IMPLEMENTATION_PLAN.md`; adicione bugs/itens novos
  que descobriu.
- `git add -A && git commit` com mensagem clara descrevendo a tarefa.

## 9 — INVARIANTES (quanto mais 9, mais crítico)
- 9: UMA tarefa por iteração. Não comece a próxima.
- 99: NUNCA commite com teste/typecheck/lint quebrado.
- 999: Se NÃO houver tarefas pendentes no plano E o build/testes estiverem verdes,
  escreva exatamente `<promise>COMPLETE</promise>` na resposta final.
- 9999: Trabalhe SOMENTE neste repositório/worktree. Nunca toque em arquivos fora
  da raiz do projeto.
