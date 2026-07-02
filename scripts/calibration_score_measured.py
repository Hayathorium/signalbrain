#!/usr/bin/env python3
"""Objective post-merge scoring for improvement claims.

Re-runs the command(s) documented under ``### How measured`` in an A/B receipt and
appends the outcome to the MEASURED ledger (``scored_by="measured"``).

Self-reported ingest (``calibration_ingest_receipts.py``) writes to a separate file;
this script is the independent verification path that can move the measured hit-rate.
"""

from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = ROOT / "scripts"
_SRC = ROOT / "src"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from calibration_ingest_receipts import VERDICTS, _value_after, change_class_from_receipt_text  # noqa: E402
from agi_os_backend.governance.calibration_ledger_core import (  # noqa: E402
    CLAIM_KIND_INVARIANT_PIN,
    is_goodhart_excluded_receipt_id,
)
from agi_os_backend.governance.calibration_same_pr_pin import is_same_pr_test_only_pin  # noqa: E402

DEFAULT_LEDGER_REL = "docs/calibration/improvement_claim_ledger.jsonl"
DEFAULT_RECEIPTS_GLOB = "docs/improvements/*.md"
DEFAULT_MAX_MEASURE = 3
DEFAULT_MEASURE_TIMEOUT_S = 180
LOCK_REL = "runtime/calibration_score_measured.lock"
MERGED_CHECK_REL = "scripts/calibration_receipt_merged_check.sh"
CODE_BLOCK = re.compile(r"```(?:bash|sh)?\n(.*?)```", re.S | re.I)


def repo_root() -> Path:
    return ROOT


def how_measured_section(text: str) -> str:
    lines = text.splitlines()
    block: list[str] = []
    capture = False
    for ln in lines:
        stripped = ln.strip().lower()
        if stripped.startswith("### how measured"):
            capture = True
            continue
        if capture and ln.startswith("## ") and not ln.startswith("###"):
            break
        if capture:
            block.append(ln)
    return "\n".join(block)


def _apply_export(line: str, env: dict[str, str]) -> None:
    if not line.startswith("export "):
        return
    payload = line[len("export ") :].strip()
    if "=" not in payload:
        return
    key, value = payload.split("=", 1)
    env[key.strip()] = value.strip().strip('"').strip("'")


def _logical_lines(body: str) -> list[str]:
    out: list[str] = []
    buf = ""
    for raw in body.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.endswith("\\"):
            buf += s[:-1].strip() + " "
            continue
        buf += s
        out.append(buf.strip())
        buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def _safe_split(line: str) -> list[str]:
    try:
        return shlex.split(line)
    except ValueError:
        return line.replace("\\", " ").split()


def _split_inline_env_prefix(line: str) -> tuple[list[str], str]:
    """Split leading VAR=value tokens into synthetic export lines for subprocess env."""
    exports: list[str] = []
    rest = line.strip()
    while rest:
        parts = rest.split(None, 1)
        if len(parts) < 2:
            break
        token, tail = parts[0], parts[1]
        if "=" in token and not token.startswith(("pytest", "python", "bash", "/bin/")):
            key, _, val = token.partition("=")
            exports.append(f"export {key}={val}")
            rest = tail
            continue
        break
    return exports, rest


def _strip_inline_env_prefix(line: str) -> str:
    """Drop leading VAR=value tokens (e.g. ``PYTHONPATH=src pytest ...``)."""
    _, rest = _split_inline_env_prefix(line)
    return rest or line.strip()


def _parse_command_line(line: str) -> list[str] | None:
    if line.startswith("export "):
        return None
    line = _strip_inline_env_prefix(line)
    if line.startswith("pytest "):
        return ["pytest"] + _safe_split(line[len("pytest ") :])
    if "-m pytest" in line:
        tail = line.split("-m pytest", 1)[1].strip()
        return ["pytest"] + (_safe_split(tail) if tail else [])
    if line.startswith("bash "):
        rest = line[len("bash ") :].strip()
        parts = _safe_split(rest)
        if parts and parts[0].endswith(".sh"):
            return ["/bin/bash", *parts]
        return ["/bin/bash", "-lc", rest]
    if line.startswith("python3 ") or line.startswith("python "):
        return _safe_split(line)
    return None


def extract_commands_with_env(text: str) -> tuple[list[str], list[list[str]]]:
    section = how_measured_section(text)
    exports: list[str] = []
    commands: list[list[str]] = []
    for match in CODE_BLOCK.finditer(section):
        body = match.group(1).strip()
        if not body or body.lower().startswith("not measured"):
            continue
        for line in _logical_lines(body):
            if line.startswith("export "):
                exports.append(line)
                continue
            inline_exports, _ = _split_inline_env_prefix(line)
            exports.extend(inline_exports)
            parsed = _parse_command_line(line)
            if parsed:
                commands.append(parsed)
    return exports, commands


def default_max_measure() -> int:
    raw = (os.getenv("CALIBRATION_SCORE_MAX_MEASURE") or "").strip()
    if not raw:
        return DEFAULT_MAX_MEASURE
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MAX_MEASURE


