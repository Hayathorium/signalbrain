#!/usr/bin/env python3
"""Record a paced-audit run as an SPC run-summary for cross-run control charts.

`scripts/stress_100q_batch.py` writes per-query JSONL (one object per line);
`scripts/spc_control_chart.py` consumes per-RUN summaries (one JSON object with an
``overall`` metrics dict). This harness bridges them: it aggregates the trial
JSONLs of one audit into the eval_matrix ``overall`` summary (SPC-compatible:
``withhold_rate``, ``grounded_share``, ``latency_p50_ms`` …), stamps it with
date + git sha + label, and writes a timestamped run-summary under the runs dir.

Then track quality across audits:
    python scripts/spc_record_run.py --label post-activation t1.jsonl t2.jsonl t3.jsonl
    python scripts/spc_control_chart.py analyze docs/eval_runs/*.json
which flags Western-Electric regressions on the latest point against the baseline.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_matrix import aggregate_trials, metrics_for_trial  # noqa: E402
import epistemic_honesty as _eh  # noqa: E402


def _honesty_band(trials: list[list[dict]]) -> dict | None:
    """Mean±stdev epistemic-honesty across trials, computed from the raw per-query records
    via the stress adapter (Phase C v2). None if no records."""
    valid = [t for t in trials if t and metrics_for_trial(t)["valid_trial"]]
    per_trial = [_eh.honesty_from_stress_records(t) for t in valid if t]
    if not per_trial:
        return None
    mean = sum(per_trial) / len(per_trial)
    var = sum((x - mean) ** 2 for x in per_trial) / len(per_trial)
    return {"mean": round(mean, 4), "stdev": round(var ** 0.5, 4), "n": len(per_trial)}


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def _read_trial(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_summary(trial_paths: list[str], *, label: str, date: str, git_sha: str) -> dict:
    """Aggregate per-trial JSONLs into an SPC-compatible run-summary."""
    trials = [_read_trial(p) for p in trial_paths]
    summary = aggregate_trials(trials)
    # Phase C v2: emit the real epistemic-honesty signal from the raw records so the proposer's
    # feedback uses it (via auditability_from_overall) instead of the grounded/governed proxy.
    band = _honesty_band(trials)
    if band is not None:
        summary.setdefault("overall", {})["epistemic_honesty"] = band
    summary["run"] = {"label": label, "date": date, "git_sha": git_sha, "trials": len(trials)}
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record an audit run as an SPC run-summary.")
    ap.add_argument("trials", nargs="+", help="per-trial stress JSONL files")
    ap.add_argument("--label", default="run")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--git-sha", default=None, help="override git sha")
    ap.add_argument("--out-dir", default="docs/eval_runs")
    args = ap.parse_args(argv)

    date = args.date or time.strftime("%Y-%m-%d")
    sha = args.git_sha or _git_sha()
    summary = build_summary(args.trials, label=args.label, date=date, git_sha=sha)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{date}-{args.label}-{sha}.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
