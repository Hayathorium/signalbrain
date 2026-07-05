"""Receipt parsing — the executable-claim grammar (RECEIPT_SPEC.md §1).

Extracts confidence, verdict, change class, and the re-runnable measurement
commands from a receipt markdown file. Ports the incident-tested parsers from
neural-chat-v3 (`calibration_ingest_receipts` + `calibration_score_measured`).
"""

from __future__ import annotations

import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

VERDICTS = ("improvement", "parity", "regression", "not_applicable")
CHANGE_CLASSES = frozenset({"bugfix", "tooling", "config", "research", "unclassified"})
CODE_BLOCK = re.compile(r"```(?:bash|sh)?\n(.*?)```", re.S | re.I)
UNSUPPORTED_SHELL_GRAMMAR = "unsupported_shell_grammar"
UNSUPPORTED_SHELL_GRAMMAR_MESSAGE = (
    "shell grammar not supported — move the pipeline into a committed script and invoke it"
)
_UNSUPPORTED_SHELL_TOKENS = frozenset({"|", ">", ">>", "<", "&&", "||", ";"})
_CHANGE_CLASS_FOOTER_RE = re.compile(
    r"^## change_class\s*\r?\n\s*([a-z][a-z0-9_-]*)\s*(?:\r?\n|$)",
    re.MULTILINE | re.IGNORECASE,
)
_STEM_CLASS_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("research", ("research", "paper", "literature", "evidence-dispatch")),
    ("bugfix", ("fix", "guard", "deadlock", "skip", "misroute", "offload", "requeue", "tautology", "toctou")),
    ("tooling", ("ledger", "eval", "gate", "trace", "hook", "tooling", "calibration")),
    ("config", ("env", "parity", "config")),
)


def value_after(header: str, text: str, pattern: str) -> str | None:
    """First regex match on the non-blank lines after an exact ``## header``."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == header:
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    m = re.search(pattern, nxt, re.I)
                    if m:
                        return m.group(0)
            break
    return None


def change_class_from_stem(stem: str) -> str:
    s = (stem or "").lower()
    for name, keywords in _STEM_CLASS_KEYWORDS:
        if any(k in s for k in keywords):
            return name
    return "unclassified"


def change_class_of(text: str, *, stem: str = "") -> str:
    """Footer wins over stem keywords (RECEIPT_SPEC.md §1)."""
    match = _CHANGE_CLASS_FOOTER_RE.search(text or "")
    if match:
        value = match.group(1).strip().lower()
        if value in CHANGE_CLASSES:
            return value
    return change_class_from_stem(stem)


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


def unsupported_shell_tokens(line: str) -> list[str]:
    """Bare shell control operators are not part of the measure argv grammar."""
    tokens = _safe_split(line)
    return [tok for tok in tokens if tok in _UNSUPPORTED_SHELL_TOKENS]


def measure_grammar_errors(text: str) -> list[str]:
    errors: list[str] = []
    section = how_measured_section(text)
    for match in CODE_BLOCK.finditer(section):
        body = match.group(1).strip()
        if not body or body.lower().startswith("not measured"):
            continue
        for line in _logical_lines(body):
            _, command_line = _split_inline_env_prefix(line)
            tokens = unsupported_shell_tokens(command_line)
            if tokens:
                errors.append(f"{UNSUPPORTED_SHELL_GRAMMAR}: {UNSUPPORTED_SHELL_GRAMMAR_MESSAGE}")
    return errors


def _split_inline_env_prefix(line: str) -> tuple[list[str], str]:
    """Split leading VAR=value tokens into synthetic export lines."""
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


def _parse_command_line(line: str) -> list[str] | None:
    if line.startswith("export "):
        return None
    _, line = _split_inline_env_prefix(line)
    if unsupported_shell_tokens(line):
        return None
    if line.startswith("pytest "):
        return ["pytest"] + _safe_split(line[len("pytest ") :])
    if "-m pytest" in line:
        tail = line.split("-m pytest", 1)[1].strip()
        return [sys.executable, "-m", "pytest"] + (_safe_split(tail) if tail else [])
    if line.startswith("bash "):
        rest = line[len("bash ") :].strip()
        parts = _safe_split(rest)
        if parts and parts[0].endswith(".sh"):
            return ["/bin/bash", *parts]
        return ["/bin/bash", "-lc", rest]
    if line.startswith(("python3 ", "python ")):
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


@dataclass
class Receipt:
    path: Path
    stem: str
    confidence: float
    verdict: str
    change_class: str
    exports: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    measure_errors: list[str] = field(default_factory=list)


def parse_receipt(path: Path) -> Receipt | None:
    """Parse a receipt file; None if unscoreable (missing fields / not_applicable)."""
    text = path.read_text(encoding="utf-8")
    conf = value_after("## Confidence", text, r"0?\.\d+|1\.0")
    verd = value_after("## Verdict", text, "|".join(VERDICTS))
    if conf is None or verd is None:
        return None
    verd = verd.lower()
    if verd == "not_applicable":
        return None
    exports, commands = extract_commands_with_env(text)
    measure_errors = measure_grammar_errors(text)
    stem = path.stem
    return Receipt(
        path=path,
        stem=stem,
        confidence=float(conf),
        verdict=verd,
        change_class=change_class_of(text, stem=stem),
        exports=exports,
        commands=commands,
        measure_errors=measure_errors,
    )
