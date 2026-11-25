"""End-to-end tests for the solutions agent."""

from __future__ import annotations

import pytest

from lakehouse_solutions.agent import SolutionsAgent
from tests.conftest import clean_case


def test_clean_case_proposes_deploys_and_sends_with_both_gates(agent) -> None:
    result = agent.run(clean_case(), approve_solution=True, approve_deploy=True)
    assert result.decision == "PROPOSE"
    assert result.solution is not None
    assert result.solution.table_id == "S001"  # freshest confirmed match
    assert result.solution.status == "draft"
    assert result.solution.shared is False
    assert result.solution.deployed is False
    assert result.solution.query.sql == "SELECT SUM(amount) AS revenue FROM sales_orders"
    assert result.solution.query.table_id == "S001"
    assert result.solution.pipeline.table_id == "S001"
    assert len(result.solution.pipeline.stages) == 3
    assert result.draft is not None
    assert result.draft.sent is False
    assert result.draft.to_requester_id == "REQ-01"
    assert result.published is True
    assert result.applied is True
    assert result.sent is True
    assert result.spend_usd == 0.0
    assert result.gates_checked == ["solution", "deploy"]
    assert result.provenance == ["S001", "agreement-001"]


def test_clean_case_solution_carries_the_customer_message_draft(agent) -> None:
    result = agent.run(clean_case(), approve_solution=True, approve_deploy=True)
    assert result.solution is not None
    assert result.draft is result.solution.customer_message
    assert result.draft.purpose == "share_solution"
    assert "S001" in result.draft.subject
    assert "sales_orders" in result.draft.body


def test_clean_case_pipeline_plan_is_recorded_in_flags(agent) -> None:
    result = agent.run(clean_case(), approve_solution=True, approve_deploy=True)
    assert result.flags["pipeline_planned"] == "S001"
    assert result.flags["catalog_tables"] == ["S001", "S004"]


def test_plan_is_the_three_allowlisted_tools(agent) -> None:
    assert agent.plan() == ["catalog_search", "pipeline_plan", "solution_draft"]


def test_agent_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        SolutionsAgent(mode="oracle")


def test_remediation_holds(agent) -> None:
    data = clean_case()
    data["remediation_needed"] = [
        "sales_returns requires finance approval for a refund policy change "
        "— a human must complete this before any deployment."
    ]
    result = agent.run(data, approve_solution=True, approve_deploy=True)
    assert result.decision == "HOLD"
    assert result.published is False
    assert result.applied is False
    assert result.sent is False


def test_live_agent_refuses_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    agent = SolutionsAgent(mode="live")
    with pytest.raises(RuntimeError, match="no ANTHROPIC_API_KEY"):
        agent.run(clean_case(), approve_solution=True, approve_deploy=True)
