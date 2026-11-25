"""Tests for the three allowlisted tools."""

from __future__ import annotations

import pytest

from lakehouse_solutions.packet import case_from_dict
from lakehouse_solutions.tools import (
    ALLOWED_TOOLS,
    catalog_search,
    nl_to_sql,
    pipeline_plan,
    read_case,
    solution_draft,
)
from tests.conftest import clean_case, table_dict


def test_only_three_tools_are_allowlisted() -> None:
    assert list(ALLOWED_TOOLS) == ["catalog_search", "pipeline_plan", "solution_draft"]


def test_read_case_validates() -> None:
    with pytest.raises(ValueError, match="unknown requester"):
        read_case({**clean_case(), "requester_id": "REQ-99"})
    with pytest.raises(ValueError, match="unknown domain"):
        read_case({**clean_case(), "domain": "marketing"})


def test_catalog_search_returns_only_visible_fresh_known_tables() -> None:
    case = case_from_dict(clean_case())
    matches = catalog_search(case)
    assert [match.table.id for match in matches] == ["S001", "S004"]
    assert matches[0].source == "S001"


def test_catalog_search_sorts_freshest_first() -> None:
    data = clean_case()
    data["tables"] = [table_dict("S002"), table_dict("S001"), table_dict("S003")]
    case = case_from_dict(data)
    assert [m.table.id for m in catalog_search(case)] == ["S001", "S003", "S002"]


def test_catalog_search_excludes_unknown_fields_and_duplicates() -> None:
    data = clean_case()
    data["tables"] = [
        table_dict("S006"),  # freshness unknown
        table_dict("S007"),  # schema unknown
        table_dict("P004"),  # both unknown
        table_dict("D001"),  # duplicate of S001
        table_dict("S001"),  # the only viable one
    ]
    case = case_from_dict(data)
    assert [m.table.id for m in catalog_search(case)] == ["S001"]


def test_catalog_search_respects_permissions() -> None:
    data = clean_case()
    data["tables"] = [table_dict("F005"), table_dict("F001")]
    data["requester_id"] = "REQ-02"
    data["requester_name"] = "Marcus Webb"
    data["domain"] = "finance"
    data["freshness_target_days"] = 30
    case = case_from_dict(data)
    # REQ-02 may see both, so both match; REQ-01 may see neither payroll.
    assert [m.table.id for m in catalog_search(case)] == ["F001", "F005"]
    data["requester_id"] = "REQ-01"
    data["requester_name"] = "Ava Chen"
    case = case_from_dict(data)
    assert [m.table.id for m in catalog_search(case)] == ["F001"]


def test_catalog_search_respects_freshness_target() -> None:
    data = clean_case()
    data["tables"] = [table_dict("S002"), table_dict("S005")]
    data["freshness_target_days"] = 2
    case = case_from_dict(data)
    assert [m.table.id for m in catalog_search(case)] == ["S002"]


def test_catalog_search_excludes_tables_over_the_domain_max() -> None:
    data = clean_case()
    table = table_dict("F003")
    table["freshness_days"] = 60  # finance max is 45d
    data["tables"] = [table]
    data["requester_id"] = "REQ-02"
    data["requester_name"] = "Marcus Webb"
    data["domain"] = "finance"
    data["freshness_target_days"] = 90
    case = case_from_dict(data)
    assert catalog_search(case) == []


def test_catalog_search_excludes_other_domains() -> None:
    data = clean_case()
    data["tables"] = [table_dict("P001"), table_dict("S001")]
    case = case_from_dict(data)
    assert [m.table.id for m in catalog_search(case)] == ["S001"]


def test_pipeline_plan_has_three_spark_style_stages() -> None:
    case = case_from_dict(clean_case())
    plan = pipeline_plan(case)
    assert plan.table_id == "S001"
    assert len(plan.stages) == 3
    assert "Ingest" in plan.stages[0]
    assert "Spark" in plan.stages[1]
    assert "Unity Catalog" in plan.stages[2]
    assert "48-case" in plan.eval_plan


def test_pipeline_plan_requires_a_match() -> None:
    data = clean_case()
    data["tables"] = [table_dict("S006")]  # freshness unknown: no match
    case = case_from_dict(data)
    with pytest.raises(ValueError, match="no governed table matches"):
        pipeline_plan(case)


def test_nl_to_sql_uses_the_metric_of_the_domain() -> None:
    case = case_from_dict(clean_case())
    query = nl_to_sql(case, table_from_inventory("S001"))
    assert query.sql == "SELECT SUM(amount) AS revenue FROM sales_orders"
    assert query.table_id == "S001"


def table_from_inventory(table_id: str):  # helper: table dataclass from the inventory
    from lakehouse_solutions.inventory import BY_ID
    from lakehouse_solutions.packet import table_from_dict

    return table_from_dict(BY_ID[table_id])


def test_nl_to_sql_falls_back_to_a_count() -> None:
    data = clean_case()
    data["request_text"] = "How many rows are in the orders table?"
    case = case_from_dict(data)
    query = nl_to_sql(case, table_from_inventory("S001"))
    assert query.sql == "SELECT COUNT(*) AS row_count FROM sales_orders"


def test_nl_to_sql_uses_the_metric_definition() -> None:
    data = clean_case()
    data["request_text"] = "What was total revenue invoiced this year?"
    data["tables"] = [table_dict("F001")]
    data["requester_id"] = "REQ-02"
    data["requester_name"] = "Marcus Webb"
    data["domain"] = "finance"
    data["freshness_target_days"] = 30
    case = case_from_dict(data)
    query = nl_to_sql(case, table_from_inventory("F001"))
    assert query.sql == "SELECT SUM(amount) AS revenue FROM finance_invoices"


def test_solution_draft_is_a_draft_only() -> None:
    case = case_from_dict(clean_case())
    solution = solution_draft(case, "S001")
    assert solution.status == "draft"
    assert solution.shared is False
    assert solution.deployed is False
    assert solution.table_id == "S001"
    assert solution.query.sql == "SELECT SUM(amount) AS revenue FROM sales_orders"
    assert solution.pipeline.table_id == "S001"
    assert solution.customer_message.sent is False
    assert solution.customer_message.purpose == "share_solution"
    assert solution.customer_message.to_requester_id == "REQ-01"
    assert "S001" in solution.customer_message.subject


def test_solution_draft_rejects_a_table_outside_the_catalog() -> None:
    case = case_from_dict(clean_case())
    with pytest.raises(ValueError, match="not a confirmed match"):
        solution_draft(case, "S999")


def test_solution_draft_rejects_a_restricted_table() -> None:
    data = clean_case()
    data["tables"] = [table_dict("F005")]
    data["requester_id"] = "REQ-03"
    data["requester_name"] = "Priya Nair"
    data["domain"] = "finance"
    data["freshness_target_days"] = 30
    case = case_from_dict(data)
    with pytest.raises(ValueError, match="not a confirmed match"):
        solution_draft(case, "F005")


def test_solution_draft_rejects_a_table_with_unknown_fields() -> None:
    data = clean_case()
    data["tables"] = [table_dict("S006")]
    case = case_from_dict(data)
    with pytest.raises(ValueError, match="not a confirmed match"):
        solution_draft(case, "S006")
