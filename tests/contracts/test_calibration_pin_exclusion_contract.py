"""Contract: invariant-pins are excluded from every trust computation.

Closes a calibration-gate gaming hole. On 2026-06-28 a batch of 19 tautological
"invariant pins" (claims that pass by construction — e.g. "kill-switch file
present") named ``calibration-trust-pin-NN`` were scored ``held=true`` and, with
``TITAN_CALIBRATION_WINDOW=20``, filled the recency window to 100% -> TRUST ->
``autonomy_widening_allowed=True``. But pins are NOT improvement claims; the
trust gate exists to measure whether genuine high-confidence IMPROVEMENT
predictions hold. This contract pins the fix: invariant-pins are excluded by
default from ``filter_rows`` (before windowing), so a batch of pins can never
force TRUST. Genuine calibration here was ~50%, which is the honest number.

CI-safe: pure python, synthetic ledger rows, no network / no brain.
"""

from agi_os_backend.governance.calibration_ledger_core import (
    calibration_verdict,
    class_auto_merge_status,
    filter_rows,
    is_invariant_pin,
)


def test_is_invariant_pin_true_for_legacy_naming():
    assert is_invariant_pin({"claim": "0481-calibration-trust-pin-01"}) is True


def test_is_invariant_pin_true_for_claim_kind():
    assert is_invariant_pin({"claim_kind": "invariant_pin"}) is True


def test_is_invariant_pin_false_for_genuine_claim():
    assert is_invariant_pin({"claim": "0479-calibration-lane-plumbing-fix"}) is False


def _synthetic_ledger():
    """19 invariant-pins (held) + 12 genuine improvement claims (6 held).

    All high-confidence (0.9) and ``scored_by=measured`` so the only thing that
    moves the hit-rate is whether pins are excluded.
    """
    rows = []
    for i in range(1, 20):
        rows.append(
            {
                "claim": f"0481-calibration-trust-pin-{i:02d}",
                "confidence": 0.9,
                "held": True,
                "scored_by": "measured",
            }
        )
    for i in range(1, 13):
        rows.append(
            {
                "claim": f"0479-genuine-improvement-claim-{i:02d}",
                "confidence": 0.9,
                "held": i <= 6,  # 6 of 12 hold -> 50%
                "scored_by": "measured",
            }
        )
    return rows


def test_pins_cannot_force_trust():
    """THE anti-gaming test: 19 held pins must not pad window=20 to TRUST.

    With pins excluded, the window=20 recency view is the 12 genuine claims at
    6/12 = 50%, well below the 95% trust threshold -> GATE.
    """
    rows = _synthetic_ledger()
    verdict = calibration_verdict(rows, require_measured=True, window=20)
    assert verdict["verdict"] == "GATE", verdict
    rate = verdict["high_confidence_hit_rate"]
    assert 0.45 <= rate <= 0.55, f"expected honest ~50% genuine calibration, got {rate}"


def test_filter_rows_opt_out_includes_pins():
    rows = _synthetic_ledger()
    with_pins = filter_rows(rows, exclude_invariant_pins=False)
    assert len(with_pins) == len(rows)
    assert any(is_invariant_pin(r) for r in with_pins)


def test_filter_rows_default_excludes_pins():
    rows = _synthetic_ledger()
    default = filter_rows(rows)
    assert len(default) == 12
    assert not any(is_invariant_pin(r) for r in default)


def test_class_auto_merge_status_excludes_pins():
    """No class should reach auto-merge ELIGIBLE purely from tautological pins.

    Pins carry a ``change_class`` and held=true; if they were counted, that class
    could cross the 95% / track-record bar on pins alone. With exclusion, the only
    high-confidence claims left are the genuine 50% set.
    """
    rows = _synthetic_ledger()
    for r in rows:
        r["change_class"] = "governance"
    status = class_auto_merge_status(rows, require_measured=True, window=20)
    for name, info in status.items():
        assert "ELIGIBLE" not in info["status"], (name, info)
