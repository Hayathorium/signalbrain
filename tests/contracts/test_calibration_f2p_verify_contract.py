"""Contract: F2P/P2P objective verifier (scripts/calibration_f2p_verify.py).

Pure-python, CI-safe: NO real git worktree and NO real pytest subprocess. The
`_run_test` helper and `subprocess.run` (worktree add/remove) are monkeypatched so
the verdict logic — not the environment — is what is under test.

The anti-gaming property being pinned: a claim is `held` only when its test is
genuinely fail-to-pass (passes on HEAD, fails against baseline code) AND every
pass-to-pass (P2P) test keeps passing. A tautological invariant-pin passes on
baseline too -> not fail-to-pass -> NOT held.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

mod = importlib.import_module("calibration_f2p_verify")


def test_is_f2p_pure_verdict():
    # genuine improvement: passes on HEAD, fails on baseline code
    assert mod.is_f2p(True, False) is True
    # tautological pin: passes on baseline too -> rejected
    assert mod.is_f2p(True, True) is False
    # broken on HEAD -> rejected regardless of baseline
    assert mod.is_f2p(False, False) is False
    # baseline indeterminate (None) -> rejected (UNKNOWN is not held)
    assert mod.is_f2p(True, None) is False


def _scripted_runner(head_pass, baseline_pass, p2p_map=None):
    """Return a _run_test stand-in keyed off cwd (HEAD root vs baseline worktree)."""
    p2p_map = p2p_map or {}

    def _runner(test_id, cwd, timeout):
        if test_id in p2p_map:
            return p2p_map[test_id], f"p2p:{test_id}"
        # cwd == module ROOT means HEAD; anything else is the baseline worktree
        if cwd == mod.ROOT:
            return head_pass, "head-summary"
        return baseline_pass, "baseline-summary"

    return _runner


def _noop_subprocess(*args, **kwargs):
    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    return _R()


def test_verify_f2p_genuine_improvement_is_held(monkeypatch):
    monkeypatch.setattr(mod, "_run_test", _scripted_runner(head_pass=True, baseline_pass=False))
    monkeypatch.setattr(mod.subprocess, "run", _noop_subprocess)
    result = mod.verify_f2p("tests/contracts/test_x.py::test_real", "deadbeef")
    assert result["held"] is True
    assert result["f2p_held"] is True
    assert result["scored_by"] == "measured_f2p"


def test_verify_f2p_pin_tautology_not_held(monkeypatch):
    # pin: passes on HEAD AND passes on baseline -> not fail-to-pass
    monkeypatch.setattr(mod, "_run_test", _scripted_runner(head_pass=True, baseline_pass=True))
    monkeypatch.setattr(mod.subprocess, "run", _noop_subprocess)
    result = mod.verify_f2p("tests/contracts/test_pin.py::test_exists", "deadbeef")
    assert result["held"] is False
    assert result["f2p_held"] is False


def test_verify_f2p_p2p_regression_not_held(monkeypatch):
    # genuine F2P but a pass-to-pass test regresses -> not held
    p2p_id = "tests/contracts/test_other.py::test_keep"
    monkeypatch.setattr(
        mod,
        "_run_test",
        _scripted_runner(head_pass=True, baseline_pass=False, p2p_map={p2p_id: False}),
    )
    monkeypatch.setattr(mod.subprocess, "run", _noop_subprocess)
    result = mod.verify_f2p("tests/contracts/test_x.py::test_real", "deadbeef", p2p=[p2p_id])
    assert result["f2p_held"] is True
    assert result["p2p_ok"] is False
    assert result["held"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
