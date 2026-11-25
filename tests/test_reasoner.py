"""Tests for the stub reasoner (rule-based, deterministic)."""

from __future__ import annotations

from lakehouse_solutions.packet import case_from_dict
from lakehouse_solutions.reasoner import StubReasoner
from lakehouse_solutions.tools import catalog_search
from tests.conftest import clean_case


def _decide(data, **flags) -> str:
    case = case_from_dict(data)
    return StubReasoner().decide(
        case,
        catalog_search(case),
        injection=flags.get("injection", False),
        fabrication=flags.get("fabrication", False),
        missing=flags.get("missing", False),
        conflicts=flags.get("conflicts", False),
        violations=flags.get("violations", False),
        remediation=flags.get("remediation", False),
    )


def test_stub_proposes_when_everything_reconciles() -> None:
    assert _decide(clean_case()) == "PROPOSE"


def test_stub_blocks_on_injection_first() -> None:
    # Injection beats every other signal, including a policy violation.
    assert _decide(clean_case(), injection=True, violations=True) == "BLOCK"


def test_stub_pauses_on_policy_violation() -> None:
    assert _decide(clean_case(), violations=True) == "PAUSE"


def test_stub_holds_on_missing_evidence() -> None:
    assert _decide(clean_case(), missing=True) == "HOLD"


def test_stub_holds_on_fabrication() -> None:
    assert _decide(clean_case(), fabrication=True) == "HOLD"


def test_stub_holds_on_remediation() -> None:
    assert _decide(clean_case(), remediation=True) == "HOLD"


def test_stub_holds_when_no_table_matches() -> None:
    data = clean_case()
    data["tables"] = []
    assert _decide(data) == "HOLD"


def test_stub_is_deterministic_across_repeated_calls() -> None:
    case = case_from_dict(clean_case())
    matches = catalog_search(case)
    reasoner = StubReasoner()
    kwargs = {
        "injection": False,
        "fabrication": False,
        "missing": False,
        "conflicts": False,
        "violations": False,
        "remediation": False,
    }
    first = reasoner.decide(case, matches, **kwargs)
    second = reasoner.decide(case, matches, **kwargs)
    assert first == second == "PROPOSE"


def test_stub_priority_order() -> None:
    # BLOCK > PAUSE > HOLD; missing evidence and fabrication both HOLD.
    assert _decide(clean_case(), missing=True, fabrication=True) == "HOLD"
    assert _decide(clean_case(), violations=True, missing=True) == "PAUSE"
    assert _decide(clean_case(), injection=True, missing=True, violations=True) == "BLOCK"
