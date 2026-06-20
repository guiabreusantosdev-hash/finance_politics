# Ralph + Superpowers — template reutilizável

Loop **Ralph** (Geoffrey Huntley) com **contexto fresco a cada iteração**, integrado
às skills do plugin **superpowers**. O loop bash alimenta `PROMPT_<modo>.md` ao
`claude -p` repetidamente; a memória entre iterações vive em arquivos no disco
(`specs/`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md`) + git, **não** na conversa.

> Por que isso e não o plugin `ralph-loop`? O plugin oficial roda na MESMA sessão
> (acumula contexto → "context rot"). O loop bash descarta o contexto a cada volta —
> a forma canônica do Huntley, e a que seu guia recomenda
> (`ia_guidelines/guia-ralph-framework-hermes.md`).

---

## Como Ralph e Superpowers se encaixam

| Camada | Papel | Onde |
|---|---|---|
| **Ralph (loop.sh)** | Reinicia o agente com contexto fresco, uma tarefa por volta | `loop.sh` |
| **Superpowers (skills)** | DIZEM ao agente *como* planejar, testar, debugar, verificar | invocadas dentro dos `PROMPT_*.md` |
| **Memória externa** | O QUE construir e o que falta | `specs/`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` |

As skills são chamadas **dentro de cada iteração**, pelos prompts:

- **`plan`** → `superpowers:writing-plans` + `superpowers:dispatching-parallel-agents`
  (gap analysis specs × código).
- **`build`** → `superpowers:test-driven-development` → `superpowers:systematic-debugging`
  (se quebrar) → `superpowers:verification-before-completion` (antes de commitar).

> `superpowers:brainstorming` é **interativa** — use você mesmo, com o Claude, na
> Fase 1 (escrever as specs). Ela NÃO roda dentro do loop headless.

---

## Pré-requisitos (já checados nesta máquina)

- ✅ Claude Code instalado (`claude --version` → 2.1.x) e autenticado.
- ✅ Plugin **superpowers** ativo (`~/.claude/settings.json` →
  `"superpowers@claude-plugins-official": true`).
- ⚠️ **git**: o template ainda não é um repo. Veja o passo 1.
- ⚠️ **Docker**: NÃO instalado. Leia "Sandbox / Segurança" antes de rodar AFK.

Conferir o plugin a qualquer momento: `claude` → `/plugin` (ou veja `settings.json`).

---

## Passo a passo

### 0. Copie o template para um projeto novo
```bash
cp -r /home/rondor/ia_projetcs/ralph-template /home/rondor/ia_projetcs/meu-projeto
cd /home/rondor/ia_projetcs/meu-projeto
```

### 1. Inicialize o git (memória entre iterações + atribuição)
```bash
git init
git config user.name  "ralph-agent"      # identidade distinta do agente
git config user.email "ralph@local"
git add -A && git commit -m "chore: scaffold Ralph + superpowers"
```

### 2. Edite o `AGENTS.md` (o "coração do loop")
Troque os placeholders pelos comandos REAIS de **test / typecheck / lint** do seu
projeto. É a backpressure que força o Ralph a acertar. Mantenha < ~60 linhas.

### 3. Fase 1 — Escreva as specs (interativo, com brainstorming)
Abra o Claude normal e use a skill de brainstorming para transformar a ideia em
specs verificáveis:
```bash
claude
# dentro da sessão:
#   "Use a skill superpowers:brainstorming para definirmos as specs do projeto."
```
Resultado: um arquivo por tópico em `specs/`. Apague o `specs/EXEMPLO-topico.md`.
**Specs ruins → resultado ruim.** Não pule isto.

### 4. Fase 2 — Modo PLANEJAMENTO (gera o IMPLEMENTATION_PLAN.md)
```bash
./loop.sh plan 2        # no máx. 2 iterações; normalmente basta 1
```
O Ralph lê `specs/`, faz gap analysis com subagentes e escreve o plano. Não
implementa nada. Revise o `IMPLEMENTATION_PLAN.md` gerado antes de seguir.

### 5. Fase 3 — Modo CONSTRUÇÃO (o loop que roda repetido)
Comece com poucas iterações, **observando**:
```bash
./loop.sh build 3
```
Cada iteração: escolhe 1 tarefa → TDD → roda testes → verifica → commita → sai →
próxima volta com contexto fresco. Quando não houver mais tarefas e o build estiver
verde, o agente emite `<promise>COMPLETE</promise>` e o loop para sozinho.

### 6. AFK — só depois de afinar o prompt
Com redes de segurança:
```bash
MAX_TURNS=40 MAX_BUDGET=5.00 MODEL=opus ./loop.sh build 20
```

---

## Comandos do `loop.sh`

```bash
./loop.sh plan          # planejar (gera/atualiza o plano)
./loop.sh build         # construir (default), 10 iterações
./loop.sh build 20      # construir, no máx. 20 iterações
```

Variáveis de ambiente (rede de segurança):

| Var | Efeito | Exemplo |
|---|---|---|
| `MODEL` | escolhe o modelo | `MODEL=opus` |
| `MAX_TURNS` | limita tool-calls por iteração | `MAX_TURNS=40` |
| `MAX_BUDGET` | teto de gasto USD por iteração | `MAX_BUDGET=5.00` |
| `SLEEP` | pausa entre iterações (s) | `SLEEP=5` |

Logs de cada run ficam em `logs/<modo>-<timestamp>.log`.

---

## Tuning ("tune o Ralph como um violão")

- Repetiu o mesmo erro >2-3 vezes? PARE. Adicione uma "placa" em `PROMPT_build.md`
  ou em `AGENTS.md` (seção *Placas*), ou regenere o plano com `./loop.sh plan`.
- Acordou com o repo quebrado? É esperado. `git reset --hard` para o último commit
  verde e reinicie, ou crie um prompt de resgate.
- Tarefa grande demais por loop → quebre em tarefas menores no plano.
- Plano obsoleto → delete e rode `./loop.sh plan` de novo (é descartável).

---

## Sandbox / Segurança ⚠️ (LEIA)

O loop usa **`--dangerously-skip-permissions`** (sem isso, o modo headless trava no
primeiro pedido de permissão). Isso dá ao agente **shell irrestrito NESTA máquina**.
Nesta configuração **não há isolamento** — foi a opção escolhida ("só documentar o
risco"). Antes de rodar AFK, prefira UMA destas proteções:

1. **Docker (isolamento real, recomendado p/ AFK).** No WSL:
   ```bash
   sudo apt-get update && sudo apt-get install -y docker.io
   sudo usermod -aG docker "$USER"   # relogue depois
   # rode o claude dentro de um container montando só a pasta do projeto
   ```
2. **Git worktree + branch isolado** (sem Docker; isola o *trabalho*, não o shell):
   ```bash
   git worktree add ../meu-projeto-ralph -b ralph/run-1
   cd ../meu-projeto-ralph && /caminho/loop.sh build 5
   ```
   Dentro do Claude você pode usar `superpowers:using-git-worktrees` para isso.
3. **No mínimo:** rode numa pasta SEM credenciais de produção, configure limites de
   gasto na conta Anthropic, e use `MAX_TURNS`/`MAX_BUDGET`. Nunca aponte para um
   diretório com chaves/segredos no alcance.

Regra mental do Ralph: a saída é **verificável por máquina** (testes/lint passam)?
Se sim, faça loop. Se não, mantenha humano no loop ou configure um LLM-as-judge.

---

## Estrutura de arquivos

```
ralph-template/
├── loop.sh                 # o loop Ralph (bash, contexto fresco/iteração)
├── PROMPT_plan.md          # instruções do modo planejamento (chama writing-plans)
├── PROMPT_build.md         # instruções do modo construção (chama TDD/debug/verify)
├── AGENTS.md               # guia operacional + backpressure (EDITE com seus comandos)
├── IMPLEMENTATION_PLAN.md  # rastreador de tarefas (gerado pelo Ralph)
├── specs/                  # fonte da verdade do QUE construir (1 arquivo/tópico)
│   └── EXEMPLO-topico.md   # apague após criar specs reais
├── logs/                   # logs por run (git-ignored)
└── .gitignore
```

Referência completa da técnica: `../ia_guidelines/guia-ralph-framework-hermes.md`.
