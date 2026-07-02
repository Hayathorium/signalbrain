#!/usr/bin/env python3
"""Statistical Process Control (SPC) for the Titan eval-matrix — the Six Sigma
"Measure + Control" layer on top of the variance bands.

`eval_matrix.py` aggregates trials into mean±stdev bands so a single A/B delta can
be judged signal-vs-noise. This goes the next step: track a metric ACROSS RUNS as
a control chart and decide whether the process is *in control* (only common-cause
noise) or *out of control* (a real special-cause shift — a regression or a win).

Pure, dependency-free, deterministic:
  - control_limits(values, k)        -> mean / stdev / UCL / LCL (k-sigma)
  - western_electric_violations(...) -> the classic out-of-control detectors
  - dpmo(defects, opportunities)     -> defects per million opportunities
  - sigma_level(dpmo)                -> process sigma (1.5-shift convention)
  - analyze_series(runs, metrics)    -> per-metric chart + violations + verdict

CLI:
  spc_control_chart.py analyze a.json b.json c.json ...   # eval_matrix outputs, oldest->newest
  spc_control_chart.py gate a.json b.json ... --metric determinism_score --floor 0.90
                                                          # exit 0 = pass, 1 = adverse shift/floor breach
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from typing import Any

# Metrics where a control-chart breach matters. Direction = which way is "bad"
# (for annotating a violation as regression vs improvement).
DEFAULT_METRICS = {
    "withhold_rate": "lower_better",
    "grounded_share": "higher_better",
    "governed_share": "higher_better",
    "deterministic_share": "higher_better",
    "light_llm_share": "lower_better",
    "latency_p50_ms": "lower_better",
    "latency_avg_ms": "lower_better",
    # Inference-stability probe (scripts/inference_determinism_probe.py): modal
    # cluster fraction over N identical temp-0 requests. 1.0 == perfectly
    # deterministic. Distinct from deterministic_share (audit fastpath share).
    "determinism_score": "higher_better",
    # Light->heavy escalation health (PRs #402-#404): a sustained escalated_share
    # rise means the light tier is degrading; a rescue-rate drop means the heavy
    # fallback is no longer saving the answers that do escalate.
    "escalated_share": "lower_better",
    "escalation_rescue_rate": "higher_better",
}


def control_limits(values: list[float], *, k: float = 3.0) -> dict[str, float]:
    """Center line + k-sigma control limits for a metric series. Uses the sample
    standard deviation; with <2 points stdev is 0 (limits collapse to the mean)."""
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "stdev": 0.0, "ucl": 0.0, "lcl": 0.0, "n": 0}
    mean = statistics.fmean(values)
    stdev = statistics.stdev(values) if n >= 2 else 0.0
    return {
        "mean": mean,
        "stdev": stdev,
        "ucl": mean + k * stdev,
        "lcl": mean - k * stdev,
        "n": n,
    }


def western_electric_violations(values: list[float], limits: dict[str, float]) -> list[dict[str, Any]]:
    """Classic Western Electric out-of-control rules (subset that needs no
    subgrouping):
      R1: any point beyond 3-sigma (the control limits).
      R2: 8 consecutive points on the same side of the center line.
      R3: 6 consecutive points steadily increasing or decreasing (trend).
      R4: 2 of 3 consecutive points beyond 2-sigma on the same side.
    A flat process (stdev 0) only ever triggers R2/R3 trivially-not, so it returns
    no violations — correct: no variation, nothing special-cause."""
    out: list[dict[str, Any]] = []
    mean = limits["mean"]
    stdev = limits["stdev"]
    ucl, lcl = limits["ucl"], limits["lcl"]
    n = len(values)
    if n == 0:
        return out

    # R1 — beyond 3-sigma; on a zero-variation baseline ANY deviation is special-cause
    if stdev > 0:
        for i, v in enumerate(values):
            if v > ucl or v < lcl:
                out.append({"rule": "R1", "index": i, "value": v,
                            "description": "point beyond 3-sigma control limit"})
    else:
        for i, v in enumerate(values):
            if v != mean:
                out.append({"rule": "R1", "index": i, "value": v,
                            "description": "deviation from a zero-variation baseline"})

    # R2 — 8 in a row same side of center
    run_side = 0
    run_len = 0
    for i, v in enumerate(values):
        side = 1 if v > mean else (-1 if v < mean else 0)
        if side != 0 and side == run_side:
            run_len += 1
        else:
            run_side, run_len = side, (1 if side != 0 else 0)
        if run_len >= 8:
            out.append({"rule": "R2", "index": i, "value": v,
                        "description": "8 consecutive points on one side of center"})

    # R3 — 6 monotonic
    inc = dec = 1
    for i in range(1, n):
        if values[i] > values[i - 1]:
            inc += 1
            dec = 1
        elif values[i] < values[i - 1]:
            dec += 1
            inc = 1
        else:
            inc = dec = 1
        if inc >= 6 or dec >= 6:
            out.append({"rule": "R3", "index": i, "value": values[i],
                        "description": "6 consecutive points trending one direction"})

    # R4 — 2 of 3 beyond 2-sigma same side
    if stdev > 0:
        two_up, two_dn = mean + 2 * stdev, mean - 2 * stdev
        for i in range(2, n):
            window = values[i - 2 : i + 1]
            up = sum(1 for v in window if v > two_up)
            dn = sum(1 for v in window if v < two_dn)
            if up >= 2 or dn >= 2:
                out.append({"rule": "R4", "index": i, "value": values[i],
                            "description": "2 of 3 consecutive beyond 2-sigma (same side)"})
    return out


def dpmo(defects: int, opportunities: int) -> float:
    """Defects Per Million Opportunities."""
    if opportunities <= 0:
        return 0.0
    return (float(defects) / float(opportunities)) * 1_000_000.0


def _inv_norm_cdf(p: float) -> float:
    """Acklam's rational approximation of the inverse normal CDF (pure-python, no
    scipy). Accurate to ~1e-9 in the central region; clamped at the tails."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def sigma_level(dpmo_value: float) -> float:
    """Process sigma from DPMO using the standard 1.5-sigma long-term shift
    convention (so 3.4 DPMO -> ~6.0 sigma, 66807 -> ~3.0). Monotonically
    decreasing in DPMO."""
    dpmo_value = max(0.0, min(1_000_000.0, float(dpmo_value)))
    yield_ = 1.0 - dpmo_value / 1_000_000.0
    if yield_ >= 1.0:
        return 6.0  # cap; effectively defect-free at this sample size
    if yield_ <= 0.0:
        return 0.0
    return round(_inv_norm_cdf(yield_) + 1.5, 2)


