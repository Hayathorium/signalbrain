from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import signalbrain

ROOT = Path(__file__).resolve().parents[2]


def test_package_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert signalbrain.__version__ == pyproject["project"]["version"]


def test_cli_help_states_core_integrity_invariant():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "signalbrain.cli", "--help"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "only byte-identical, human-merged receipts" in result.stdout
    assert "increase earned trust" in result.stdout


def test_distribution_version_pins_match_package_version():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    version = pyproject["project"]["version"]

    action = (ROOT / "action.yml").read_text()
    assert f"signalbrain=={version}" in action

    server = json.loads((ROOT / "server.json").read_text())
    assert server["version"] == version
    package_versions = {
        pkg["version"]
        for pkg in server.get("packages", [])
        if pkg.get("identifier") == "signalbrain"
    }
    assert package_versions == {version}


def test_security_and_breach_docs_are_present():
    assert "Security Policy" in (ROOT / "SECURITY.md").read_text()
    breach = (ROOT / "docs/INTEGRITY_BREACH_RUNBOOK.md").read_text()
    assert "No unmerged, modified, self-scored" in breach
    assert "Circuit breaker integration" in breach


def test_license_is_declared_as_apache_2():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert pyproject["project"]["license"] == "Apache-2.0"
    license_text = (ROOT / "LICENSE").read_text()
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "http://www.apache.org/licenses/LICENSE-2.0" in license_text


def test_mcp_registry_description_stays_within_limit():
    server = json.loads((ROOT / "server.json").read_text())
    assert len(server["description"]) <= 100