def default_measure_timeout_s() -> int:
    raw = (os.getenv("CALIBRATION_SCORE_TIMEOUT_S") or "").strip()
    if not raw:
        return DEFAULT_MEASURE_TIMEOUT_S
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MEASURE_TIMEOUT_S


@contextmanager
def score_lock(root: Path):
    lock_path = root / LOCK_REL
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(
                "calibration_score_measured: another scorer is running "
                f"(lock={lock_path}); refuse parallel bulk re-score"
            ) from exc
        yield


def merged_ref() -> str:
    return (os.getenv("CALIBRATION_MERGED_REF") or "origin/main").strip()


def enforce_merged_receipt(path: Path, *, root: Path) -> tuple[bool, str]:
    if os.getenv("CALIBRATION_ALLOW_UNMERGED", "0") == "1":
        return True, ""
    script = root / MERGED_CHECK_REL
    proc = subprocess.run(
        ["bash", str(script), str(path)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True, ""
    detail = (proc.stderr or proc.stdout or "").strip()
    return False, detail or f"merged-receipt guard exit {proc.returncode}"


def run_measurement(
    commands: list[list[str]],
    exports: list[str],
    *,
    root: Path,
    base_env: dict[str, str],
    timeout_s: int,
) -> tuple[bool, list[str]]:
    env = dict(base_env)
    for exp in exports:
        _apply_export(exp, env)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "src"), str(root / "scripts"), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    errors: list[str] = []
    for argv in commands:
        if argv[0] == "pytest" and not shutil.which("pytest"):
            argv = [sys.executable, "-m", "pytest", *argv[1:]]
        try:
            proc = subprocess.run(
                argv,
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"{' '.join(argv)} -> timeout {timeout_s}s")
            continue
        if proc.returncode != 0:
            errors.append(f"{' '.join(argv)} -> exit {proc.returncode}")
    return not errors, errors


def score_receipt(
    path: Path,
    *,
    root: Path,
    base_env: dict[str, str],
    timeout_s: int | None = None,
    skip_merged_check: bool = False,
) -> dict | None:
    if not skip_merged_check:
        ok, detail = enforce_merged_receipt(path, root=root)
        if not ok:
            print(f"calibration_score_measured: refuse {path.name}: {detail}", file=sys.stderr)
            return None
    text = path.read_text(encoding="utf-8")
    conf = _value_after("## Confidence", text, r"0?\.\d+|1\.0")
    verd = _value_after("## Verdict", text, "|".join(VERDICTS))
    if conf is None or verd is None:
        return None
    verd = verd.lower()
    if verd == "not_applicable":
        return None
    exports, commands = extract_commands_with_env(text)
    if not commands:
        return None
    ok, errors = run_measurement(
        commands,
        exports,
        root=root,
        base_env=base_env,
        timeout_s=timeout_s if timeout_s is not None else default_measure_timeout_s(),
    )
    stem = path.stem
    if is_goodhart_excluded_receipt_id(stem):
        return None
    rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    entry: dict = {
        "claim": stem,
        "confidence": float(conf),
        "held": ok,
        "caught_by": "objective_receipt_rerun",
        "session": "measured-score",
        "scored_by": "measured",
        "change_class": change_class_from_receipt_text(text, stem=stem),
        "verdict": verd,
        "receipt_id": stem,
        "measure_errors": errors[:5],
    }
    if is_same_pr_test_only_pin(root, rel, commands, merged_ref=merged_ref()):
        entry["claim_kind"] = CLAIM_KIND_INVARIANT_PIN
    return entry


def remove_receipt_id(ledger_path: Path, receipt_id: str) -> int:
    """Remove all ledger rows matching receipt_id (operator rescore after scorer fix)."""
    if not ledger_path.is_file():
        return 0
    kept: list[str] = []
    removed = 0
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("receipt_id") or row.get("claim") or "")
        if rid == receipt_id:
            removed += 1
            continue
        kept.append(line)
    if removed:
        ledger_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed


