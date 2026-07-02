#!/usr/bin/env python3
"""Eval-matrix scoreboard for the Titan 100-query audit.

Why this exists: a single 100q run carries enough backend-routing noise that a
real quality improvement can be masked by it. Diffing the post-#291 baseline
against the prior run showed 3 genuine recoveries swamped by 8 queries that
flipped ``fallback`` <-> ``light_llm`` on pure timing variance — a net "+5
withholds" that was noise, not regression. This tool aggregates *multiple* trial
runs into per-category and overall metrics with variance bands (mean +/- stdev
across trials), so a delta can be judged signal-vs-noise instead of guessed.

Subcommands:
  analyze <trial.jsonl> [trial2.jsonl ...]   -> metrics JSON (stdout) + human table (stderr)
  delta   <baseline.json> <current.json>     -> per-metric delta + significance flag

A "trial" is one JSONL produced by stress_100q_batch.py (one full 100q run).
Pass 3+ trials of the same build to get a stable variance band.
"""
from __future__ import annotations

import json
import statistics
import sys

WITHHOLD_MARKER = "do not have enough verified evidence"
WITHHOLD_LEN = 119  # the canonical governor-withhold message length
LIGHT_LLM_METHODS = {"light_llm", "llm_light", "brain_light"}


def _get(row: dict, *keys, default=None):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return default


def _is_withhold(row: dict) -> bool:
    preview = str(_get(row, "preview", "answer", default="") or "")
    if WITHHOLD_MARKER in preview.lower():
        return True
    length = _get(row, "len", "length")
    return length == WITHHOLD_LEN


def _is_rate_limited(row: dict) -> bool:
    status = _get(row, "status")
    return status == 429 or status == "429"


def _backend(row: dict) -> str:
    return str(_get(row, "backend", "strategy", default="?") or "?")


def _method(row: dict) -> str:
    method = _get(row, "method")
    if method is None:
        meta = _get(row, "metadata", "meta")
        if isinstance(meta, dict):
            method = meta.get("method")
    return str(method or "").strip().lower()


def _llm_skipped_row(row: dict) -> bool:
    v = _get(row, "llm_skipped")
    if v is not None:
        return v is True
    b = _backend(row).strip().lower()
    m = _method(row)
    if m in ("worldindex_recall", "rmq_range_max", "cosine_semantic_recall", "zero_marginal"):
        return True
    if m.startswith("zero_marginal_"):
        return True
    if b.startswith("deterministic_") or b.startswith("worldindex_"):
        return True
    if b in ("fallback", "light_llm", "light_llm_escalated", "brain_light", "llm_light"):
        return False
    if m in ("fallback", "light_llm", "light_llm_escalated", "brain_light", "llm_light"):
        return False
    return False


def _recall_source_row(row: dict) -> str | None:
    src = _get(row, "recall_source")
    if src:
        return str(src)
    m = _method(row)
    if m == "worldindex_recall":
        return "exact"
    if m == "rmq_range_max":
        return "rmq"
    if m == "cosine_semantic_recall":
        return "cosine"
    return None


def _is_light_llm_lane(row: dict) -> bool:
    backend = _backend(row).strip().lower()
    if backend in LIGHT_LLM_METHODS:
        return True
    return _method(row) in LIGHT_LLM_METHODS


def _is_escalated(row: dict) -> bool:
    """Light->heavy escalation marker (PRs #402-#404): either the routed
    backend/method is the escalated variant, or the response metadata carries
    ``escalated: true`` (layer3 BrainResult propagates it)."""
    if _backend(row) == "light_llm_escalated" or _method(row) == "light_llm_escalated":
        return True
    if _get(row, "escalated") is True:
        return True
    meta = _get(row, "metadata", "meta")
    return bool(isinstance(meta, dict) and meta.get("escalated") is True)


