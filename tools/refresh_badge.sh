#!/usr/bin/env bash
# Regenerate the live earned-autonomy badge from the reference ledger and push
# to gh-pages IF it changed. A stale badge is a fake-green; this keeps it honest.
# Intended for cron. Requires: signalbrain clone with gh-pages worktree access.
set -euo pipefail

SB="${SB_REPO:-$HOME/signalbrain}"
LEDGER="${SB_LEDGER:-$HOME/neural-chat-v3/docs/calibration/improvement_claim_ledger.jsonl}"
PAGES_WT="${SB_PAGES_WT:-/tmp/sb-badge-wt}"

[ -d "$PAGES_WT/.git" ] || git -C "$SB" worktree add "$PAGES_WT" gh-pages 2>/dev/null || true
git -C "$PAGES_WT" pull -q origin gh-pages || true

mkdir -p "$PAGES_WT/badge"
python3 "$SB/tools/make_badge.py" "$LEDGER" 10 > "$PAGES_WT/badge/titan.json.new"
if ! cmp -s "$PAGES_WT/badge/titan.json.new" "$PAGES_WT/badge/titan.json" 2>/dev/null; then
  mv "$PAGES_WT/badge/titan.json.new" "$PAGES_WT/badge/titan.json"
  git -C "$PAGES_WT" add badge/titan.json
  git -C "$PAGES_WT" -c user.email=badge@signalbrain.ai -c user.name=badge-bot \
    commit -qm "badge: refresh from reference ledger ($(date -u +%FT%TZ))"
  git -C "$PAGES_WT" push -q origin gh-pages
  echo "badge updated"
else
  rm -f "$PAGES_WT/badge/titan.json.new"
  echo "badge unchanged"
fi
