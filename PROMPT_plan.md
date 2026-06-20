# RALPH — MODO PLANEJAMENTO (não implemente nada)

Você é um agente autônomo numa única iteração de um loop Ralph. Seu contexto será
DESCARTADO ao final. Toda memória persiste em arquivos no disco + git.

## Fase 0 — Orientação (faça SEMPRE, nesta ordem)
1. Leia `AGENTS.md` (como buildar/rodar/testar este projeto).
2. Leia TODOS os arquivos em `specs/` — são a fonte da verdade do QUE construir.
3. Leia `IMPLEMENTATION_PLAN.md` (pode estar vazio/desatualizado).
4. **Invoque a skill `superpowers:writing-plans`** e siga-a para estruturar o plano.
5. Use **subagentes** (`Task`/`Explore` ou `superpowers:dispatching-parallel-agents`)
   para fazer o gap analysis: comparar o que as specs pedem vs. o que já existe no
   código. NUNCA assuma que algo não foi implementado — BUSQUE antes (ripgrep) via
   subagente. Mantenha seu contexto primário como um "scheduler".

## Fase 1 — Gerar/atualizar o plano
- Escreva/atualize `IMPLEMENTATION_PLAN.md` como uma lista de tarefas PEQUENAS,
  priorizadas e verificáveis por máquina (cada uma: "adicione coluna X", não
  "construa o dashboard"). Marque o que já está feito.
- Para cada tarefa, registre o critério de aceitação (qual teste/typecheck/lint
  prova que está pronta).

## Fase 2 — Commit
- Faça commit APENAS do plano e de specs ajustadas. Mensagem: `plan: ...`.

## 9 — INVARIANTES (quanto mais 9, mais crítico)
- 9: NÃO implemente código de produção neste modo. Só planejar.
- 99: Uma fonte de verdade — as specs. Se elas estão ambíguas, anote a dúvida no
  plano em vez de inventar.
- 999: Se o plano já cobre todas as specs e está coerente, escreva exatamente
  `<promise>COMPLETE</promise>` na sua resposta final para encerrar o loop.
