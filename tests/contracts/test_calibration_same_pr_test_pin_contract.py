"""Contract: same-PR-only test measures classify as invariant_pin at score time.

Closes the tooling-trust streak gaming hole (2026-07-02): receipts whose
``### How measured`` section runs only pytest targets introduced in the same
merge as the receipt are tautological pins — recorded but trust-excluded.
Also pins merged-receipt guard wiring into ``calibration_score_measured.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from agi_os_backend.governance.calibration_ledger_core import (
    CLAIM_KIND_INVARIANT_PIN,
    is_invariant_pin,
)
from agi_os_backend.governance.calibration_same_pr_pin import (
    is_same_pr_test_only_pin,
    parse_pytest_targets,
)

REPO = Path(__file__).resolve().parents[2]
SCORER = REPO / "scripts" / "calibration_score_measured.py"
MERGED_CHECK = REPO / "scripts" / "calibration_receipt_merged_check.sh"
STREAK_RECEIPTS = (
    "0575-tooling-automerge-receipt-class-footer",
    "0576-tooling-operator-receipt-class-runbook",
    "0577-tooling-supervised-lane-measure-hygiene",
    "0578-tooling-calibration-scorer-inline-env",
    "0579-tooling-calibration-per-class-window",
    "0581-tooling-calibration-rescore-preserves-order",
    "0583-tooling-scorer-receipt-class-footer",
)


def test_scorer_wires_merged_guard_and_same_pr_pin():
    text = SCORER.read_text(encoding="utf-8")
    assert "calibration_receipt_merged_check.sh" in text
    assert "is_same_pr_test_only_pin" in text
    assert "claim_kind" in text
    assert "CLAIM_KIND_INVARIANT_PIN" in text


def test_merged_guard_script_exists():
    assert MERGED_CHECK.is_file()


def test_parse_pytest_targets_node_and_file():
    cmds = [
        [
            "python3",
            "-m",
            "pytest",
            "tests/contracts/test_x.py::test_foo",
            "tests/contracts/test_y.py",
            "-q",
        ]
    ]
    assert parse_pytest_targets(cmds) == [
        ("tests/contracts/test_x.py", "test_foo"),
        ("tests/contracts/test_y.py", None),
    ]


def test_streak_ledger_rows_tagged_invariant_pin():
    ledger = REPO / "docs" / "calibration" / "improvement_claim_ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {str(r.get("receipt_id") or r.get("claim")): r for r in rows}
    for rid in STREAK_RECEIPTS:
        row = by_id[rid]
        assert row.get("claim_kind") == CLAIM_KIND_INVARIANT_PIN, rid
        assert is_invariant_pin(row), rid


def test_audit_self_credit_row_absent():
    ledger = REPO / "docs" / "calibration" / "improvement_claim_ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert not any(
        r.get("receipt_id") == "0575-tooling-automerge-receipt-class-footer-audit" for r in rows
    )


def test_0575_is_same_pr_test_only_pin_on_main():
    receipt = REPO / "docs" / "improvements" / "0575-tooling-automerge-receipt-class-footer.md"
    text = receipt.read_text(encoding="utf-8")
    from scripts.calibration_score_measured import extract_commands_with_env

    _, commands = extract_commands_with_env(text)
    rel = "docs/improvements/0575-tooling-automerge-receipt-class-footer.md"
    assert is_same_pr_test_only_pin(REPO, rel, commands, merged_ref="HEAD")
