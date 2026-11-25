"""Solution case: the single input to the agent.

A case is a synthetic customer request: a one-sentence request parsed
into requester, domain and freshness target, a shortlist of candidate
tables drawn from the governed catalog, notes from the customer or the
data team, and claims about the case. Every note and claim carries a
provenance source; a claim without a source is unsourced by construction
and the guardrail treats it as fabrication. Every table carries who may
see it: a table visible only to another requester is a misrouted record,
and the agent may never query or cite it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lakehouse_solutions.inventory import DOMAINS, REQUESTER_BY_ID


@dataclass(frozen=True)
class Column:
    """One column of a catalog table."""

    name: str
    dtype: str
    nullable: bool
    pii: bool = False
    description: str = ""


@dataclass(frozen=True)
class Table:
    """One table in the governed catalog, with facts copied from the corpus.

    ``schema`` and ``freshness_days`` are None when that fact is unknown
    (missing evidence, G3). ``requires`` names a human step that must be
    completed before any deployment (remediation). ``duplicate_of`` names
    the table this one duplicates, if any. ``visible_to`` is "shared" or
    one requester id: a table visible only to another requester is never
    queried or cited for this case (per-requester isolation, G3).
    """

    id: str
    domain: str
    name: str
    schema: list[Column] | None
    row_count: int | None
    freshness_days: int | None
    owner: str
    visible_to: str
    sensitivity: str
    description: str
    requires: str | None = None
    duplicate_of: str | None = None


@dataclass(frozen=True)
class Metric:
    """One named metric. The same name may be defined differently in two
    domains (e.g. "revenue" in sales vs finance): a request that needs
    both definitions is a policy conflict (G5)."""

    name: str
    domain: str
    table_id: str
    column: str
    agg: str
    definition: str


@dataclass(frozen=True)
class CaseNote:
    """One note from the customer or the data team. ``source`` is the table id.

    ``asserts`` holds machine-readable facts the note claims (e.g. a row
    count or a freshness). The guardrail compares them against the catalog:
    an assert that contradicts the catalog is a conflict (G5).
    """

    text: str
    source: str
    asserts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Claim:
    """One claim about the case. ``source`` may be None (unsourced)."""

    text: str
    source: str | None


@dataclass(frozen=True)
class Case:
    """A solutions case. All fields are required; see tools.read_case."""

    id: str
    category: str
    requester_id: str
    requester_name: str
    request_text: str
    domain: str
    freshness_target_days: int
    tables: list[Table] = field(default_factory=list)
    notes: list[CaseNote] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    remediation_needed: list[str] = field(default_factory=list)
    required_metrics: list[str] = field(default_factory=list)


def column_from_dict(data: dict) -> Column:
    return Column(
        name=data["name"],
        dtype=data["dtype"],
        nullable=data["nullable"],
        pii=data.get("pii", False),
        description=data.get("description", ""),
    )


def table_from_dict(data: dict) -> Table:
    schema = None
    if data.get("schema") is not None:
        schema = [column_from_dict(c) for c in data["schema"]]
    return Table(
        id=data["id"],
        domain=data["domain"],
        name=data["name"],
        schema=schema,
        row_count=data.get("row_count"),
        freshness_days=data.get("freshness_days"),
        owner=data["owner"],
        visible_to=data["visible_to"],
        sensitivity=data["sensitivity"],
        description=data["description"],
        requires=data.get("requires"),
        duplicate_of=data.get("duplicate_of"),
    )


def metric_from_dict(data: dict) -> Metric:
    return Metric(
        name=data["name"],
        domain=data["domain"],
        table_id=data["table_id"],
        column=data["column"],
        agg=data["agg"],
        definition=data["definition"],
    )


def case_from_dict(data: dict) -> Case:
    """Build a Case from a plain dict, validating required fields."""
    required = [
        "id",
        "category",
        "requester_id",
        "requester_name",
        "request_text",
        "domain",
        "freshness_target_days",
    ]
    for key in required:
        if key not in data or data[key] in (None, ""):
            raise ValueError(f"case is missing required field: {key}")
    if data["requester_id"] not in REQUESTER_BY_ID:
        raise ValueError(f"unknown requester: {data['requester_id']!r}")
    if data["domain"] not in DOMAINS:
        raise ValueError(f"unknown domain: {data['domain']!r}")
    tables = [table_from_dict(t) for t in data.get("tables", [])]
    notes = [
        CaseNote(text=n["text"], source=n["source"], asserts=dict(n.get("asserts", {})))
        for n in data.get("notes", [])
    ]
    claims = [Claim(text=c["text"], source=c.get("source")) for c in data.get("claims", [])]
    return Case(
        id=data["id"],
        category=data["category"],
        requester_id=data["requester_id"],
        requester_name=data["requester_name"],
        request_text=data["request_text"],
        domain=data["domain"],
        freshness_target_days=data["freshness_target_days"],
        tables=tables,
        notes=notes,
        claims=claims,
        required_evidence=list(data.get("required_evidence", [])),
        remediation_needed=list(data.get("remediation_needed", [])),
        required_metrics=list(data.get("required_metrics", [])),
    )


def column_to_dict(column: Column) -> dict:
    return {
        "name": column.name,
        "dtype": column.dtype,
        "nullable": column.nullable,
        "pii": column.pii,
        "description": column.description,
    }


def table_to_dict(table: Table) -> dict:
    return {
        "id": table.id,
        "domain": table.domain,
        "name": table.name,
        "schema": [column_to_dict(c) for c in table.schema] if table.schema is not None else None,
        "row_count": table.row_count,
        "freshness_days": table.freshness_days,
        "owner": table.owner,
        "visible_to": table.visible_to,
        "sensitivity": table.sensitivity,
        "description": table.description,
        "requires": table.requires,
        "duplicate_of": table.duplicate_of,
    }


def case_to_dict(case: Case) -> dict:
    """Serialise a Case back to a plain dict."""
    return {
        "id": case.id,
        "category": case.category,
        "requester_id": case.requester_id,
        "requester_name": case.requester_name,
        "request_text": case.request_text,
        "domain": case.domain,
        "freshness_target_days": case.freshness_target_days,
        "tables": [table_to_dict(t) for t in case.tables],
        "notes": [
            {"text": n.text, "source": n.source, "asserts": dict(n.asserts)} for n in case.notes
        ],
        "claims": [{"text": c.text, "source": c.source} for c in case.claims],
        "required_evidence": list(case.required_evidence),
        "remediation_needed": list(case.remediation_needed),
        "required_metrics": list(case.required_metrics),
    }
