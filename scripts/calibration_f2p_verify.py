#!/usr/bin/env python3
"""F2P/P2P objective verification for improvement claims (deep-research validated).

A *genuine* improvement's test is FAIL-TO-PASS (F2P): the same test fails against the
pre-change (baseline) code and passes against the change. That proves the change CAUSED
the improvement — and it inherently rejects tautological "invariant pins" (whose
``*_exists`` tests pass on baseline too, so they are not fail-to-pass and cannot count).

    held = (test PASSES on HEAD) AND (same test FAILS against baseline code) AND (P2P all pass)

P2P (pass-to-pass): a set of tests that must keep passing on HEAD — the no-regression half.

Bounded by construction (the 2026-06-28 swarm lesson): one F2P test + an optional small
P2P set, a per-run timeout, and a single short-lived baseline worktree that is always
removed. No bulk sweeps.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT = int(os.environ.get("CALIBRATION_F2P_TIMEOUT", "180"))


def _run_test(test_id: str, cwd: Path, timeout: int) -> tuple[bool, str]:
    """Run a pytest test id in ``cwd``; return (passed, last-summary-line)."""
    argv = [sys.executable, "-m", "pytest", test_id, "-q", "--no-header", "-p", "no:cacheprovider"]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(cwd / "src"), str(cwd / "scripts"), env.get("PYTHONPATH", "")])
    try:
        p = subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    out = (p.stdout or "").strip()
    return p.returncode == 0, (out.splitlines()[-1] if out else f"exit {p.returncode}")


def is_f2p(head_pass: bool, baseline_pass: bool | None) -> bool:
    """Fail-to-pass: passes on HEAD (the change) AND fails on baseline code.

    A tautological pin passes on baseline too -> not fail-to-pass -> not held. This is the
    anti-gaming property at the measurement layer.
    """
    return bool(head_pass) and baseline_pass is False


def verify_f2p(
    test_id: str,
    baseline_sha: str,
    *,
    p2p: list[str] | None = None,
    root: Path = ROOT,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Verify an improvement claim is genuinely fail-to-pass against ``baseline_sha``."""
    test_file = test_id.split("::", 1)[0]
    # 1. HEAD (the change) — expect PASS
    head_pass, head_sum = _run_test(test_id, root, timeout)
    # 2. Baseline code with the HEAD test injected — expect FAIL
    baseline_pass: bool | None = None
    baseline_sum = "skipped"
    wt: Path | None = None
    try:
        wt = Path(tempfile.mkdtemp(prefix="nc3-f2p-"))
        add = subprocess.run(
            ["git", "worktree", "add", "--detach", str(wt), baseline_sha],
            cwd=str(root), capture_output=True, text=True, timeout=120,
        )
        if add.returncode == 0:
            src_test = root / test_file
            if src_test.is_file():  # test baseline CODE with the NEW test
                dst = wt / test_file
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_test, dst)
            baseline_pass, baseline_sum = _run_test(test_id, wt, timeout)
        else:
            baseline_sum = f"worktree add failed: {add.stderr.strip()[:80]}"
    finally:
        if wt is not None:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                           cwd=str(root), capture_output=True)
    # F2P: passes on HEAD, fails on baseline code
    f2p_flag = is_f2p(head_pass, baseline_pass)
    # P2P: no regression on HEAD
    p2p_results = []
    p2p_ok = True
    for t in (p2p or []):
        ok, summ = _run_test(t, root, timeout)
        p2p_results.append({"test": t, "pass": ok, "summary": summ})
        p2p_ok = p2p_ok and ok
    return {
        "test": test_id,
        "baseline_sha": baseline_sha,
        "head_pass": head_pass,
        "head_summary": head_sum,
        "baseline_pass": baseline_pass,
        "baseline_summary": baseline_sum,
        "f2p_held": f2p_flag,
        "p2p_ok": p2p_ok,
        "p2p": p2p_results,
        # The objective verdict: a real fail-to-pass improvement with no regression.
        "held": f2p_flag and p2p_ok,
        "scored_by": "measured_f2p",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="F2P/P2P objective verification of an improvement claim")
    ap.add_argument("--test", required=True, help="pytest test id that should be fail-to-pass")
    ap.add_argument("--baseline", required=True, help="baseline git SHA (pre-change, e.g. the PR parent)")
    ap.add_argument("--p2p", action="append", default=[], help="pass-to-pass test id (repeatable)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    a = ap.parse_args(argv)
    result = verify_f2p(a.test, a.baseline, p2p=a.p2p, timeout=a.timeout)
    print(json.dumps(result, indent=2))
    return 0 if result["held"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
