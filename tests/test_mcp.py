"""Tests for the MCP server (stdio JSON-RPC 2.0)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import clean_case

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _run_server(requests: list[dict]) -> list[dict]:
    """Send JSON-RPC requests to the MCP server, return its responses."""
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    payload = "".join(json.dumps(request) + "\n" for request in requests)
    proc = subprocess.run(
        [sys.executable, "-m", "lakehouse_solutions.mcp_server"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def test_initialize_names_the_server() -> None:
    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
            }
        ]
    )
    assert len(responses) == 1
    assert responses[0]["result"]["serverInfo"]["name"] == "lakehouse-solutions-agent"


def test_tools_list_exposes_exactly_three_tools() -> None:
    responses = _run_server([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = responses[0]["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "catalog_search",
        "pipeline_plan",
        "solution_draft",
    ]


def test_tools_call_catalog_search() -> None:
    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "catalog_search", "arguments": {"case": clean_case()}},
            }
        ]
    )
    content = json.loads(responses[0]["result"]["content"][0]["text"])
    assert [match["table"]["id"] for match in content] == ["S001", "S004"]


def test_tools_call_pipeline_plan() -> None:
    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "pipeline_plan", "arguments": {"case": clean_case()}},
            }
        ]
    )
    content = json.loads(responses[0]["result"]["content"][0]["text"])
    assert content["table_id"] == "S001"
    assert len(content["stages"]) == 3


def test_tools_call_solution_draft() -> None:
    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "solution_draft",
                    "arguments": {"case": clean_case(), "table_id": "S001"},
                },
            }
        ]
    )
    content = json.loads(responses[0]["result"]["content"][0]["text"])
    assert content["table_id"] == "S001"
    assert content["status"] == "draft"
    assert content["shared"] is False
    assert content["deployed"] is False
    assert content["query"]["sql"] == "SELECT SUM(amount) AS revenue FROM sales_orders"


def test_unknown_tool_returns_an_error() -> None:
    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "deploy_pipeline", "arguments": {}},
            }
        ]
    )
    assert responses[0]["error"]["code"] == -32602


def test_unknown_method_returns_an_error() -> None:
    responses = _run_server([{"jsonrpc": "2.0", "id": 1, "method": "resources/list"}])
    assert responses[0]["error"]["code"] == -32601


def test_notifications_get_no_response() -> None:
    responses = _run_server(
        [
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        ]
    )
    assert len(responses) == 1
    assert responses[0]["id"] == 1
    assert responses[0]["result"] == {}
