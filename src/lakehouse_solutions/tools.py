"""The three allowlisted tools. Nothing else may touch a case.

1. catalog_search — governed tables the requester may see, most fresh first.
2. pipeline_plan — an ingest -> transform -> serve plan. Plan only; it
   deploys nothing.
3. solution_draft — a production solution draft for a Senior FDE to
   approve. It shares nothing and deploys nothing; the Genie-style
   NL-to-SQL query it cites runs inside the draft as its evidence step,
   over governed tables only.

The NL-to-SQL step itself is built by ``nl_to_sql`` (a helper, not a
tool) and travels inside the solution draft, so the draft is the only
place a query against the catalog can originate.
"""

from __future__ import annotations

from dataclasses import dataclass

from lakehouse_solutions import guardrail
from lakehouse_solutions.inventory import METRICS, TABLES
from lakehouse_solutions.packet import Case, Table, case_from_dict, table_from_dict

ALLOWED_TOOLS = (
    "catalog_search",
    "pipeline_plan",
    "solution_draft",
)

MESSAGE_PURPOSES = (
    "share_solution",
    "request_info",
    "escalation_notice",
)


@dataclass(frozen=True)
class TableMatch:
    """One table that can satisfy the case, with its provenance source."""

    table: Table
    source: str


@dataclass(frozen=True)
class Query:
    """A Genie-style NL-to-SQL query over one governed table.

    The SQL cites only tables the requester may see and columns the
    catalog knows. It answers the request; it never invents a table, a
    column, or a metric definition.
    """

    sql: str
    table_id: str
    columns: list[str]
    metric: str | None


@dataclass(frozen=True)
class PipelinePlan:
    """An ingest -> transform -> serve plan. Plan only: nothing is deployed."""

    table_id: str
    stages: list[str]
    eval_plan: str


@dataclass(frozen=True)
class Draft:
    """A drafted message to the customer. ``sent`` is always False: it sends nothing."""

    to_customer: str
    to_requester_id: str
    purpose: str
    subject: str
    body: str
    sent: bool = False


@dataclass(frozen=True)
class Solution:
    """A drafted production solution. Status is always 'draft': it shares
    nothing and deploys nothing.

    ``shared`` and ``deployed`` are always False on the draft itself —
    only human confirmations (gates 1 and 2) may flip them on the agent
    result.
    """

    table_id: str
    requester_id: str
    summary: str
    query: Query
    pipeline: PipelinePlan
    steps: list[str]
    customer_message: Draft
    status: str = "draft"
    shared: bool = False
    deployed: bool = False


def catalog_search(case: Case) -> list[TableMatch]:
    """Tool 1: tables that can satisfy the case, freshest first.

    A table matches only when every fact is known and passes: it is
    visible to the case's requester (per-requester isolation), its domain
    matches, its schema and freshness are known, and its freshness is
    within its domain's ceiling and the case's target. Unknown facts
    exclude the table (G3) rather than being guessed.
    """
    matches = []
    for table in case.tables:
        if table.visible_to not in ("shared", case.requester_id):
            continue
        if table.domain != case.domain:
            continue
        if table.duplicate_of is not None:
            continue
        if table.schema is None or table.freshness_days is None:
            continue
        if table.freshness_days > guardrail.DOMAIN_MAX_STALENESS[table.domain]:
            continue
        if table.freshness_days > case.freshness_target_days:
            continue
        matches.append(TableMatch(table=table, source=table.id))
    matches.sort(key=lambda match: (match.table.freshness_days or 0, match.table.id))
    return matches


def pipeline_plan(case: Case) -> PipelinePlan:
    """Tool 2: a governed pipeline plan for the case's best table.

    The plan is ingest -> transform -> serve, with Spark-style stages.
    It plans only: no data moves, no pipeline is created, nothing is
    deployed. Only a case with a matching governed table can be planned.
    """
    matches = catalog_search(case)
    if not matches:
        raise ValueError("no governed table matches this case")
    table = matches[0].table
    stages = [
        f"Ingest: source system -> bronze table {table.name}_bronze "
        "(append-only, raw, PII-tagged columns flagged).",
        f"Transform: Spark-style job bronze -> silver (clean, dedupe, "
        f"type-cast, freshness {table.freshness_days}d) with data-quality checks.",
        f"Serve: silver -> gold governed view {table.name}_gold "
        "(Unity Catalog-style permissions, audit on, requester-scoped access).",
    ]
    return PipelinePlan(
        table_id=table.id,
        stages=stages,
        eval_plan="Validate the solution against the frozen 48-case eval "
        "before sharing it with the customer.",
    )


