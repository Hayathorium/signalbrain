"""Contract: per-class auto-merge gate windows recency PER CLASS, not globally.

With a single window shared across the whole ledger, scoring a burst of claims
in one class evicted other classes' recent rows from the gate's view — observed
2026-07-02, when four legitimate post-merge tooling scores shrank bugfix from
auto-merge ELIGIBLE (100%, n=10) to GATE (n=6) without any bugfix evidence
changing. The graduated-autonomy invariant: a class's standing moves only on
evidence about that class.

- A burst of claims in class A must not change class B's hit-rate, n, or status.
- The window still applies within a class (old failures age out only as that
  class accumulates newer claims).
- Pins/goodhart-excluded rows stay excluded before any windowing.
"""

from __future__ import annotations

from agi_os_backend.governance.calibration_ledger_core import class_auto_merge_status


def _row(rid: str, held: bool, change_class: str, confidence: float = 0.9) -> dict:
    return {
        "claim": rid,
        "confidence": confidence,
        "held": held,
        "scored_by": "measured",
        "change_class": change_class,
        "receipt_id": rid,
    }


def _bugfix_track_record(n: int = 10) -> list[dict]:
    return [_row(f"bugfix-{i}", True, "bugfix") for i in range(n)]


def test_burst_in_one_class_does_not_evict_another():
    rows = _bugfix_track_record(10)
    baseline = class_auto_merge_status(rows, require_measured=True, window=20)["bugfix"]
    assert baseline["status"] == "auto-merge ELIGIBLE"
    assert baseline["n"] == 10

    # 25 tooling claims scored afterwards — more than the whole window.
    rows_after_burst = rows + [_row(f"tooling-{i}", i % 2 == 0, "tooling") for i in range(25)]
    after = class_auto_merge_status(rows_after_burst, require_measured=True, window=20)["bugfix"]
    assert after == baseline  # bugfix standing unchanged: no bugfix evidence changed


def test_window_still_applies_within_class():
    # 5 old failures, then 20 wins: within-class window of 20 sees only the wins.
    rows = [_row(f"tooling-old-{i}", False, "tooling") for i in range(5)]
    rows += [_row(f"tooling-win-{i}", True, "tooling") for i in range(20)]
    status = class_auto_merge_status(rows, require_measured=True, window=20)["tooling"]
    assert status["n"] == 20
    assert status["hit_rate"] == 1.0
    assert status["status"] == "auto-merge ELIGIBLE"


def test_within_class_failures_do_not_age_out_via_other_classes():
    # An old tooling failure inside the class's own last-20 keeps counting even
    # when OTHER classes add many rows after it — no cross-class laundering.
    rows = [_row("tooling-fail", False, "tooling")]
    rows += [_row(f"tooling-win-{i}", True, "tooling") for i in range(10)]
    rows += [_row(f"bugfix-{i}", True, "bugfix") for i in range(30)]
    status = class_auto_merge_status(rows, require_measured=True, window=20)["tooling"]
    assert status["n"] == 11
    assert status["hit_rate"] < 0.95
    assert "GATE" in status["status"]


def test_pins_still_excluded_before_windowing():
    rows = _bugfix_track_record(5)
    rows += [_row(f"0481-calibration-trust-pin-{i:02d}", True, "bugfix") for i in range(10)]
    status = class_auto_merge_status(rows, require_measured=True, window=20)["bugfix"]
    assert status["n"] == 5  # pins cannot pad a class to ELIGIBLE
    assert "GATE" in status["status"]