def _metric_mean(run: dict[str, Any], metric: str) -> float | None:
    overall = run.get("overall") if isinstance(run.get("overall"), dict) else run
    cell = overall.get(metric)
    if isinstance(cell, dict):
        return float(cell.get("mean", 0.0) or 0.0)
    if isinstance(cell, (int, float)):
        return float(cell)
    return None


def analyze_series(runs: list[dict[str, Any]], *, metrics: dict[str, str] | None = None,
                   k: float = 3.0) -> dict[str, Any]:
    """Given eval_matrix outputs in chronological order (oldest->newest), build a
    control chart per metric and flag out-of-control signals on the LATEST point."""
    metrics = metrics or DEFAULT_METRICS
    result: dict[str, Any] = {"runs": len(runs), "metrics": {}, "in_control": True}
    for metric, direction in metrics.items():
        series = [v for v in (_metric_mean(r, metric) for r in runs) if v is not None]
        if not series:
            continue
        # Phase-2 monitoring: establish limits from the baseline (all prior points)
        # and test the latest point against them, so a fresh regression cannot
        # inflate its own control limits and hide. With <4 points there is no
        # stable baseline yet, so fall back to the full series (Phase-1).
        baseline = series[:-1] if len(series) >= 4 else series
        limits = control_limits(baseline, k=k)
        violations = western_electric_violations(series, limits)
        latest_idx = len(series) - 1
        latest_violations = [v for v in violations if v["index"] == latest_idx]
        if latest_violations:
            result["in_control"] = False
        result["metrics"][metric] = {
            "direction": direction,
            "series": series,
            "limits": limits,
            "violations": violations,
            "latest": series[-1],
            "latest_out_of_control": bool(latest_violations),
        }
    return result


