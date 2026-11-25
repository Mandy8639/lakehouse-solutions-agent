"""The solutions agent: two human gates around three allowlisted tools."""

from __future__ import annotations

from dataclasses import dataclass, field

from lakehouse_solutions import guardrail
from lakehouse_solutions.reasoner import LiveReasoner, StubReasoner
from lakehouse_solutions.tools import (
    ALLOWED_TOOLS,
    Draft,
    Solution,
    catalog_search,
    pipeline_plan,
    read_case,
    solution_draft,
)


@dataclass(frozen=True)
class AgentResult:
    """Everything one agent run produces (or refuses to produce)."""

    case_id: str
    decision: str  # PROPOSE | HOLD | PAUSE | BLOCK | REFUSED
    solution: Solution | None = None
    draft: Draft | None = None
    flags: dict = field(default_factory=dict)
    published: bool = False
    applied: bool = False
    sent: bool = False
    provenance: list[str] = field(default_factory=list)
    spend_usd: float = 0.0
    gates_checked: list[str] = field(default_factory=list)
    refusal: str = ""


class SolutionsAgent:
    """Bounded Data & AI solutions agent."""

    def __init__(self, mode: str = "stub", live_model: str | None = None) -> None:
        if mode not in ("stub", "live"):
            raise ValueError(f"unknown mode: {mode!r}")
        self.mode = mode
        self._live = LiveReasoner(model=live_model) if mode == "live" else None

    def plan(self) -> list[str]:
        """The tool plan, fixed and allowlisted. Gate 1 approves this plan."""
        return list(ALLOWED_TOOLS)

    def run(
        self,
        case_data: dict,
        *,
        approve_solution: bool,
        approve_deploy: bool,
    ) -> AgentResult:
        case = read_case(case_data)
        if not approve_solution:
            return AgentResult(
                case_id=case.id,
                decision="REFUSED",
                refusal="solution gate not approved: no tool ran",
                gates_checked=["solution"],
            )
        matches = catalog_search(case)
        plan = pipeline_plan(case) if matches else None
        injected = guardrail.scan_injection(case.notes)
        fabricated = guardrail.scan_fabrication(case.claims)
        missing = guardrail.missing_evidence(case)
        conflicts = guardrail.scan_table_conflicts(case)
        violations = guardrail.policy_violations(case)
        misrouted = guardrail.cross_requester_records(case)
        duplicates = [table.id for table in case.tables if table.duplicate_of is not None]
        flags = {
            "injection": [note.text for note in injected],
            "fabrication": [claim.text for claim in fabricated],
            "missing_evidence": missing,
            "table_conflicts": conflicts,
            "policy_violations": violations,
            "misrouted": misrouted,
            "duplicates": duplicates,
            "catalog_tables": [match.table.id for match in matches],
            "pipeline_planned": plan.table_id if plan is not None else None,
        }
        if self.mode == "live":
            assert self._live is not None
            decision, cost = self._live.decide(case, matches)
            spend = cost
        else:
            decision = StubReasoner().decide(
                case,
                matches,
                injection=bool(injected),
                fabrication=bool(fabricated),
                missing=bool(missing),
                conflicts=bool(conflicts),
                violations=bool(violations),
                remediation=bool(case.remediation_needed),
            )
            spend = 0.0
        solution = None
        draft = None
        published = False
        applied = False
        sent = False
        if decision == "PROPOSE" and matches:
            # Gate 1 (G1): the solution draft is issued only because a
            # human confirmed it. Gate 2 (G2): the pipeline or agent is
            # deployed and the message sent only with the second explicit
            # confirmation.
            best = matches[0].table
            solution = solution_draft(case, best.id)
            draft = solution.customer_message
            published = True
            applied = bool(approve_deploy)
            sent = bool(approve_deploy)
        return AgentResult(
            case_id=case.id,
            decision=decision,
            solution=solution,
            draft=draft,
            flags=flags,
            published=published,
            applied=applied,
            sent=sent,
            provenance=guardrail.cited_sources(case),
            spend_usd=spend,
            gates_checked=["solution", "deploy"],
        )