def nl_to_sql(case: Case, table: Table) -> Query:
    """Genie-style NL-to-SQL over one governed table (helper, not a tool).

    The metric is picked by keyword from the request, matched to this
    table and this domain only. With no metric keyword the query falls
    back to a row count over the same table. The SQL never references a
    table the requester may not see or a column the catalog does not know.
    """
    request = case.request_text.lower()
    for metric in METRICS:
        if metric["domain"] != case.domain or metric["table_id"] != table.id:
            continue
        if metric["name"] in request:
            return Query(
                sql=f"SELECT {metric['agg']}({metric['column']}) AS {metric['name']} "
                f"FROM {table.name}",
                table_id=table.id,
                columns=[metric["column"]],
                metric=metric["name"],
            )
    return Query(
        sql=f"SELECT COUNT(*) AS row_count FROM {table.name}",
        table_id=table.id,
        columns=[],
        metric=None,
    )


def customer_message(case: Case, table: Table, purpose: str) -> Draft:
    """Build a message draft to the customer. It is never sent.

    The body cites catalog facts only — never a fact the catalog does
    not know — and any PII quoted from the table is redacted before the
    draft leaves the catalog (G3).
    """
    if purpose not in MESSAGE_PURPOSES:
        raise ValueError(f"unknown message purpose: {purpose!r}")
    description = guardrail.redact_pii(table.description)
    if purpose == "share_solution":
        subject = f"Proposed solution — {table.name} ({table.id})"
        body = (
            f"Hello {case.requester_name}, we have a proposed solution for "
            f"'{case.request_text}' over {table.id} ({table.name}). "
            f"Catalog note: {description} Please confirm before we share it "
            f"with your team — nothing is deployed until a Senior FDE confirms. "
            f"Freshness target: {case.freshness_target_days}d."
        )
    elif purpose == "request_info":
        subject = f"More information needed — {table.name} ({table.id})"
        body = (
            f"Hello {case.requester_name}, we need one more detail to plan "
            f"the solution over {table.id} ({table.name}). Catalog note: "
            f"{description} Could you confirm which metric this should answer?"
        )
    else:  # escalation_notice
        subject = f"Escalation — {table.name} ({table.id})"
        body = (
            f"Hello {case.requester_name}, {table.id} ({table.name}) has been "
            f"escalated to a Senior FDE for review. Catalog note: "
            f"{description} We will update you once they have looked at it."
        )
    return Draft(
        to_customer="Meridian Retail Group",
        to_requester_id=case.requester_id,
        purpose=purpose,
        subject=subject,
        body=body,
    )


def solution_draft(case: Case, table_id: str) -> Solution:
    """Tool 3: draft a production solution for one matching table.

    The solution is a draft: it shares nothing with the customer and
    deploys nothing. Only a table returned by catalog_search may be
    drafted. The Genie-style NL-to-SQL query runs inside the draft as
    its evidence step, over the governed table only, and the pipeline
    plan travels inside the draft. The customer message travels inside
    the draft too.
    """
    matches = {match.table.id: match for match in catalog_search(case)}
    if table_id not in matches:
        raise ValueError(f"table {table_id!r} is not a confirmed match for this case")
    table = matches[table_id].table
    query = nl_to_sql(case, table)
    plan = pipeline_plan(case)
    steps = [
        f"Answer the request with the governed query over {table.id} ({table.name}): {query.sql}",
        *[f"Pipeline: {stage}" for stage in plan.stages],
        f"Confirm the result with the requester before sharing "
        f"(freshness target {case.freshness_target_days}d).",
    ]
    if table.requires:
        steps.append(f"Pre-deployment step (human): {table.requires}")
    steps.append("Senior FDE confirmation required before sharing or deploying anything.")
    summary = guardrail.redact_pii(table.description)
    return Solution(
        table_id=table.id,
        requester_id=case.requester_id,
        summary=summary,
        query=query,
        pipeline=plan,
        steps=steps,
        customer_message=customer_message(case, table, "share_solution"),
    )


def read_case(data: dict) -> Case:
    """Load and validate a case. Raises ValueError if malformed."""
    return case_from_dict(data)


def table_by_id(table_id: str) -> Table:
    """Look a catalog table up by id (for tests and the MCP server)."""
    for data in TABLES:
        if data["id"] == table_id:
            return table_from_dict(data)
    raise ValueError(f"unknown table: {table_id!r}")
