"""MCP server e2e: a real client session over stdio, as goose would drive it."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

mcp_sdk = pytest.importorskip("mcp", reason="install signalbrain[mcp]")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _server_params() -> StdioServerParameters:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "signalbrain.mcp_server"],
        cwd=ROOT,
        env=env,
    )


@pytest.mark.anyio
async def test_emit_validate_gate_roundtrip(tmp_path):
    params = _server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"emit_receipt", "validate_receipt", "gate_status"} <= names

            result = await session.call_tool("emit_receipt", {
                "slug": "add-widget",
                "change_class": "tooling",
                "title": "add widget",
                "change_summary": "Adds the widget.",
                "how_measured_commands": ['python3 -c "pass"'],
                "confidence": 0.9,
                "date": "2026-07-05",
                "repo_root": str(tmp_path),
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"], payload
            assert payload["stem"] == "0001-tooling-add-widget"
            receipt = tmp_path / payload["path"]
            assert receipt.is_file()

            v = await session.call_tool("validate_receipt", {"path": str(receipt)})
            vp = json.loads(v.content[0].text)
            assert vp["ok"] and vp["confidence"] == 0.9 and vp["measure_commands"] == 1

            g = await session.call_tool("gate_status", {"ledger": str(tmp_path / "none.jsonl")})
            gp = json.loads(g.content[0].text)
            assert gp["ok"] and gp["classes"] == {}


@pytest.mark.anyio
async def test_emit_refuses_dishonest_inputs(tmp_path):
    params = _server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # no date — the server does not guess dates
            r = await session.call_tool("emit_receipt", {
                "slug": "x", "change_class": "tooling", "title": "x",
                "change_summary": "x", "how_measured_commands": ["python3 -c pass"],
                "confidence": 0.9, "repo_root": str(tmp_path),
            })
            assert not json.loads(r.content[0].text)["ok"]
            # disallowed measure leader — grammar validation kills the file
            r = await session.call_tool("emit_receipt", {
                "slug": "y", "change_class": "tooling", "title": "y",
                "change_summary": "y", "how_measured_commands": ["python3 scripts/check.py | grep ok"],
                "confidence": 0.9, "date": "2026-07-05", "repo_root": str(tmp_path),
            })
            payload = json.loads(r.content[0].text)
            assert not payload["ok"]
            assert "shell grammar not supported" in payload["error"]
            assert not list((tmp_path / "receipts").glob("*-y.md"))


@pytest.fixture
def anyio_backend():
    return "asyncio"
