"""Contract: only human-merged receipts may be objectively scored (Track 1).

Observed 2026-07-02: an unmerged, untracked receipt was scored held=true into
the measured ledger — a lane crediting itself for work that never survived
review. `calibration_receipt_merged_check.sh` fail-closes the scoring wrapper:

- receipt not on the merged ref (or outside the repo)  -> exit 3
- receipt content differs from the merged content      -> exit 4
- merged ref unavailable                               -> exit 5 (no silent pass)
- CALIBRATION_ALLOW_UNMERGED=1                         -> explicit supervised bypass
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CHECK = REPO / "scripts" / "calibration_receipt_merged_check.sh"
WRAPPER = REPO / "scripts" / "calibration_score_receipt.sh"
MERGED_RECEIPT = REPO / "docs" / "improvements" / "0570-calibration-bash-measure-fix.md"


def _run(args: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env_extra or {})}
    env.pop("CALIBRATION_ALLOW_UNMERGED", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(CHECK), *args], capture_output=True, text=True, env=env, cwd=REPO
    )


def _ref_available(ref: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            capture_output=True,
        ).returncode
        == 0
    )


def test_guard_script_exists_and_wired_into_wrapper():
    assert CHECK.is_file() and CHECK.stat().st_mode & 0o111
    assert "calibration_receipt_merged_check.sh" in WRAPPER.read_text(encoding="utf-8")


def test_unmerged_receipt_outside_repo_refused(tmp_path):
    receipt = tmp_path / "9999-unmerged-self-credit.md"
    receipt.write_text("# fake\n", encoding="utf-8")
    proc = _run([str(receipt)], {"CALIBRATION_MERGED_REF": "HEAD"})
    assert proc.returncode == 3
    assert "human-merged" in proc.stderr


def test_untracked_receipt_in_repo_refused(tmp_path):
    # Simulates the observed incident: an untracked receipt under docs/improvements/.
    # Uses HEAD as the merged ref so the check is hermetic to fetch state.
    name = "9999-contract-tmp-unmerged-receipt.md"
    target = REPO / "docs" / "improvements" / name
    assert not target.exists()
    target.write_text("# fake unmerged receipt\n", encoding="utf-8")
    try:
        proc = _run([str(target)], {"CALIBRATION_MERGED_REF": "HEAD"})
        assert proc.returncode == 3
    finally:
        target.unlink()


def test_merged_receipt_with_identical_content_passes():
    proc = _run([str(MERGED_RECEIPT)], {"CALIBRATION_MERGED_REF": "HEAD"})
    assert proc.returncode == 0, proc.stderr


def test_modified_copy_of_merged_receipt_refused(tmp_path):
    doctored = tmp_path / MERGED_RECEIPT.name
    shutil.copy(MERGED_RECEIPT, doctored)
    doctored.write_text(
        MERGED_RECEIPT.read_text(encoding="utf-8").replace("0.93", "0.99"), encoding="utf-8"
    )
    proc = _run([str(MERGED_RECEIPT), str(doctored)], {"CALIBRATION_MERGED_REF": "HEAD"})
    assert proc.returncode == 4
    assert "differs" in proc.stderr


def test_missing_ref_fails_closed(tmp_path):
    receipt = tmp_path / "9999-x.md"
    receipt.write_text("# fake\n", encoding="utf-8")
    proc = _run([str(receipt)], {"CALIBRATION_MERGED_REF": "refs/no/such/ref"})
    assert proc.returncode == 5


def test_explicit_override_allows_supervised_scoring(tmp_path):
    receipt = tmp_path / "9999-supervised-experiment.md"
    receipt.write_text("# fake\n", encoding="utf-8")
    proc = _run([str(receipt)], {"CALIBRATION_ALLOW_UNMERGED": "1"})
    assert proc.returncode == 0


@pytest.mark.skipif(not _ref_available("origin/main"), reason="origin/main not fetched")
def test_default_ref_is_origin_main():
    text = CHECK.read_text(encoding="utf-8")
    assert 'CALIBRATION_MERGED_REF:-origin/main' in text
