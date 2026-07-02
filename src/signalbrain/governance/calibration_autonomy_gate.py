"""Calibration gate for widening autonomous authority.

Scores improvement-claim confidence vs outcome (held/not-held). Autonomy widening
(factory dispatch, research dispatch, mutation env flags) requires TRUST unless
an operator explicitly bypasses with TITAN_AUTONOMY_CALIBRATION_BYPASS=1.

By default the gate counts only ``scored_by == "measured"`` claims so self-reported
A/B ingest cannot inflate trust (see calibration_ingest_receipts.py).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from signalbrain.governance.calibration_ledger_core import (
    AUTONOMY_RECENCY_WINDOW,
    DEFAULT_MIN_HIT_RATE,
    calibration_verdict,
    class_auto_merge_status,
    load_rows,
)

DEFAULT_LEDGER_REL = "docs/calibration/improvement_claim_ledger.jsonl"
CALIBRATION_BYPASS_ENV = "TITAN_AUTONOMY_CALIBRATION_BYPASS"
LEDGER_PATH_ENV = "TITAN_CALIBRATION_LEDGER_PATH"
MIN_HIT_RATE_ENV = "TITAN_CALIBRATION_MIN_HIT_RATE"
REQUIRE_MEASURED_ENV = "TITAN_CALIBRATION_REQUIRE_MEASURED"
WINDOW_ENV = "TITAN_CALIBRATION_WINDOW"
CHANGE_CLASS_ENV = "TITAN_CALIBRATION_CHANGE_CLASS"
DUAL_GATE_ENV = "TITAN_CALIBRATION_DUAL_GATE"
RECENCY_GATE_ENV = "TITAN_CALIBRATION_RECENCY_GATE"


def default_ledger_path(root: Path | None = None) -> Path:
    override = os.getenv(LEDGER_PATH_ENV, "").strip()
    if override:
        return Path(override)
    base = root or Path(__file__).resolve().parents[3]
    return base / DEFAULT_LEDGER_REL


def min_hit_rate_from_env(env: dict[str, str] | None = None) -> float:
    env = env if env is not None else os.environ
    raw = str(env.get(MIN_HIT_RATE_ENV, "") or DEFAULT_MIN_HIT_RATE).strip()
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_MIN_HIT_RATE
    return value if 0.0 < value <= 1.0 else DEFAULT_MIN_HIT_RATE


def require_measured_from_env(env: dict[str, str] | None = None) -> bool:
    env = env if env is not None else os.environ
    raw = str(env.get(REQUIRE_MEASURED_ENV, "1")).strip().lower()
    return raw in ("1", "true", "yes", "on")


def window_from_env(env: dict[str, str] | None = None) -> int | None:
    env = env if env is not None else os.environ
    raw = str(env.get(WINDOW_ENV, "")).strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def change_class_from_env(env: dict[str, str] | None = None) -> str | None:
    env = env if env is not None else os.environ
    raw = str(env.get(CHANGE_CLASS_ENV, "")).strip()
    return raw or None


def calibration_bypass_enabled(env: dict[str, str] | None = None) -> bool:
    env = env if env is not None else os.environ
    return str(env.get(CALIBRATION_BYPASS_ENV, "0")).strip().lower() in ("1", "true", "yes", "on")


def calibration_autonomy_verdict(
    ledger_path: Path,
    *,
    min_hit_rate: float = DEFAULT_MIN_HIT_RATE,
    require_measured: bool | None = None,
    window: int | None = None,
    change_class: str | None = None,
    exclude_goodhart: bool = True,
) -> dict[str, Any]:
    if not ledger_path.is_file():
        return {
            "claims": 0,
            "high_confidence_claims": 0,
            "high_confidence_hit_rate": 0.0,
            "min_hit_rate": min_hit_rate,
            "verdict": "GATE",
            "reason": "calibration ledger missing",
            "require_measured": require_measured,
        }
    rows = load_rows(ledger_path)
    return calibration_verdict(
        rows,
        min_hit_rate=min_hit_rate,
        require_measured=bool(require_measured),
        window=window,
        change_class=change_class,
        exclude_goodhart=exclude_goodhart,
    )


def per_class_auto_merge(ledger_path: Path, *, window: int | None = None) -> dict[str, dict[str, Any]]:
    return class_auto_merge_status(
        load_rows(ledger_path),
        window=window,
        require_measured=True,
        exclude_goodhart=True,
    )


def _truthy_env(env: dict[str, str], key: str) -> bool:
    return str(env.get(key, "")).strip().lower() in ("1", "true", "yes", "on")


def recency_only_from_env(env: dict[str, str] | None = None) -> bool:
    """When True, operative gate uses recency-window TRUST only (operator opt-in to option b)."""
    env = env if env is not None else os.environ
    if _truthy_env(env, DUAL_GATE_ENV):
        return False
    return _truthy_env(env, RECENCY_GATE_ENV)


def dual_gate_from_env(env: dict[str, str] | None = None) -> bool:
    """Default operative gate: require both full-history and recency-window TRUST."""
    return not recency_only_from_env(env)


def autonomy_widening_allowed(
    root: Path,
    *,
    env: dict[str, str] | None = None,
    ledger_path: Path | None = None,
) -> tuple[bool, dict[str, Any]]:
    env = dict(env if env is not None else os.environ)
    if calibration_bypass_enabled(env):
        return True, {"verdict": "BYPASS", "reason": "operator bypass env set"}
    path = ledger_path or default_ledger_path(root)
    measured = require_measured_from_env(env)
    min_rate = min_hit_rate_from_env(env)
    operator_window = window_from_env(env)
    full = calibration_autonomy_verdict(
        path,
        min_hit_rate=min_rate,
        require_measured=measured,
        window=None,
        change_class=change_class_from_env(env),
        exclude_goodhart=True,
    )
    recency_window = operator_window if operator_window is not None else AUTONOMY_RECENCY_WINDOW
    recency = calibration_autonomy_verdict(
        path,
        min_hit_rate=min_rate,
        require_measured=measured,
        window=recency_window,
        change_class=change_class_from_env(env),
        exclude_goodhart=True,
    )
    if recency_only_from_env(env):
        allowed = recency.get("verdict") == "TRUST"
        reason = "recency-windowed measured gate (full history advisory only; operator opt-in)"
    else:
        allowed = full.get("verdict") == "TRUST" and recency.get("verdict") == "TRUST"
        reason = "dual gate: full measured history and recency window must both TRUST"
    verdict = {
        "verdict": "TRUST" if allowed else "GATE",
        "reason": reason,
        "operative_gate": "recency_window" if recency_only_from_env(env) else "dual",
        "full_history": full,
        "recency_window": recency,
        "recency_window_size": recency_window,
        "require_measured": measured,
    }
    return allowed, verdict
