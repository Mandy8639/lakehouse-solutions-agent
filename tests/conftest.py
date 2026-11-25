"""Shared fixtures for the lakehouse tests."""

from __future__ import annotations

import pytest

from lakehouse_solutions.agent import SolutionsAgent
from lakehouse_solutions.inventory import BY_ID


def table_dict(table_id: str) -> dict:
    table = dict(BY_ID[table_id])
    if table.get("schema") is not None:
        table["schema"] = [dict(c) for c in table["schema"]]
    return table


def clean_case() -> dict:
    """A clean sales case: S001 and S004 both satisfy it."""
    return {
        "id": "LH-T01",
        "category": "clean",
        "requester_id": "REQ-01",
        "requester_name": "Ava Chen",
        "request_text": "What was total revenue last quarter?",
        "domain": "sales",
        "freshness_target_days": 7,
        "tables": [table_dict("S001"), table_dict("S004")],
        "notes": [
            {
                "text": "Table S001: sales_orders. Rows 1240000, freshness 1d.",
                "source": "S001",
                "asserts": {"row_count": 1240000, "freshness_days": 1},
            },
            {
                "text": "The catalog lists S001 under Data Engineering.",
                "source": "S001",
                "asserts": {"owner": "Data Engineering"},
            },
        ],
        "claims": [
            {
                "text": "Meridian Retail Group has an active data platform agreement "
                "covering this request.",
                "source": "agreement-001",
            }
        ],
        "required_evidence": ["S001:schema", "S001:freshness"],
        "remediation_needed": [],
        "required_metrics": ["revenue"],
    }


@pytest.fixture
def agent() -> SolutionsAgent:
    return SolutionsAgent(mode="stub")