def gate_metric(runs: list[dict[str, Any]], metric: str, *, direction: str | None = None,
                k: float = 3.0, floor: float | None = None,
                min_baseline: int = 4, baseline_window: int = 30) -> dict[str, Any]:
    """Fail-closed gate on a single metric: the latest run must (a) not be an
    ADVERSE out-of-control point against the prior-runs baseline, and (b) clear
    the absolute floor when one is given.

    Direction-aware: a control-limit breach on the GOOD side (e.g. a
    higher_better metric spiking above UCL) is a win, not a gate failure. With
    fewer than ``min_baseline`` runs there is no stable baseline, so only the
    floor applies (reported via ``insufficient_baseline``).

    ``baseline_window`` caps the reference distribution to the most recent N
    prior runs: an unbounded baseline lets a months-old regime dominate the
    limits and slowly absorbs drift; a windowed baseline keeps the center
    line representative of the current operating regime."""
    direction = direction or DEFAULT_METRICS.get(metric, "higher_better")
    series = [v for v in (_metric_mean(r, metric) for r in runs) if v is not None]
    verdict: dict[str, Any] = {
        "metric": metric,
        "direction": direction,
        "series": series,
        "floor": floor,
        "baseline_window": baseline_window,
        "insufficient_baseline": len(series) < min_baseline,
        "passed": True,
        "reasons": [],
    }
    if not series:
        verdict["passed"] = False
        verdict["reasons"].append(f"no '{metric}' values found in the supplied runs")
        return verdict

    latest = series[-1]
    verdict["latest"] = latest

    if floor is not None:
        breached = latest < floor if direction == "higher_better" else latest > floor
        if breached:
            verdict["passed"] = False
            verdict["reasons"].append(
                f"latest {metric}={latest} breaches absolute floor {floor} ({direction})")

    if not verdict["insufficient_baseline"]:
        baseline = series[:-1][-max(baseline_window, 1):]
        limits = control_limits(baseline, k=k)
        verdict["limits"] = limits
        latest_idx = len(series) - 1
        bad_side_high = direction == "lower_better"
        for v in western_electric_violations(series, limits):
            if v["index"] != latest_idx:
                continue
            adverse = latest > limits["mean"] if bad_side_high else latest < limits["mean"]
            if adverse:
                verdict["passed"] = False
                verdict["reasons"].append(
                    f"latest point out of control ({v['rule']}: {v['description']}) "
                    f"on the adverse side of center")
            else:
                verdict.setdefault("favorable_signals", []).append(v["rule"])
    return verdict


def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "analyze":
        runs = [_load(p) for p in argv[2:]]
        print(json.dumps(analyze_series(runs), indent=2))
        return 0

    if len(argv) >= 3 and argv[1] == "gate":
        metric = "determinism_score"
        floor: float | None = None
        k = 3.0
        baseline_window = 30
        paths: list[str] = []
        args = argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--metric" and i + 1 < len(args):
                metric = args[i + 1]
                i += 2
            elif args[i] == "--floor" and i + 1 < len(args):
                floor = float(args[i + 1])
                i += 2
            elif args[i] == "--k" and i + 1 < len(args):
                k = float(args[i + 1])
                i += 2
            elif args[i] == "--baseline-window" and i + 1 < len(args):
                baseline_window = int(args[i + 1])
                i += 2
            else:
                paths.append(args[i])
                i += 1
        if not paths:
            print("usage: spc_control_chart.py gate <run1.json> ... [--metric M] [--floor F] "
                  "[--k K] [--baseline-window N]",
                  file=sys.stderr)
            return 2
        verdict = gate_metric([_load(p) for p in paths], metric, k=k, floor=floor,
                              baseline_window=baseline_window)
        print(json.dumps(verdict, indent=2))
        return 0 if verdict["passed"] else 1

    print("usage: spc_control_chart.py {analyze|gate} <run1.json> <run2.json> ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
