"""End-to-end acceptance: receipt → merge → guard → score → gate, in a scratch repo.

Hermetic replacements for the reference-deployment-context contracts skipped in
tests/contracts/ (see conftest there). Covers SPEC §2 (merged-only scoring,
guard exit codes), §6.2 (same-PR pin classification on a real merge commit),
and §3 (class gate flip at n=10).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from signalbrain.gate import eligible_classes, per_class
from signalbrain.guard import CONTENT_DRIFT, REF_UNAVAILABLE, UNMERGED, check_merged
from signalbrain.scorer import ScoreConfig, score_receipt

RECEIPT_TMPL = """# {stem}

## Compared
- branch: `feat@abc`
- baseline: `origin/main@def`
- date: `2026-07-02`

## Change summary
{summary}

## Metric delta
| Metric | Baseline | Branch | Delta |
|---|---|---|---|
| thing | 1 | 2 | +1 |

### How measured
```bash
{command}
```

## Verdict
`improvement`

## Confidence
0.9

## change_class

tooling
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "receipts").mkdir()
    (root / "README.md").write_text("# scratch\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    return root


def _merge_receipt(root: Path, stem: str, command: str, extra: dict[str, str] | None = None) -> Path:
    path = root / "receipts" / f"{stem}.md"
    path.write_text(RECEIPT_TMPL.format(stem=stem, summary="a change", command=command))
    for rel, content in (extra or {}).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"merge {stem}")
    return path


def _cfg(root: Path, **kw) -> ScoreConfig:
    return ScoreConfig(root=root, ledger_path=root / "ledger.jsonl", merged_ref="HEAD", **kw)


def test_guard_refuses_unmerged_drifted_and_missing_ref(repo):
    unmerged = repo / "receipts" / "9999-unmerged.md"
    unmerged.write_text(RECEIPT_TMPL.format(stem="9999-unmerged", summary="x", command="python3 -c pass"))
    assert check_merged(repo, unmerged, merged_ref="HEAD").code == UNMERGED

    merged = _merge_receipt(repo, "0001-tooling-win", 'python3 -c "pass"')
    assert check_merged(repo, merged, merged_ref="HEAD").ok
    merged.write_text(merged.read_text().replace("0.9", "0.99"))
    assert check_merged(repo, merged, merged_ref="HEAD").code == CONTENT_DRIFT
    assert check_merged(repo, merged, merged_ref="refs/no/such").code == REF_UNAVAILABLE


def test_score_refuses_unmerged_but_scores_merged(repo):
    unmerged = repo / "receipts" / "9999-self-credit.md"
    unmerged.write_text(RECEIPT_TMPL.format(stem="9999-self-credit", summary="x", command='python3 -c "pass"'))
    result = score_receipt(unmerged, _cfg(repo))
    assert result["status"] == "refused_guard"
    assert not (repo / "ledger.jsonl").exists()

    merged = _merge_receipt(repo, "0001-tooling-win", 'python3 -c "pass"')
    result = score_receipt(merged, _cfg(repo))
    assert result["status"] == "scored"
    assert result["row"]["held"] is True
    assert "claim_kind" not in result["row"]  # python command → not a pin


def test_honest_failure_is_recorded(repo):
    merged = _merge_receipt(repo, "0002-tooling-fails", 'python3 -c "raise SystemExit(1)"')
    result = score_receipt(merged, _cfg(repo))
    assert result["status"] == "scored"
    assert result["row"]["held"] is False
    assert result["row"]["measure_errors"]


def test_unsupported_shell_grammar_is_recorded_as_measure_error(repo):
    merged = _merge_receipt(repo, "0003-tooling-shell-grammar", "pytest tests -q | grep passed")
    result = score_receipt(merged, _cfg(repo))
    assert result["status"] == "scored"
    assert result["row"]["held"] is False
    assert any("unsupported_shell_grammar" in err for err in result["row"]["measure_errors"])


def test_same_pr_test_only_receipt_is_pinned(repo):
    test_body = "def test_pin_me():\n    assert True\n"
    merged = _merge_receipt(
        repo, "0003-tooling-pin", "pytest tests/test_new_thing.py -q",
        extra={"tests/test_new_thing.py": test_body},
    )
    result = score_receipt(merged, _cfg(repo))
    assert result["status"] == "scored"
    assert result["row"]["claim_kind"] == "invariant_pin"


def test_preexisting_test_measure_is_not_pinned(repo):
    _merge_receipt(repo, "0000-seed", 'python3 -c "pass"', extra={"tests/test_old.py": "def test_old():\n    assert True\n"})
    merged = _merge_receipt(repo, "0004-tooling-behavioral", "pytest tests/test_old.py -q")
    result = score_receipt(merged, _cfg(repo))
    assert result["status"] == "scored"
    assert "claim_kind" not in result["row"]


def test_class_gate_flips_at_ten_held_claims(repo):
    ledger = repo / "ledger.jsonl"
    cfg = _cfg(repo)
    for i in range(10):
        merged = _merge_receipt(repo, f"00{10+i}-tooling-win", 'python3 -c "pass"')
        assert score_receipt(merged, cfg)["status"] == "scored"
        eligible = eligible_classes(ledger, window=10)
        if i < 9:
            assert eligible == [], f"eligible too early at n={i+1}"
    assert eligible_classes(ledger, window=10) == ["tooling"]
    status = per_class(ledger, window=10)["tooling"]
    assert status == {"hit_rate": 1.0, "n": 10, "status": "auto-merge ELIGIBLE"}


def test_pins_do_not_count_toward_eligibility(repo):
    ledger = repo / "ledger.jsonl"
    cfg = _cfg(repo)
    for i in range(10):
        merged = _merge_receipt(
            repo, f"00{30+i}-tooling-pin", f"pytest tests/test_p{i}.py -q",
            extra={f"tests/test_p{i}.py": f"def test_p{i}():\n    assert True\n"},
        )
        result = score_receipt(merged, cfg)
        assert result["row"]["claim_kind"] == "invariant_pin"
    assert eligible_classes(ledger, window=10) == []  # ten green pins earn nothing


def test_rescore_rewrites_in_place(repo):
    cfg = _cfg(repo)
    first = _merge_receipt(repo, "0050-tooling-first", 'python3 -c "raise SystemExit(1)"')
    score_receipt(first, cfg)
    second = _merge_receipt(repo, "0051-tooling-second", 'python3 -c "pass"')
    score_receipt(second, cfg)

    # Fix the first receipt's measure and re-merge, then rescore: row stays first.
    first.write_text(first.read_text().replace('raise SystemExit(1)', "pass"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fix measure")
    result = score_receipt(first, _cfg(repo, rescore=True))
    assert result["status"] == "replaced"
    rows = [json.loads(ln) for ln in (repo / "ledger.jsonl").read_text().splitlines()]
    assert [r["receipt_id"] for r in rows] == ["0050-tooling-first", "0051-tooling-second"]
    assert rows[0]["held"] is True
