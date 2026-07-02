#!/usr/bin/env python3
"""Six Sigma defect Pareto + DPMO/sigma by stratum — find the *vital few* causes.

SPC (spc_control_chart.py) tells you *whether* a process is in control over time.
This tells you *where* the defects concentrate: stratify the per-query eval records
(by category, backend route, governor verdict, ...) and rank strata by defect count
with cumulative % — the classic Pareto "80% of defects from 20% of causes" — plus
DPMO + sigma per stratum. The output tells the JIT/admission/prewarm work *where to
aim*.

A "defect" is configurable; the default counts a record as defective when the
response failed (``ok`` false) or the governor rejected it (``governor_verdict``
starting with ``rejected``). Reads the enriched stress_100q records
(``cat``, ``backend``, ``governor_verdict``, ``has_evidence``, ``ok``, ``len``).

Pure + dependency-free. Uses spc_control_chart's sigma if importable; otherwise a
built-in fallback, so this runs standalone.

CLI:
  defect_pareto.py <records.jsonl> [--dim cat|backend|governor_verdict]
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable
from typing import Any

DefectPredicate = Callable[[dict[str, Any]], bool]


def _dpmo(defects: int, opportunities: int) -> float:
    if opportunities <= 0:
        return 0.0
    return (float(defects) / float(opportunities)) * 1_000_000.0


def _sigma_level(dpmo_value: float) -> float:
    """Process sigma from DPMO (1.5-shift). Prefers spc_control_chart's precise
    implementation; falls back to a built-in inverse-normal so this is standalone."""
    try:
        from spc_control_chart import sigma_level  # type: ignore

        return sigma_level(dpmo_value)
    except Exception:
        pass
    d = max(0.0, min(1_000_000.0, float(dpmo_value)))
    y = 1.0 - d / 1_000_000.0
    if y >= 1.0:
        return 6.0
    if y <= 0.0:
        return 0.0
    # Acklam inverse-normal (central + tails) + 1.5 shift
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    dd = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if y < plow:
        q = math.sqrt(-2 * math.log(y))
        z = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    elif y > phigh:
        q = math.sqrt(-2 * math.log(1 - y))
        z = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    else:
        q = y - 0.5
        r = q * q
        z = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    return round(z + 1.5, 2)


def default_defect_predicate(record: dict[str, Any]) -> bool:
    """A record is defective if the call failed or the governor rejected the answer."""
    if record.get("ok") is False:
        return True
    verdict = str(record.get("governor_verdict") or "")
    return verdict.startswith("rejected")


def stratify(records: list[dict[str, Any]], dim: str,
             predicate: DefectPredicate | None = None) -> dict[str, dict[str, int]]:
    """Per-stratum opportunities + defects for one dimension."""
    pred = predicate or default_defect_predicate
    strata: dict[str, dict[str, int]] = {}
    for r in records:
        key = str(r.get(dim, "?"))
        cell = strata.setdefault(key, {"opportunities": 0, "defects": 0})
        cell["opportunities"] += 1
        if pred(r):
            cell["defects"] += 1
    return strata


def pareto(strata: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    """Rank strata by defect count (desc), with cumulative % and a vital-few flag
    (the leading strata that together account for <=80% of all defects)."""
    rows = []
    total_defects = sum(c["defects"] for c in strata.values())
    ordered = sorted(strata.items(), key=lambda kv: (-kv[1]["defects"], kv[0]))
    cum = 0
    for stratum, c in ordered:
        opp, dfc = c["opportunities"], c["defects"]
        cum += dfc
        cum_pct = (cum / total_defects * 100.0) if total_defects else 0.0
        prev_pct = ((cum - dfc) / total_defects * 100.0) if total_defects else 0.0
        rows.append({
            "stratum": stratum,
            "opportunities": opp,
            "defects": dfc,
            "defect_rate": round(dfc / opp, 4) if opp else 0.0,
            "dpmo": round(_dpmo(dfc, opp), 1),
            "sigma": _sigma_level(_dpmo(dfc, opp)),
            "cum_defect_pct": round(cum_pct, 1),
            # vital-few: contributes to the first 80% of defects (always include the
            # top contributor even if it alone exceeds 80%)
            "vital_few": dfc > 0 and (prev_pct < 80.0),
        })
    return rows


def analyze(records: list[dict[str, Any]], *, dims: list[str] | None = None,
            predicate: DefectPredicate | None = None) -> dict[str, Any]:
    dims = dims or ["cat", "backend", "governor_verdict"]
    n = len(records)
    total_defects = sum(1 for r in records if (predicate or default_defect_predicate)(r))
    out: dict[str, Any] = {
        "records": n,
        "total_defects": total_defects,
        "overall_dpmo": round(_dpmo(total_defects, n), 1),
        "overall_sigma": _sigma_level(_dpmo(total_defects, n)),
        "by_dim": {},
    }
    for dim in dims:
        if any(dim in r for r in records):
            out["by_dim"][dim] = pareto(stratify(records, dim, predicate))
    return out


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: defect_pareto.py <records.jsonl> [--dim cat]", file=sys.stderr)
        return 2
    path = argv[1]
    dims = None
    if "--dim" in argv:
        dims = [argv[argv.index("--dim") + 1]]
    print(json.dumps(analyze(_load_jsonl(path), dims=dims), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
