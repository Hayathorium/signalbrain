"""Contract: calibration rescore rewrites ledger rows IN PLACE (order-preserving).

The per-class auto-merge gate (`class_auto_merge_status`) reads a recency
window over ledger row order. A rescore that removed the old row and appended
the fresh score at the tail shifted every later row toward the window edge and
evicted unrelated recent wins — observed demoting bugfix from auto-merge
ELIGIBLE (100%, n=10) to GATE (n=5) on 2026-07-02. Rescore must therefore:

1. rewrite the receipt's existing row at its original position,
2. leave every other row's position untouched,
3. keep the old row when the re-measurement fails to produce a row,
4. still append genuinely new receipts at the tail.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "scripts" / "calibration_score_measured.py"


def _load():
    spec = importlib.util.spec_from_file_location("calibration_score_measured", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _row(rid: str, held: bool, change_class: str = "tooling") -> dict:
    return {
        "claim": rid,
        "confidence": 0.9,
        "held": held,
        "caught_by": "objective_receipt_rerun",
        "session": "measured-score",
        "scored_by": "measured",
        "change_class": change_class,
        "verdict": "improvement",
        "receipt_id": rid,
        "measure_errors": [],
    }


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _ids(path: Path) -> list[str]:
    return [
        json.loads(ln)["receipt_id"]
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def test_replace_receipt_rows_preserves_position_and_drops_dupes(tmp_path):
    mod = _load()
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(
        ledger,
        [_row("old-tooling", False), _row("bugfix-1", True, "bugfix"), _row("old-tooling", False), _row("bugfix-2", True, "bugfix")],
    )
    fresh = _row("old-tooling", True)
    matched = mod.replace_receipt_rows(ledger, "old-tooling", fresh)
    assert matched == 2  # both stale rows matched; duplicate dropped
    assert _ids(ledger) == ["old-tooling", "bugfix-1", "bugfix-2"]
    first = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert first["held"] is True  # rewritten in place with the fresh score


def test_score_glob_rescore_keeps_row_order(tmp_path, monkeypatch):
    mod = _load()
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger, [_row("0001-old", False), _row("0002-win", True, "bugfix"), _row("0003-win", True, "bugfix")])
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "0001-old.md").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setattr(mod, "score_receipt", lambda path, **kw: _row(Path(path).stem, True))
    result = mod.score_glob(
        str(receipts / "*.md"), ledger, root=REPO, base_env={}, rescore=True
    )
    assert result["replaced"] == 1
    assert result["added"] == 0
    assert _ids(ledger) == ["0001-old", "0002-win", "0003-win"]  # order unchanged
    assert json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])["held"] is True


def test_score_glob_failed_rescore_keeps_old_row(tmp_path, monkeypatch):
    mod = _load()
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger, [_row("0001-old", False), _row("0002-win", True, "bugfix")])
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "0001-old.md").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setattr(mod, "score_receipt", lambda path, **kw: None)  # measurement produced nothing
    mod.score_glob(str(receipts / "*.md"), ledger, root=REPO, base_env={}, rescore=True)
    assert _ids(ledger) == ["0001-old", "0002-win"]  # old row not lost
    assert json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])["held"] is False


def test_score_glob_new_receipt_still_appends(tmp_path, monkeypatch):
    mod = _load()
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger, [_row("0002-win", True, "bugfix")])
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "0009-new.md").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setattr(mod, "score_receipt", lambda path, **kw: _row(Path(path).stem, True))
    result = mod.score_glob(
        str(receipts / "*.md"), ledger, root=REPO, base_env={}, rescore=True
    )
    assert result["added"] == 1
    assert _ids(ledger) == ["0002-win", "0009-new"]  # new claims append at the tail
