#!/usr/bin/env python3
"""Auto-ingest A/B-receipt claims into a SELF-REPORTED calibration ledger.

Each receipt carries a ``## Confidence`` (the proposer's probability the change is a real
improvement) and a ``## Verdict`` (improvement/parity/regression/not_applicable). This
populates the *claim record* automatically as PRs ship.

INTEGRITY — read this:
  These are SELF-REPORTED outcomes (the author's own verdict), so they are written with
  ``scored_by="self_report"`` to a SEPARATE file, NOT the measured seed ledger. The
  autonomy gate runs with ``--require-measured`` and therefore IGNORES these — by design.
  Auto-scoring receipt verdicts as "measured" would be the exact over-confidence the
  calibration ledger exists to catch (every PR claims improvement).

  The VALUE here is the GAP: self-reported hit-rate (~100%, everyone claims improvement)
  vs the measured seed (40%, reality). That gap is the over-confidence signal. Moving the
  *measured* rate to 95% needs INDEPENDENT verification (held-out eval / post-merge A/B),
  which is a separate step — not this script.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

VERDICTS = ("improvement", "parity", "regression", "not_applicable")
# verdict -> held for an IMPROVEMENT claim: only "improvement" held; parity/regression did not.
HELD = {"improvement": True, "parity": False, "regression": False}


def _value_after(header: str, text: str, pattern: str) -> str | None:
    """First regex match on the non-blank lines after an exact ``## header``."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == header:
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    m = re.search(pattern, nxt, re.I)
                    if m:
                        return m.group(0)
                    # allow one blank-then-value; keep scanning a couple lines
            break
    return None


def _change_class(stem: str) -> str:
    s = stem.lower()
    if any(k in s for k in ("fix", "guard", "deadlock", "skip", "misroute", "offload", "requeue", "tautology", "toctou")):
        return "bugfix"
    if any(k in s for k in ("ledger", "eval", "gate", "trace", "hook", "tooling", "calibration")):
        return "tooling"
    if any(k in s for k in ("env", "parity", "config")):
        return "config"
    return "unclassified"


_CHANGE_CLASS_FOOTER_RE = re.compile(
    r"^## change_class\s*\r?\n\s*([a-z][a-z0-9_-]*)\s*(?:\r?\n|$)",
    re.MULTILINE | re.IGNORECASE,
)
_VALID_RECEIPT_CHANGE_CLASSES = frozenset({"bugfix", "tooling", "config", "research", "unclassified"})


def change_class_from_receipt_text(text: str, *, stem: str = "") -> str:
    match = _CHANGE_CLASS_FOOTER_RE.search(text or "")
    if match:
        value = match.group(1).strip().lower()
        if value in _VALID_RECEIPT_CHANGE_CLASSES:
            return value
    return _change_class(stem)


def ingest(receipts_glob: str, out_path: str) -> dict:
    existing_ids = set()
    if os.path.exists(out_path):
        for ln in open(out_path):
            if ln.strip():
                existing_ids.add(json.loads(ln).get("receipt_id"))
    added = []
    for f in sorted(glob.glob(receipts_glob)):
        text = open(f, encoding="utf-8").read()
        conf = _value_after("## Confidence", text, r"0?\.\d+|1\.0")
        verd = _value_after("## Verdict", text, "|".join(VERDICTS))
        if conf is None or verd is None:
            continue
        verd = verd.lower()
        if verd == "not_applicable":
            continue
        stem = os.path.basename(f)[:-3]
        if stem in existing_ids:
            continue
        added.append({
            "claim": stem,
            "confidence": float(conf),
            "held": HELD.get(verd, False),
            "caught_by": "ab_receipt_verdict",
            "scored_by": "self_report",            # NEVER "measured" — author's own verdict
            "change_class": _change_class(stem),
            "verdict": verd,
            "receipt_id": stem,
        })
    if added:
        with open(out_path, "a", encoding="utf-8") as fh:
            for e in added:
                fh.write(json.dumps(e) + "\n")
    return {"added": len(added), "out": out_path}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipts", default="docs/improvements/*.md")
    ap.add_argument("--out", default="docs/calibration/self_reported_claims.jsonl")
    a = ap.parse_args()
    r = ingest(a.receipts, a.out)
    print(f"  ingested {r['added']} self-reported receipt claims -> {r['out']}")
