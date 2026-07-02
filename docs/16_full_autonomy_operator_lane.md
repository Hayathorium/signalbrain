# Runbook 16 — Full autonomy operator lane (Lucy)

Arm the closed loop: **propose → implement → PR → pr-prep → automerge (docs/tests only) → measure**.
Runtime `.py` still requires **human merge** — see `docs/AUTONOMOUS_MERGE_BOUNDARY.md`.

Prerequisites on Lucy (`~/neural-chat-v3`):

- Brain `/v1/ready` 200 (`TITAN_READINESS_PROFILE=strict` on Lucy)
- `gh auth login` (or `GH_TOKEN` in `.env`) for PR prep / automerge
- **Git fetch over SSH** for unattended cron (HTTPS prompts fail in cron)
- NIM / Ollama reachable for proposer when `NORTHSTAR_USE_NIM=1`

## 1. Sync canonical tree

```bash
cd ~/neural-chat-v3
git fetch origin main
git checkout main
git pull origin main
bash scripts/operator_full_autonomy_bootstrap.sh --production
```

If the tree diverged and you only need scripts:

```bash
git fetch origin main
git checkout origin/main -- scripts/ docs/AUTONOMY_MODES.md docs/runbook/16_full_autonomy_operator_lane.md
```

## 2. SSH remote (required for cron)

Cron runs without a TTY; HTTPS `git fetch` fails with auth errors.

```bash
git remote -v
# If origin is https://github.com/... switch to SSH:
git remote set-url origin git@github.com:whitestone1121-web/neural-chat-v3.git
ssh -T git@github.com   # must succeed once
```

Fetch errors log to `logs/autonomous_fetch.err`.

## 3. Arm active mode + cron

```bash
bash scripts/activate_autonomy_loop.sh --pull --active-agent
bash scripts/start_autonomy_cron.sh
```

This writes active flags into `.env`, creates `.autonomous_dev_armed`, and installs
`run_autonomous_tick_authorized.sh --apply` on the 6h schedule.

Minimum `.env` block (also applied by `merge_autonomy_env.py`):

```bash
AUTONOMOUS_LOOP_MODE=active
AUTONOMOUS_DEV_APPLY=1
AUTONOMOUS_DEV_RUN_PROPOSER=1
AUTONOMOUS_DEV_AUTO_ACCEPT=1
AUTONOMOUS_DEV_AUTO_ROUTE=1
AUTONOMOUS_DEV_PR_PREP=1
AUTONOMOUS_DEV_AUTOMERGE=1
TITAN_AUTOMERGE_REQUIRE_CLASS_ELIGIBLE=1
NORTHSTAR_USE_NIM=1
TITAN_NEMOTRON_ORCHESTRATOR_ENABLED=1
TITAN_AUTONOMY_REQUIRE_CALIBRATION_TRUST=1
```

Optional agent tick (corrigibility tradeoff):

```bash
AUTONOMOUS_AGENT_TICK_AUTHORIZED=1
```

## 4. Manual tick (operator smoke)

```bash
AUTONOMOUS_TICK_INVOKER=operator NORTHSTAR_FULL_REPO_CONTEXT=1 \
  bash scripts/run_autonomous_tick_authorized.sh --apply
```

## 5. Monitor (read-only)

```bash
bash scripts/watch_autonomous_tick.sh
bash scripts/monitor_autonomous_tick.sh
tail -f logs/autonomous_dev_tick-cron.log
```

## 6. Stand down

```bash
bash scripts/deactivate_autonomy_loop.sh
touch AUTONOMOUS_DEV_STOP    # canonical tree kill-switch (tracked)
```

## Failure modes

| Symptom | Fix |
|---------|-----|
| `git fetch origin main failed` | SSH remote (§2), deploy key, or `gh auth` |
| `inference not ready — skipping` | Wait for brain `/v1/ready`; check Ollama/NIM |
| `evidence-gate: validated_at_stale` | pr-prep auto-refreshes timestamp when bundle is otherwise valid |
| `scope gate` on new tests/scripts | pr-prep registers allowlist + manifest |
| Automerge refused on runtime `.py` | Expected — human merge required |
| Calibration GATE blocks widening | `bash scripts/calibration_score_receipt.sh` after human merges |

## 7. Receipt change-class for automerge

Automerge maps each `docs/improvements/*.md` receipt to a calibration change-class for
the class-eligible rail. Resolution order:

1. `## change_class` footer in the receipt body (preferred — explicit operator intent)
2. Filename stem keywords (`fix` → bugfix, `calibration`/`tooling`/`gate` → tooling, etc.)

Example footer (required when stem keywords are ambiguous):

```markdown
## change_class

bugfix
```

If stem and footer disagree, **footer wins**. Score receipts after merge; only measured
**ELIGIBLE** classes auto-merge on docs/tests proposal PRs.

Per-class window defaults to **10** (`TITAN_CALIBRATION_WINDOW`, equals `MIN_TRACK_RECORD`).
Operative widening uses **recency-only** gate when `TITAN_CALIBRATION_RECENCY_GATE=1`
(managed in `.env` via `merge_autonomy_env.py`).

See also: `docs/AUTONOMY_MODES.md`, `docs/AUTONOMOUS_DEV_LOOP.md`, `docs/runbook/15_operator_resume_lane.md`.
