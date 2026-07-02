"""Contract: calibration gate rejects Goodhart trust-pin gaming."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

core = __import__("agi_os_backend.governance.calibration_ledger_core", fromlist=["*"])
gate = __import__("agi_os_backend.governance.calibration_autonomy_gate", fromlist=["*"])
SEED = REPO_ROOT / "docs" / "calibration" / "improvement_claim_ledger.jsonl"


def test_goodhart_receipt_markers_defined():
    assert "calibration-trust-pin" in core.GOODHART_EXCLUDED_RECEIPT_MARKERS
    assert "0500-calibration-trust-95" in core.GOODHART_EXCLUDED_RECEIPT_MARKERS


def test_trust_pin_rows_excluded_from_gate(tmp_path):
    rows = [
        {
            "claim": "0481-calibration-trust-pin-01",
            "confidence": 0.88,
            "held": True,
            "scored_by": "measured",
            "receipt_id": "0481-calibration-trust-pin-01",
            "change_class": "tooling",
        }
        for _ in range(20)
    ]
    path = tmp_path / "pins.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    raw = gate.calibration_autonomy_verdict(path, require_measured=True, window=20, exclude_goodhart=False)
    gated = gate.calibration_autonomy_verdict(path, require_measured=True, window=20, exclude_goodhart=True)
    assert raw["verdict"] == "TRUST"
    assert gated["verdict"] == "GATE"
    assert gated["high_confidence_claims"] == 0


def test_seed_ledger_dual_gate_blocks_widening_by_default(monkeypatch):
    monkeypatch.delenv("TITAN_AUTONOMY_CALIBRATION_BYPASS", raising=False)
    monkeypatch.delenv("TITAN_CALIBRATION_WINDOW", raising=False)
    monkeypatch.delenv("TITAN_CALIBRATION_DUAL_GATE", raising=False)
    monkeypatch.delenv("TITAN_CALIBRATION_RECENCY_GATE", raising=False)
    allowed, verdict = gate.autonomy_widening_allowed(REPO_ROOT, ledger_path=SEED)
    assert allowed is False
    assert verdict["verdict"] == "GATE"
    assert verdict["operative_gate"] == "dual"
    assert verdict["full_history"]["verdict"] == "GATE"
    assert verdict["recency_window"]["verdict"] == "TRUST"


def test_seed_ledger_recency_gate_env_allows_when_operator_opt_in(monkeypatch):
    monkeypatch.delenv("TITAN_AUTONOMY_CALIBRATION_BYPASS", raising=False)
    monkeypatch.setenv("TITAN_CALIBRATION_RECENCY_GATE", "1")
    allowed, verdict = gate.autonomy_widening_allowed(REPO_ROOT, ledger_path=SEED)
    assert allowed is True
    assert verdict["verdict"] == "TRUST"
    assert verdict["operative_gate"] == "recency_window"


def test_window_default_unset_means_full_history():
    assert gate.window_from_env({}) is None


def test_score_measured_skips_trust_pin_receipts(tmp_path):
    scripts = REPO_ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    receipt = tmp_path / "0481-calibration-trust-pin-01.md"
    receipt.write_text(
        "\n".join(
            [
                "# 0481-calibration-trust-pin-01",
                "## Confidence",
                "0.88",
                "## Verdict",
                "improvement",
                "### How measured",
                "```bash",
                "true",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    score_mod = __import__("calibration_score_measured", fromlist=["score_receipt"])
    row = score_mod.score_receipt(receipt, root=REPO_ROOT, base_env={}, timeout_s=30)
    assert row is None
