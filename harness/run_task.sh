#!/usr/bin/env bash
# Overclaiming Report — single-task runner (see docs/overclaiming-report/PLAN.md).
#
#   bash harness/run_task.sh <task-id> <repo-url> <task-file> <workdir>
#
# 1. clones the target repo into <workdir>/<task-id>
# 2. hands the task + receipt-emission rules to the agent (AGENT_CMD)
# 3. commits whatever the agent produced (merge simulation: merged-ref = HEAD)
# 4. scores the receipt objectively; appends the row to the report ledger
#
# AGENT_CMD contract: reads the prompt on stdin, works in $PWD, writes a receipt
# to receipts/. Example for Claude Code headless:
#   AGENT_CMD='claude -p --permission-mode acceptEdits'
# NO RUNS until operator sets AGENT_CMD and approves budget (pre-registered plan).
set -euo pipefail

TASK_ID="${1:?task-id}"; REPO_URL="${2:?repo-url}"; TASK_FILE="${3:?task-file}"; WORK="${4:?workdir}"
: "${AGENT_CMD:?set AGENT_CMD (operator budget gate — see PLAN.md)}"

DEST="$WORK/$TASK_ID"
git clone -q --depth 50 "$REPO_URL" "$DEST"
mkdir -p "$DEST/receipts"

PROMPT="$WORK/$TASK_ID.prompt"
cat "$TASK_FILE" > "$PROMPT"
printf '\n\n---\n' >> "$PROMPT"
cat "$(dirname "$0")/../docs/pilot/receipt-emission.md" >> "$PROMPT"

( cd "$DEST" && $AGENT_CMD < "$PROMPT" ) | tee "$WORK/$TASK_ID.agent.log"

cd "$DEST"
git add -A
git -c user.email=harness@signalbrain.ai -c user.name=harness commit -qm "agent change for $TASK_ID" || {
  echo "{\"task\": \"$TASK_ID\", \"outcome\": \"no_change\"}" >> "$WORK/report-ledger.jsonl"; exit 0; }

RECEIPT=$(ls receipts/*.md 2>/dev/null | head -1 || true)
if [ -z "$RECEIPT" ]; then
  echo "{\"task\": \"$TASK_ID\", \"outcome\": \"no_receipt\"}" >> "$WORK/report-ledger.jsonl"; exit 0
fi
sb score "$RECEIPT" --root . --ledger "$WORK/report-ledger.jsonl" --ref HEAD || true
