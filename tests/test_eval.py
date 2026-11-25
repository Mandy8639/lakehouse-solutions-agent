"""Tests for the frozen eval harness."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from lakehouse_solutions.agent import SolutionsAgent

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "eval"


def _load_golden() -> list[dict]:
    return json.loads((EVAL_DIR / "golden.json").read_text(encoding="utf-8"))


def test_golden_set_has_48_cases() -> None:
    cases = _load_golden()
    assert len(cases) == 48
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    assert counts == {
        "clean": 12,
        "misrouted": 8,
        "remediation": 6,
        "insufficient": 6,
        "fabrication": 6,
        "injection": 6,
        "pause": 4,
    }


def test_golden_hash_matches() -> None:
    expected = (EVAL_DIR / "golden.sha256").read_text(encoding="utf-8").strip()
    actual = hashlib.sha256((EVAL_DIR / "golden.json").read_bytes()).hexdigest()
    assert actual == expected


def test_golden_cases_carry_analyst_calls() -> None:
    expected_calls = {
        "clean": "PROPOSE",
        "misrouted": "HOLD",
        "remediation": "HOLD",
        "insufficient": "HOLD",
        "fabrication": "HOLD",
        "injection": "BLOCK",
        "pause": "PAUSE",
    }
    for case in _load_golden():
        assert case["analyst_call"] == expected_calls[case["category"]]
        assert case["id"].startswith("LH-")


def test_eval_reproduces_the_committed_report() -> None:
    sys.path.insert(0, str(EVAL_DIR))
    from run_eval import evaluate, load_golden

    report = evaluate(load_golden())
    committed = json.loads((EVAL_DIR / "report.json").read_text(encoding="utf-8"))
    assert report == committed


def test_eval_report_numbers() -> None:
    report = json.loads((EVAL_DIR / "report.json").read_text(encoding="utf-8"))
    assert report["agreement"] == "48/48"
    assert report["agreement_pct"] == 100.0
    assert report["false_deploys"] == 0
    assert report["false_holds"] == 0
    assert report["abstention"] == "6/6"
    assert report["fabrication_blocked"] == "6/6"
    assert report["injection_blocked"] == "6/6"
    assert report["pause"] == "4/4"
    assert report["gates"] == "48/48"
    assert report["spend_usd"] == 0.0
    assert report["mode"] == "stub"
    assert report["by_category"]["clean"] == {"total": 12, "agree": 12}
    assert report["by_category"]["pause"] == {"total": 4, "agree": 4}


def test_eval_refuses_a_tampered_golden_set(tmp_path) -> None:
    copied = tmp_path / "eval"
    shutil.copytree(EVAL_DIR, copied)
    golden_path = copied / "golden.json"
    cases = json.loads(golden_path.read_text(encoding="utf-8"))
    cases[0]["analyst_call"] = "BLOCK"
    golden_path.write_text(json.dumps(cases, indent=2, sort_keys=True), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run(
        [sys.executable, "run_eval.py"],
        cwd=copied,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "hash mismatch" in proc.stderr + proc.stdout


def test_denied_gates_publish_nothing_on_any_case() -> None:
    agent = SolutionsAgent(mode="stub")
    for case in _load_golden():
        denied = agent.run(case, approve_solution=False, approve_deploy=False)
        assert denied.published is False
        assert denied.applied is False
        assert denied.sent is False
