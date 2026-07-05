"""SignalBrain MCP server — receipts as native agent tools.

Exposes the receipt lifecycle to any MCP client (goose, Claude Desktop, etc.):

  emit_receipt      write a spec-compliant receipt for the change you just made
  validate_receipt  check a receipt file against the grammar before committing
  gate_status       read your own earned-autonomy standing from the ledger

Install:  pip install "signalbrain[mcp]"     Run:  sb-mcp (or: signalbrain)
The server is stateless and local: it reads/writes files in the working
repository. Nothing leaves the machine.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        'signalbrain[mcp] extra not installed — pip install "signalbrain[mcp]"'
    ) from exc

from .gate import per_class
from .receipt import (
    CHANGE_CLASSES,
    UNSUPPORTED_SHELL_GRAMMAR_MESSAGE,
    measure_grammar_errors,
    parse_receipt,
)

mcp = FastMCP(
    "signalbrain",
    instructions=(
        "Receipt tools for verifiable agent claims. After completing a change, "
        "call emit_receipt with an honest confidence and a measure command that "
        "could realistically FAIL if your claim is false. Receipts are "
        "objectively re-scored after merge; overclaiming at confidence >= 0.85 "
        "permanently damages your earned autonomy. When unsure, state lower "
        "confidence — calibration is rewarded, bravado is not."
    ),
)

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _next_number(receipts_dir: Path) -> str:
    nums = []
    for f in receipts_dir.glob("[0-9]" * 4 + "-*.md"):
        try:
            nums.append(int(f.name[:4]))
        except ValueError:
            continue
    return f"{(max(nums) + 1) if nums else 1:04d}"


@mcp.tool()
def emit_receipt(
    slug: str,
    change_class: str,
    title: str,
    change_summary: str,
    how_measured_commands: list[str],
    confidence: float,
    metric_rows: list[str] | None = None,
    verdict: str = "improvement",
    branch: str = "work@HEAD",
    baseline: str = "origin/main",
    date: str = "",
    repo_root: str = ".",
    receipts_dir: str = "receipts",
) -> str:
    """Write a spec-compliant receipt for a change you just completed.

    slug: kebab-case identifier, e.g. "fix-null-deref".
    change_class: one of bugfix | tooling | config | research.
    how_measured_commands: shell commands (pytest/python/bash) that PROVE the
      claim and could fail if it is false. Never measure only with tests you
      wrote in this same change — that is recorded as a pin and earns no trust.
    confidence: your honest probability (0.0-1.0) the measures pass on re-run.
    metric_rows: markdown table rows "metric | baseline | branch | delta".
    date: YYYY-MM-DD; required (the server does not guess the date).
    Returns the receipt path and validation verdict as JSON.
    """
    if change_class not in CHANGE_CLASSES - {"unclassified"}:
        return json.dumps({"ok": False, "error": f"change_class must be one of {sorted(CHANGE_CLASSES - {'unclassified'})}"})
    if not _SLUG.match(slug):
        return json.dumps({"ok": False, "error": "slug must be kebab-case [a-z0-9-]"})
    if not 0.0 <= confidence <= 1.0:
        return json.dumps({"ok": False, "error": "confidence must be in [0,1]"})
    if not date or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return json.dumps({"ok": False, "error": "date required as YYYY-MM-DD"})
    if not how_measured_commands:
        return json.dumps({"ok": False, "error": "at least one measure command required"})
    command_block = "### How measured\n\n```bash\n" + "\n".join(how_measured_commands) + "\n```"
    if measure_grammar_errors(command_block):
        return json.dumps({"ok": False, "error": UNSUPPORTED_SHELL_GRAMMAR_MESSAGE})

    root = Path(repo_root).resolve()
    rdir = root / receipts_dir
    rdir.mkdir(parents=True, exist_ok=True)
    stem = f"{_next_number(rdir)}-{change_class}-{slug}"
    path = rdir / f"{stem}.md"

    rows = metric_rows or ["claimed effect | absent | present | see summary"]
    table = "\n".join(f"| {r} |" for r in rows)
    cmds = "\n".join(how_measured_commands)
    body = f"""# {stem} — {title}

## Compared
- branch:    `{branch}`
- baseline:  `{baseline}`
- date:      `{date}`

## Change summary

{change_summary}

## Metric delta

| Metric | Baseline | Branch | Delta |
|---|---|---|---|
{table}

### How measured

```bash
{cmds}
```

## Verdict

`{verdict}`

## Confidence

{confidence}

## change_class

{change_class}
"""
    path.write_text(body, encoding="utf-8")
    parsed = parse_receipt(path)
    if parsed is None or not parsed.commands:
        path.unlink()
        return json.dumps({"ok": False, "error": "generated receipt failed grammar validation (check measure commands: pytest/python/bash only)"})
    return json.dumps({"ok": True, "path": str(path.relative_to(root)), "stem": stem,
                       "parsed_commands": len(parsed.commands), "confidence": parsed.confidence,
                       "note": "receipt will be objectively re-scored after merge; honest failure is a first-class result"})


@mcp.tool()
def validate_receipt(path: str) -> str:
    """Validate an existing receipt file against the grammar. Returns JSON."""
    p = Path(path)
    if not p.is_file():
        return json.dumps({"ok": False, "error": "file not found"})
    parsed = parse_receipt(p)
    if parsed is None:
        return json.dumps({"ok": False, "error": "unparseable: missing Confidence/Verdict, or verdict is not_applicable"})
    if parsed.measure_errors:
        return json.dumps({"ok": False, "error": UNSUPPORTED_SHELL_GRAMMAR_MESSAGE,
                           "measure_errors": parsed.measure_errors})
    return json.dumps({"ok": True, "stem": parsed.stem, "change_class": parsed.change_class,
                       "confidence": parsed.confidence, "verdict": parsed.verdict,
                       "measure_commands": len(parsed.commands),
                       "warning": None if parsed.commands else "no executable measure commands — receipt cannot be scored"})


@mcp.tool()
def gate_status(ledger: str = ".signalbrain/ledger.jsonl", window: int = 10) -> str:
    """Read per-class earned-autonomy standing from the ledger. Returns JSON."""
    p = Path(ledger)
    if not p.is_file():
        return json.dumps({"ok": True, "classes": {}, "note": "no ledger yet — no claims have been scored"})
    return json.dumps({"ok": True, "window": window, "classes": per_class(p, window=window)})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
