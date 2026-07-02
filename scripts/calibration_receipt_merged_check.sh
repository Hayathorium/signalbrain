#!/usr/bin/env bash
# Guard: a receipt may only be objectively scored once it is HUMAN-MERGED.
#
# Scoring a working-tree receipt before merge lets a lane credit itself with
# held=true rows for work that never survived review (observed 2026-07-02:
# an unmerged, untracked receipt was scored held=true into the measured
# ledger). The scorer re-runs the receipt's own commands, so the content that
# is scored must be exactly the content that was merged.
#
# Exit codes:
#   0 — receipt exists on the merged ref with identical content (or override)
#   3 — receipt is not on the merged ref (unmerged / untracked / outside repo)
#   4 — receipt differs from the merged content (doctored local copy)
#   5 — merged ref unavailable (fetch first, or override)
#
# Env:
#   CALIBRATION_MERGED_REF     ref that defines "merged" (default origin/main)
#   CALIBRATION_ALLOW_UNMERGED set to 1 to bypass (supervised experiments only)
#
# $2 (optional, tests only): worktree file to hash instead of the receipt path.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

RECEIPT="${1:-}"
if [[ -z "$RECEIPT" ]]; then
  echo "usage: bash scripts/calibration_receipt_merged_check.sh docs/improvements/NNNN-name.md" >&2
  exit 1
fi

if [[ "${CALIBRATION_ALLOW_UNMERGED:-0}" == "1" ]]; then
  echo "calibration_receipt_merged_check: CALIBRATION_ALLOW_UNMERGED=1 — skipping merged-receipt guard (supervised only)" >&2
  exit 0
fi

REF="${CALIBRATION_MERGED_REF:-origin/main}"
if ! git -C "$ROOT" rev-parse --verify --quiet "$REF^{commit}" >/dev/null; then
  echo "calibration_receipt_merged_check: ref '$REF' unavailable — git fetch origin, or set CALIBRATION_ALLOW_UNMERGED=1 (supervised only)" >&2
  exit 5
fi

ABS="$(cd "$(dirname "$RECEIPT")" 2>/dev/null && pwd)/$(basename "$RECEIPT")" || ABS="$RECEIPT"
case "$ABS" in
  "$ROOT"/*) REL="${ABS#"$ROOT"/}" ;;
  *)
    echo "calibration_receipt_merged_check: $RECEIPT is outside the repo — score only human-merged receipts (Track 1)" >&2
    exit 3
    ;;
esac

if ! git -C "$ROOT" cat-file -e "$REF:$REL" 2>/dev/null; then
  echo "calibration_receipt_merged_check: $REL is not on $REF — score only human-merged receipts (Track 1)" >&2
  exit 3
fi

WORKFILE="${2:-$ROOT/$REL}"
LOCAL_HASH="$(git -C "$ROOT" hash-object "$WORKFILE")"
MERGED_HASH="$(git -C "$ROOT" rev-parse "$REF:$REL")"
if [[ "$LOCAL_HASH" != "$MERGED_HASH" ]]; then
  echo "calibration_receipt_merged_check: $REL differs from the merged content on $REF — refusing to score a modified copy" >&2
  exit 4
fi

exit 0