def replace_receipt_rows(ledger_path: Path, receipt_id: str, entry: dict) -> int:
    """Rewrite the existing row(s) for receipt_id in place, preserving ledger order.

    The per-class auto-merge gate reads a recency window over row order; a
    remove-then-append rescore shifts every later row toward the window edge and
    can evict unrelated recent wins (observed demoting bugfix ELIGIBLE -> GATE).
    The first matching row is rewritten with ``entry``; extra duplicate rows for
    the same receipt_id are dropped. Returns the number of old rows matched.
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


def existing_receipt_ids(ledger_path: Path) -> set[str]:
    ids: set[str] = set()
    if not ledger_path.is_file():
        return ids
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ids.add(str(row.get("receipt_id") or row.get("claim") or ""))
    return ids


def append_scored(entries: list[dict], ledger_path: Path) -> int:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    existing = existing_receipt_ids(ledger_path)
    added = 0
    with ledger_path.open("a", encoding="utf-8") as fh:
        for entry in entries:
            rid = str(entry.get("receipt_id") or entry.get("claim") or "")
            if not rid or rid in existing:
                continue
            fh.write(json.dumps(entry) + "\n")
            existing.add(rid)
            added += 1
    return added


def score_glob(
    receipts_glob: str,
    ledger_path: Path,
    *,
    root: Path,
    base_env: dict[str, str],
    max_measure: int | None = None,
    timeout_s: int | None = None,
    rescore: bool = False,
) -> dict:
    scored: list[dict] = []
    skipped = 0
    skipped_ledger = 0
    refused_unmerged = 0
    capped = 0
    measure_limit = default_max_measure() if max_measure is None else max(0, max_measure)
    measure_timeout = timeout_s if timeout_s is not None else default_measure_timeout_s()
    already = existing_receipt_ids(ledger_path)
    rescore_ids: set[str] = set()
    measured = 0
    for path_str in sorted(glob.glob(receipts_glob)):
        stem = Path(path_str).stem
        if stem in already:
            if rescore:
                # Replace in place after scoring (preserves ledger row order for
                # the recency-windowed class gate; keeps the old row on failure).
                rescore_ids.add(stem)
            else:
                skipped += 1
                skipped_ledger += 1
                continue
        if measure_limit == 0:
            capped += 1
            continue
        if measured >= measure_limit:
            capped += 1
            continue
        receipt_path = Path(path_str)
        allowed, _detail = enforce_merged_receipt(receipt_path, root=root)
        if not allowed:
            refused_unmerged += 1
            continue
        try:
            row = score_receipt(
                receipt_path,
                root=root,
                base_env=base_env,
                timeout_s=measure_timeout,
                skip_merged_check=True,
            )
        except Exception:
            skipped += 1
            continue
        if row is None:
            skipped += 1
            continue
        measured += 1
        scored.append(row)
    replaced = 0
    to_append: list[dict] = []
    for row in scored:
        rid = str(row.get("receipt_id") or row.get("claim") or "")
        if rid in rescore_ids and replace_receipt_rows(ledger_path, rid, row):
            replaced += 1
        else:
            to_append.append(row)
    added = append_scored(to_append, ledger_path)
    return {
        "scored": len(scored),
        "added": added,
        "replaced": replaced,
        "skipped": skipped,
        "skipped_ledger": skipped_ledger,
        "refused_unmerged": refused_unmerged,
        "capped": capped,
        "max_measure": measure_limit,
        "measure_timeout_s": measure_timeout,
        "ledger": str(ledger_path),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Objective A/B receipt measurement → measured ledger")
    ap.add_argument("--receipts", default=DEFAULT_RECEIPTS_GLOB)
    ap.add_argument("--ledger", default=str(repo_root() / DEFAULT_LEDGER_REL))
    ap.add_argument(
        "--max-measure",
        type=int,
        default=None,
        help=(
            "Max unscored receipts to measure this run (default "
            f"{DEFAULT_MAX_MEASURE} or CALIBRATION_SCORE_MAX_MEASURE; 0=ledger skip only)"
        ),
    )
    ap.add_argument(
        "--timeout-s",
        type=int,
        default=None,
        help=f"Per-command timeout (default {DEFAULT_MEASURE_TIMEOUT_S}s or CALIBRATION_SCORE_TIMEOUT_S)",
    )
    ap.add_argument(
        "--all-receipts",
        action="store_true",
        help="Disable max-measure cap (operator bulk backfill only)",
    )
    ap.add_argument(
        "--rescore",
        action="store_true",
        help="Re-measure receipts already in the ledger, rewriting their row in place (operator rescore)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    root = repo_root()
    max_measure = None if args.all_receipts else args.max_measure
    if args.dry_run:
        would = 0
        skipped = 0
        skipped_ledger = 0
        already = existing_receipt_ids(Path(args.ledger))
        for path_str in sorted(glob.glob(args.receipts)):
            stem = Path(path_str).stem
            if stem in already:
                skipped += 1
                skipped_ledger += 1
                continue
            text = Path(path_str).read_text(encoding="utf-8")
            conf = _value_after("## Confidence", text, r"0?\.\d+|1\.0")
            verd = _value_after("## Verdict", text, "|".join(VERDICTS))
            if conf is None or verd is None or str(verd).lower() == "not_applicable":
                skipped += 1
                continue
            _, commands = extract_commands_with_env(text)
            if commands:
                would += 1
            else:
                skipped += 1
        limit = default_max_measure() if max_measure is None else max(0, max_measure)
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "would_score": would,
                    "would_score_capped": min(would, limit) if limit else 0,
                    "max_measure": limit,
                    "skipped": skipped,
                    "skipped_ledger": skipped_ledger,
                },
                indent=2,
            )
        )
        return 0
    with score_lock(root):
        result = score_glob(
            args.receipts,
            Path(args.ledger),
            root=root,
            base_env=dict(os.environ),
            max_measure=max_measure,
            timeout_s=args.timeout_s,
            rescore=bool(args.rescore),
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
