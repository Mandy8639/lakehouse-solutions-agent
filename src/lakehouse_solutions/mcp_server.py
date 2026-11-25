"""Minimal MCP server (stdio JSON-RPC 2.0), no external dependencies.

Exposes the three allowlisted tools over the Model Context Protocol:
tools/list and tools/call. Run: python -m lakehouse_solutions.mcp_server
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from lakehouse_solutions.tools import (
    ALLOWED_TOOLS,
    catalog_search,
    pipeline_plan,
    read_case,
    solution_draft,
)

TOOLS = {
    "catalog_search": {
        "description": "Governed tables the requester may see, freshest first.",
        "inputSchema": {
            "type": "object",
            "properties": {"case": {"type": "object"}},
            "required": ["case"],
        },
    },
    "pipeline_plan": {
        "description": "A governed ingest -> transform -> serve plan. Plan only; "
        "it deploys nothing.",
        "inputSchema": {
            "type": "object",
            "properties": {"case": {"type": "object"}},
            "required": ["case"],
        },
    },
    "solution_draft": {
        "description": "Draft a production solution for one matching table. Never "
        "shares it with the customer or deploys anything; the Genie-style "
        "NL-to-SQL query and the pipeline plan travel inside the draft.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "case": {"type": "object"},
                "table_id": {"type": "string"},
            },
            "required": ["case", "table_id"],
        },
    },
}


def _tool_result(payload: object) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def handle(request: dict) -> dict | None:
    """Handle one JSON-RPC request. Returns None for notifications."""
    method = request.get("method", "")
    request_id = request.get("id")
    params = request.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "lakehouse-solutions-agent", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method.startswith("notifications/"):
        return None
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {"name": name, **spec} for name, spec in TOOLS.items() if name in ALLOWED_TOOLS
                ]
            },
        }
    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}
        try:
            if name == "catalog_search":
                case = read_case(arguments["case"])
                matches = catalog_search(case)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result([asdict(match) for match in matches]),
                }
            if name == "pipeline_plan":
                case = read_case(arguments["case"])
                plan = pipeline_plan(case)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result(asdict(plan)),
                }
            if name == "solution_draft":
                case = read_case(arguments["case"])
                solution = solution_draft(case, arguments["table_id"])
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result(asdict(solution)),
                }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
        except (KeyError, ValueError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": str(exc)},
            }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
