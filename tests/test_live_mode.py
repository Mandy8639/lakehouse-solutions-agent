"""Tests for live mode: only refusal paths are exercised.

No test here makes a real API call. Live mode is Haiku only, behind a
$1.00/day cap, and refuses without an API key, for an unknown model, when
the cap is reached, or when the anthropic package is absent.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta

import pytest

from lakehouse_solutions.packet import case_from_dict
from lakehouse_solutions.reasoner import (
    DAILY_CAP_USD,
    PRICED_MODELS,
    LiveReasoner,
    SpendTracker,
)
from tests.conftest import clean_case


def test_only_haiku_is_priced() -> None:
    assert list(PRICED_MODELS) == ["claude-haiku-4-5"]
    assert PRICED_MODELS["claude-haiku-4-5"] == {
        "input_usd_per_mtok": 1.00,
        "output_usd_per_mtok": 5.00,
    }
    assert DAILY_CAP_USD == 1.00


def test_live_refuses_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reasoner = LiveReasoner()
    with pytest.raises(RuntimeError, match="no ANTHROPIC_API_KEY"):
        reasoner.decide(case_from_dict(clean_case()), [])


def test_live_refuses_unknown_model(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    reasoner = LiveReasoner(model="claude-opus-4-5")
    with pytest.raises(RuntimeError, match="not in the priced-model table"):
        reasoner.decide(case_from_dict(clean_case()), [])


def test_live_refuses_when_the_daily_cap_is_reached(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    spend_path = tmp_path / "spend.json"
    spend_path.write_text(
        json.dumps({"date": date.today().isoformat(), "spent_usd": 1.00}),
        encoding="utf-8",
    )
    reasoner = LiveReasoner(spend_path=str(spend_path))
    with pytest.raises(RuntimeError, match="daily cap"):
        reasoner.decide(case_from_dict(clean_case()), [])


def test_live_refuses_without_the_anthropic_package(monkeypatch, tmp_path) -> None:
    if importlib.util.find_spec("anthropic") is not None:
        pytest.skip("anthropic is installed; the no-package refusal cannot be shown here")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    reasoner = LiveReasoner(spend_path=str(tmp_path / "spend.json"))
    with pytest.raises(RuntimeError, match="anthropic package not installed"):
        reasoner.decide(case_from_dict(clean_case()), [])


def test_spend_tracker_records_and_reads_today(tmp_path) -> None:
    tracker = SpendTracker(str(tmp_path / "spend.json"))
    assert tracker.today_spent() == 0.0
    assert tracker.record(0.25) == 0.25
    assert tracker.today_spent() == 0.25
    assert tracker.record(0.10) == 0.35


def test_spend_tracker_ignores_yesterday(tmp_path) -> None:
    spend_path = tmp_path / "spend.json"
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    spend_path.write_text(json.dumps({"date": yesterday, "spent_usd": 0.99}), encoding="utf-8")
    assert SpendTracker(str(spend_path)).today_spent() == 0.0


def test_live_parse_accepts_the_four_decisions() -> None:
    assert LiveReasoner._parse("PROPOSE") == "PROPOSE"
    assert LiveReasoner._parse("i think HOLD") == "HOLD"
    assert LiveReasoner._parse("pause here") == "PAUSE"
    assert LiveReasoner._parse("BLOCK") == "BLOCK"


def test_live_parse_rejects_anything_else() -> None:
    with pytest.raises(RuntimeError, match="unparseable"):
        LiveReasoner._parse("maybe later")
