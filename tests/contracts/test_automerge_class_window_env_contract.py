"""Contract: the automerge rail's class gate honors TITAN_CALIBRATION_WINDOW.

The supervised lane report and the rail's merge decision must read the same
per-class window. Before this gate, `auto_merge_eligible_classes` /
`class_merge_status` hardcoded window=20 while the lane scripts displayed
window=${TITAN_CALIBRATION_WINDOW} — an operator setting window=10 saw
ELIGIBLE in the report while the rail still computed GATE (or vice versa).

- class_gate_window() defaults to 20 with no env
- TITAN_CALIBRATION_WINDOW=N drives class_gate_window and the rail helpers
- _calibration_gates_for_files passes the operator env through to eligibility
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SRC = REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
_SCRIPTS = REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _load_am():
    spec = importlib.util.spec_from_file_location(
        "autonomous_merge_env_contract", REPO / "scripts" / "autonomous_merge.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _row(rid: str, held: bool, change_class: str = "bugfix") -> dict:
    return {
        "claim": rid,
        "confidence": 0.9,
        "held": held,
        "scored_by": "measured",
        "change_class": change_class,
        "receipt_id": rid,
    }


def _ledger(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "ledger.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def test_class_gate_window_defaults_to_20(monkeypatch):
    am = _load_am()
    monkeypatch.delenv("TITAN_CALIBRATION_WINDOW", raising=False)
    assert am.class_gate_window() == 20
    assert am.class_gate_window({}) == 20


def test_class_gate_window_honors_env():
    am = _load_am()
    assert am.class_gate_window({"TITAN_CALIBRATION_WINDOW": "10"}) == 10
    assert am.class_gate_window({"TITAN_CALIBRATION_WINDOW": "bogus"}) == 20
    assert am.class_gate_window({"TITAN_CALIBRATION_WINDOW": "0"}) == 20


def test_rail_and_report_windows_agree(tmp_path, monkeypatch):
    """10 recent wins after old failures: ELIGIBLE at window=10, GATE at 20."""
    am = _load_am()
    rows = [_row(f"old-fail-{i}", False) for i in range(4)]
    rows += [_row(f"win-{i:02d}", True) for i in range(10)]
    ledger = _ledger(tmp_path, rows)

    monkeypatch.delenv("TITAN_CALIBRATION_WINDOW", raising=False)
    assert am.auto_merge_eligible_classes(ledger) == []  # window 20 sees the failures

    monkeypatch.setenv("TITAN_CALIBRATION_WINDOW", "10")
    assert am.auto_merge_eligible_classes(ledger) == ["bugfix"]
    assert am.class_merge_status(ledger, "bugfix") == "auto-merge ELIGIBLE"


def test_calibration_gates_pass_operator_env_window(tmp_path, monkeypatch):
    am = _load_am()
    rows = [_row(f"old-fail-{i}", False) for i in range(4)]
    rows += [_row(f"win-{i:02d}", True) for i in range(10)]
    ledger = _ledger(tmp_path, rows)
    monkeypatch.setattr(am, "default_ledger_path", lambda root=None: ledger)
    monkeypatch.delenv("TITAN_AUTONOMY_CALIBRATION_BYPASS", raising=False)

    base_env = {
        "TITAN_AUTONOMY_REQUIRE_CALIBRATION_TRUST": "1",
        "TITAN_AUTOMERGE_REQUIRE_CLASS_ELIGIBLE": "1",
    }
    files = ["docs/improvements/0523-coderag-filter-toctou.md"]

    monkeypatch.delenv("TITAN_CALIBRATION_WINDOW", raising=False)
    _, class_ok_20 = am._calibration_gates_for_files(files, env=dict(base_env))
    assert class_ok_20 is False  # window 20 sees the old failures

    trust_ok, class_ok_10 = am._calibration_gates_for_files(
        files, env={**base_env, "TITAN_CALIBRATION_WINDOW": "10"}
    )
    assert class_ok_10 is True
    assert trust_ok is True  # class-local rail satisfies rail 7
