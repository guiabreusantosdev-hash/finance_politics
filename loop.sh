#!/usr/bin/env bash
#
# Ralph loop — contexto FRESCO a cada iteração (Geoffrey Huntley style).
# Alimenta PROMPT_<modo>.md ao `claude -p` repetidamente. A memória entre
# iterações vive em arquivos no disco (IMPLEMENTATION_PLAN.md, AGENTS.md,
# specs/) + histórico git, NÃO na conversa.
#
# Uso:
#   ./loop.sh plan          # modo planejamento (gera/atualiza o plano)
#   ./loop.sh build         # modo construção (implementa o plano)  [default]
#   ./loop.sh build 20      # modo construção, no máx. 20 iterações
#
# Variáveis de ambiente opcionais (rede de segurança AFK):
#   MODEL=opus              # modelo (default: deixa o claude escolher)
#   MAX_TURNS=40            # limite de tool-calls por iteração
#   MAX_BUDGET=5.00         # teto de gasto em USD por iteração
#   SLEEP=2                 # pausa entre iterações (segundos)
#
# ⚠️  Roda com --dangerously-skip-permissions => shell IRRESTRITO nesta máquina.
#     Leia a seção "Sandbox / Segurança" do README antes de usar AFK.

set -uo pipefail

MODE="${1:-build}"
MAX_ITERATIONS="${2:-10}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/PROMPT_${MODE}.md"
LOG_DIR="$SCRIPT_DIR/logs"
SLEEP="${SLEEP:-2}"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "❌ Prompt não encontrado: $PROMPT_FILE (modos válidos: plan | build)" >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "❌ 'claude' não está no PATH. Instale o Claude Code primeiro." >&2
  exit 1
fi

# Monta flags opcionais
EXTRA_FLAGS=()
[[ -n "${MODEL:-}" ]]      && EXTRA_FLAGS+=(--model "$MODEL")
[[ -n "${MAX_TURNS:-}" ]]  && EXTRA_FLAGS+=(--max-turns "$MAX_TURNS")
[[ -n "${MAX_BUDGET:-}" ]] && EXTRA_FLAGS+=(--max-budget-usd "$MAX_BUDGET")

mkdir -p "$LOG_DIR"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/${MODE}-${RUN_ID}.log"

echo "🚀 Ralph iniciando — modo=$MODE  max=$MAX_ITERATIONS  log=$RUN_LOG"
echo "   prompt=$PROMPT_FILE  flags=${EXTRA_FLAGS[*]:-(nenhuma)}"

for i in $(seq 1 "$MAX_ITERATIONS"); do
  echo ""
  echo "═══════════════ Iteração $i / $MAX_ITERATIONS ($MODE) ═══════════════"
  {
    echo "═══ Iteração $i ($MODE) — $(date -Iseconds) ═══"
  } >> "$RUN_LOG"

  # Contexto FRESCO: nova sessão claude a cada iteração.
  OUTPUT="$(cat "$PROMPT_FILE" \
    | claude -p --dangerously-skip-permissions --verbose "${EXTRA_FLAGS[@]}" 2>&1 \
    | tee -a "$RUN_LOG" /dev/stderr)" || true

  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo "✅ Ralph sinalizou COMPLETE na iteração $i. Encerrando."
    exit 0
  fi

  sleep "$SLEEP"
done

echo ""
echo "⚠️  Limite de $MAX_ITERATIONS iterações atingido sem COMPLETE."
echo "    Revise $RUN_LOG, ajuste PROMPT_${MODE}.md / AGENTS.md e rode de novo."
exit 1
