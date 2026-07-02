#!/usr/bin/env bash
# Targeted objective score for one human-merged A/B receipt (Track 1).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="${ROOT}/.venv/bin:${PATH}"
export PYTHONPATH="${ROOT}/src:${ROOT}/scripts"

RECEIPT="${1:-}"
if [[ -z "$RECEIPT" ]]; then
  echo "usage: bash scripts/calibration_score_receipt.sh docs/improvements/NNNN-name.md" >&2
  exit 1
fi
if [[ ! -f "$RECEIPT" ]]; then
  echo "calibration_score_receipt: file not found: $RECEIPT" >&2
  exit 1
fi

# Track 1 doctrine: only human-merged receipts earn measured ledger rows.
bash "$ROOT/scripts/calibration_receipt_merged_check.sh" "$RECEIPT"

echo "=== targeted objective score: $RECEIPT ==="
RESCORE_ARGS=()
if [[ "${CALIBRATION_RESCORE:-0}" == "1" ]]; then
  RESCORE_ARGS+=(--rescore)
fi
python "$ROOT/scripts/calibration_score_measured.py" --receipts "$RECEIPT" "${RESCORE_ARGS[@]}"
echo ""
echo "=== measured-only gate ==="
python "$ROOT/scripts/calibration_ledger.py" \
  "$ROOT/docs/calibration/improvement_claim_ledger.jsonl" \
  --require-measured --by-class --window "${TITAN_CALIBRATION_WINDOW:-10}"
