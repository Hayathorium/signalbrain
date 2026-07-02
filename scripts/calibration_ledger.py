#!/usr/bin/env python3
"""Calibration ledger: scores improvement-claim confidence against actual outcome.

CLI wrapper around ``agi_os_backend.governance.calibration_ledger_core``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agi_os_backend.governance.calibration_ledger_core import (  # noqa: E402
    DEFAULT_MIN_HIT_RATE,
    HIGH_CONFIDENCE_THRESHOLD,
    MIN_TRACK_RECORD,
    class_auto_merge_status,
    filter_rows,
    high_confidence_hit_rate,
    is_goodhart_excluded_row,
    load_rows,
)


def report(rows, window=None, require_measured=False, by_class=False):
    n = len(rows)
    if not n:
        print("  claims=0  (empty ledger)")
        return 0.0
    held = sum(1 for r in rows if r["held"])
    brier = sum((r["confidence"] - (1.0 if r["held"] else 0.0)) ** 2 for r in rows) / n if n else 0.0
    over = [r for r in rows if r["confidence"] >= HIGH_CONFIDENCE_THRESHOLD and not r["held"]]
    print(f"  claims={n}  held={held}/{n} ({held/n:.0%})  Brier={brier:.3f} (0=perfect, lower better)")
    print(
        f"  high-confidence (>={HIGH_CONFIDENCE_THRESHOLD}) claims that FAILED: "
        f"{len(over)}/{sum(1 for r in rows if r['confidence']>=HIGH_CONFIDENCE_THRESHOLD)}  <- overconfidence signal"
    )
    for r in over:
        print(f"    OVERCONFIDENT {r['confidence']}: {r['claim'][:48]!r} (caught by {r['caught_by']})")
    # Trust rate excludes tautological invariant-pins (genuine improvement claims only).
    rate, _ = high_confidence_hit_rate(filter_rows(rows))
    verdict = "TRUST" if rate >= DEFAULT_MIN_HIT_RATE else "GATE — calibration too low for autonomy"
    print(f"  high-confidence hit-rate={rate:.0%}  -> autonomy verdict: {verdict}")

    if window:
        scoped = filter_rows(rows, window=window)
        r_rate, r_n = high_confidence_hit_rate(scoped)
        print(
            f"  [recency window={window}] high-confidence hit-rate={r_rate:.0%} (n={r_n}) "
            f"— recent calibration; past failures fade as verified claims accumulate"
        )
    if require_measured:
        measured = filter_rows(rows, require_measured=True)
        m_rate, m_n = high_confidence_hit_rate(measured)
        print(
            f"  [measured-only] high-confidence hit-rate={m_rate:.0%} (n={m_n}) "
            f"— self-reported holds excluded (anti-gaming integrity anchor)"
        )
    if by_class:
        statuses = class_auto_merge_status(
            rows,
            require_measured=require_measured,
            window=window,
            exclude_goodhart=True,
        )
        print("  [per change-class auto-merge gate (graduated autonomy)]")
        if not statuses:
            print("    (no high-confidence classified claims in scope)")
        for name, row in statuses.items():
            print(f"    {name}: hit-rate={row['hit_rate']:.0%} n={row['n']} -> {row['status']}")
    excluded = sum(1 for r in rows if is_goodhart_excluded_row(r))
    if excluded:
        print(
            f"  [goodhart-excluded] {excluded} trust-pin row(s) omitted from autonomy gate "
            f"(existence-only pins cannot earn TRUST)"
        )
    return brier


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger", nargs="?", default="ledger.jsonl")
    ap.add_argument("--window", type=int, default=None)
    ap.add_argument("--require-measured", action="store_true")
    ap.add_argument("--by-class", action="store_true")
    a = ap.parse_args()
    report(load_rows(Path(a.ledger)), window=a.window, require_measured=a.require_measured, by_class=a.by_class)
