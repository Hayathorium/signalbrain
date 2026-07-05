"""Objective post-merge scoring — re-run the receipt's own measurements (SPEC §2).

Explicit-config port of neural-chat-v3 `calibration_score_measured`: no repo-root
assumptions; the caller supplies root, ledger path, and merged ref. Incident-tested
behaviors preserved:

- merged-receipt guard runs on EVERY scoring path (§6.4)
- rescore rewrites rows IN PLACE; capped/failed re-measurement never destroys a row (§6.3)
- same-PR test-only receipts are recorded as invariant pins, never trust (§6.2)
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import guard as guard_mod
from .ledger import CLAIM_KIND_INVARIANT_PIN, is_goodhart_excluded_receipt_id
from .pins import is_same_pr_test_only_pin
from .receipt import Receipt, parse_receipt

DEFAULT_MEASURE_TIMEOUT_S = 180


@dataclass
class ScoreConfig:
    root: Path
    ledger_path: Path
    merged_ref: str = "origin/main"
    allow_unmerged: bool = False
    timeout_s: int = DEFAULT_MEASURE_TIMEOUT_S
    rescore: bool = False
    base_env: dict[str, str] | None = None


def _apply_export(line: str, env: dict[str, str]) -> None:
    if not line.startswith("export "):
        return
    payload = line[len("export ") :].strip()
    if "=" not in payload:
        return
    key, value = payload.split("=", 1)
    env[key.strip()] = value.strip().strip('"').strip("'")


def run_measurement(receipt: Receipt, cfg: ScoreConfig) -> tuple[bool, list[str]]:
    env = dict(cfg.base_env if cfg.base_env is not None else os.environ)
    for exp in receipt.exports:
        _apply_export(exp, env)
    errors: list[str] = []
    for argv in receipt.commands:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cfg.root),
                env=env,
                capture_output=True,
                text=True,
                timeout=cfg.timeout_s,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"{' '.join(argv)} -> timeout {cfg.timeout_s}s")
            continue
        except FileNotFoundError as exc:
            errors.append(f"{' '.join(argv)} -> {exc}")
            continue
        if proc.returncode != 0:
            errors.append(f"{' '.join(argv)} -> exit {proc.returncode}")
    return not errors, errors


def existing_receipt_ids(ledger_path: Path) -> set[str]:
    ids: set[str] = set()
    if not ledger_path.is_file():
        return ids
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            ids.add(str(row.get("receipt_id") or row.get("claim") or ""))
    return ids


def replace_receipt_rows(ledger_path: Path, receipt_id: str, entry: dict) -> int:
    """Rewrite existing row(s) for receipt_id in place, preserving ledger order.

    The per-class gate reads a recency window over row order; remove-then-append
    rescoring shifts every later row toward the window edge and can evict
    unrelated recent wins. First match is rewritten; duplicates dropped.
    """
    if not ledger_path.is_file():
        return 0
    out_lines: list[str] = []
    matched = 0
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("receipt_id") or row.get("claim") or "")
        if rid == receipt_id:
            if matched == 0:
                out_lines.append(json.dumps(entry))
            matched += 1
            continue
        out_lines.append(line)
    if matched:
        ledger_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return matched


def append_row(ledger_path: Path, entry: dict) -> bool:
    rid = str(entry.get("receipt_id") or entry.get("claim") or "")
    if not rid or rid in existing_receipt_ids(ledger_path):
        return False
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return True


def score_receipt(path: Path, cfg: ScoreConfig) -> dict:
    """Score one receipt. Returns a result dict with 'status' and optionally 'row'.

    Statuses: scored | replaced | skipped_ledger | refused_guard | unscoreable
    """
    receipt = parse_receipt(path)
    if receipt is None:
        return {"status": "unscoreable", "receipt": str(path)}
    if is_goodhart_excluded_receipt_id(receipt.stem):
        return {"status": "unscoreable", "receipt": str(path), "reason": "goodhart-excluded name"}

    # Guard on EVERY path (SPEC §6.4).
    g = guard_mod.check_merged(
        cfg.root, path, merged_ref=cfg.merged_ref, allow_unmerged=cfg.allow_unmerged
    )
    if not g.ok:
        return {"status": "refused_guard", "receipt": str(path), "code": g.code, "message": g.message}

    already = receipt.stem in existing_receipt_ids(cfg.ledger_path)
    if already and not cfg.rescore:
        return {"status": "skipped_ledger", "receipt": str(path)}

    if not receipt.commands and not receipt.measure_errors:
        return {"status": "unscoreable", "receipt": str(path), "reason": "no measure commands"}

    if receipt.measure_errors:
        held = False
        errors = receipt.measure_errors
    else:
        held, errors = run_measurement(receipt, cfg)
    row: dict = {
        "claim": receipt.stem,
        "confidence": receipt.confidence,
        "held": held,
        "caught_by": "objective_receipt_rerun",
        "scored_by": "measured",
        "change_class": receipt.change_class,
        "verdict": receipt.verdict,
        "receipt_id": receipt.stem,
        "measure_errors": errors[:5],
    }
    try:
        rel = str(path.resolve().relative_to(cfg.root.resolve()))
    except ValueError:
        rel = path.name
    if is_same_pr_test_only_pin(cfg.root, rel, receipt.commands, merged_ref=cfg.merged_ref):
        row["claim_kind"] = CLAIM_KIND_INVARIANT_PIN  # recorded, never trust (SPEC §6.2)

    if already and cfg.rescore:
        if replace_receipt_rows(cfg.ledger_path, receipt.stem, row):
            return {"status": "replaced", "receipt": str(path), "row": row}
    append_row(cfg.ledger_path, row)
    return {"status": "scored", "receipt": str(path), "row": row}