def _intelligence_density(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    good = sum(
        1
        for r in rows
        if str(_get(r, "governor_verdict", default="")) == "authorized"
        and _get(r, "has_evidence") is True
    )
    compute_s = sum(float(_get(r, "ms", "latency_ms", default=0.0) or 0.0) for r in rows) / 1000.0
    return round(good / compute_s, 4) if compute_s > 0 else 0.0


def metrics_for_trial(rows: list[dict]) -> dict:
    """Scalar metrics for one trial (one full run). All rates are 0..1."""
    n = len(rows) or 1
    backends = [_backend(r) for r in rows]
    withholds = [r for r in rows if _is_withhold(r)]
    latencies = [float(_get(r, "ms", "latency_ms", default=0.0) or 0.0) for r in rows]
    governed = [r for r in rows if str(_get(r, "governance_mode", default="")).startswith(("governed", "cognitive"))]
    grounded = [r for r in rows if _get(r, "has_evidence") is True]
    escalated = [r for r in rows if _is_escalated(r)]
    # Rescue = escalation produced a real answer (ok, not a withhold). With zero
    # escalations the rate is vacuously 1.0 (no failed rescues); read it together
    # with escalated_share, which says whether escalation was exercised at all.
    rescued = [r for r in escalated if _get(r, "ok") and not _is_withhold(r)]
    rate_limited = [r for r in rows if _is_rate_limited(r)]
    rate_limited_rate = len(rate_limited) / n
    skip_llm = [r for r in rows if _llm_skipped_row(r)]
    recall_exact = sum(1 for r in rows if _recall_source_row(r) == "exact")
    recall_rmq = sum(1 for r in rows if _recall_source_row(r) == "rmq")
    recall_cosine = sum(1 for r in rows if _recall_source_row(r) == "cosine")
    return {
        "n": len(rows),
        "ok_rate": sum(1 for r in rows if _get(r, "ok")) / n,
        "rate_limited_rate": rate_limited_rate,
        "valid_trial": rate_limited_rate == 0.0,
        "withhold_rate": len(withholds) / n,
        "skip_llm_rate": len(skip_llm) / n,
        "recall_hit_rate_exact": recall_exact / n,
        "recall_hit_rate_rmq": recall_rmq / n,
        "recall_hit_rate_cosine": recall_cosine / n,
        "intelligence_density": _intelligence_density(rows),
        "light_llm_share": sum(1 for r in rows if _is_light_llm_lane(r)) / n,
        "deterministic_share": sum(1 for b in backends if b.startswith("deterministic_")) / n,
        "fallback_share": sum(1 for b in backends if b == "fallback") / n,
        "governed_share": len(governed) / n,
        "grounded_share": len(grounded) / n,
        "escalated_share": len(escalated) / n,
        "escalation_rescue_rate": (len(rescued) / len(escalated)) if escalated else 1.0,
        "latency_avg_ms": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
    }


def metrics_by_category(rows: list[dict]) -> dict:
    cats: dict[str, list[dict]] = {}
    for r in rows:
        cats.setdefault(str(_get(r, "cat", "category", default="?")), []).append(r)
    return {c: metrics_for_trial(rs) for c, rs in sorted(cats.items())}


def _band(values: list[float]) -> dict:
    """mean / stdev / n band for one metric across trials."""
    if not values:
        return {"mean": 0.0, "stdev": 0.0, "n": 0}
    return {
        "mean": round(statistics.fmean(values), 4),
        "stdev": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        "n": len(values),
    }


def aggregate_trials(trials: list[list[dict]]) -> dict:
    """Aggregate per-trial metrics into mean +/- stdev bands across trials."""
    per_trial = [metrics_for_trial(t) for t in trials]
    keys = [
        k
        for k in (per_trial[0] if per_trial else {})
        if k not in ("n", "valid_trial")
    ]
    invalid_indices = [i for i, pt in enumerate(per_trial) if not pt.get("valid_trial", True)]
    valid_indices = [i for i, pt in enumerate(per_trial) if pt.get("valid_trial", True)]
    band_trials = [per_trial[i] for i in valid_indices]
    overall = (
        {k: _band([float(pt[k]) for pt in band_trials]) for k in keys}
        if band_trials
        else {k: {"mean": 0.0, "stdev": 0.0, "n": 0} for k in keys}
    )
    # Per-category bands — valid trials only so HTTP 429 collapse cannot poison SPC.
    cat_trials: dict[str, list[dict]] = {}
    for idx in valid_indices:
        for cat, m in metrics_by_category(trials[idx]).items():
            cat_trials.setdefault(cat, []).append(m)
    by_cat = {}
    for cat, ms in cat_trials.items():
        by_cat[cat] = {k: _band([float(m[k]) for m in ms]) for k in keys}
    return {
        "trials": len(trials),
        "valid_trials": len(valid_indices),
        "invalid_trials": len(invalid_indices),
        "invalid_trial_indices": invalid_indices,
        "single_run_warning": len(valid_indices) < 2,
        "invalid_run_warning": bool(invalid_indices),
        "per_trial": per_trial,
        "overall": overall,
        "by_category": by_cat,
    }


def compute_delta(baseline: dict, current: dict, k_sigma: float = 1.0) -> dict:
    """Per-metric delta with a signal-vs-noise verdict.

    A delta is SIGNAL when |mean_c - mean_b| exceeds k_sigma * the combined
    noise band (stdev_b + stdev_c); otherwise it is within run-to-run NOISE.
    With single-run inputs (stdev 0) every nonzero delta reads as SIGNAL but is
    flagged ``unreliable`` because there is no variance estimate.
    """
    out = {"k_sigma": k_sigma, "metrics": {}}
    b_over, c_over = baseline.get("overall", {}), current.get("overall", {})
    single = baseline.get("single_run_warning") or current.get("single_run_warning")
    for key in sorted(set(b_over) | set(c_over)):
        b, c = b_over.get(key, {}), c_over.get(key, {})
        bm, cm = float(b.get("mean", 0.0)), float(c.get("mean", 0.0))
        band = k_sigma * (float(b.get("stdev", 0.0)) + float(c.get("stdev", 0.0)))
        delta = round(cm - bm, 4)
        verdict = "signal" if abs(delta) > band else "noise"
        out["metrics"][key] = {
            "baseline": bm,
            "current": cm,
            "delta": delta,
            "noise_band": round(band, 4),
            "verdict": verdict,
            "unreliable": bool(single),
        }
    return out


# ── CLI ────────────────────────────────────────────────────────────────────

def _load_jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def _print_table(agg: dict) -> None:
    w = sys.stderr.write
    w(f"\n=== eval matrix ({agg['trials']} trial(s)) ===\n")
    if agg.get("invalid_run_warning"):
        bad = agg.get("invalid_trial_indices") or []
        w(
            f"  ⚠️  {len(bad)} trial(s) excluded from variance bands "
            f"(HTTP 429 rate-limited — indices {bad}). "
            f"Re-run paced: STRESS_PRECOOLDOWN_S=120 STRESS_QUERY_DELAY_S=2.0\n"
        )
    if agg["single_run_warning"]:
        w("  ⚠️  single run — no variance band; deltas are unreliable (run 3+ valid trials)\n")
    w(f"  {'metric':<22} {'mean':>8}  {'± stdev':>8}\n")
    for k, band in agg["overall"].items():
        w(f"  {k:<22} {band['mean']:>8.3f}  {band['stdev']:>8.3f}\n")
    w("\n  withhold_rate by category (mean ± stdev):\n")
    for cat, m in agg["by_category"].items():
        wr = m.get("withhold_rate", {})
        w(f"    {cat:<14} {wr.get('mean', 0):>6.3f} ± {wr.get('stdev', 0):>5.3f}\n")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(__doc__ or "")
        return 2
    cmd = argv[1]
    if cmd == "analyze":
        trials = [_load_jsonl(p) for p in argv[2:]]
        if not trials:
            sys.stderr.write("analyze: need >=1 trial jsonl\n")
            return 2
        agg = aggregate_trials(trials)
        _print_table(agg)
        sys.stdout.write(json.dumps(agg, indent=2) + "\n")
        return 0
    if cmd == "delta":
        if len(argv) != 4:
            sys.stderr.write("delta: need <baseline.json> <current.json>\n")
            return 2
        baseline = json.load(open(argv[2], encoding="utf-8"))
        current = json.load(open(argv[3], encoding="utf-8"))
        d = compute_delta(baseline, current)
        for k, m in d["metrics"].items():
            flag = "⚠️" if m["unreliable"] else ("📈" if m["verdict"] == "signal" else "·")
            sys.stderr.write(
                f"  {flag} {k:<22} {m['baseline']:>7.3f} -> {m['current']:>7.3f}  "
                f"Δ={m['delta']:+.3f} (band ±{m['noise_band']:.3f}) {m['verdict']}\n"
            )
        sys.stdout.write(json.dumps(d, indent=2) + "\n")
        return 0
    sys.stderr.write(f"unknown command: {cmd}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
