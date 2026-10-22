"""Synthetic role benchmark — fixed cases, not real-world prediction metrics."""
import json
from pathlib import Path

from jobscout.benchmark import evaluate, fixture_config

FIXTURE = Path(__file__).resolve().parents[1] / "benchmarks" / "phase2_1_cases.json"


def test_curated_benchmark_guards_precision_recall_and_exclusions():
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    results = evaluate(cases, fixture_config())
    assert results["cases"] >= 30
    assert results["good"] >= 10
    assert results["precision_at_5"] >= 0.80, results["outcomes"]
    assert results["good_ready_recall"] >= 0.70, results["outcomes"]
    assert results["excluded_correctly"] >= results["excluded_total"] - 1, results["outcomes"]
    assert results["review_flagged"] >= results["review_total"] - 2, results["outcomes"]


def test_benchmark_refuses_unknown_label():
    try:
        evaluate([{"title": "Web Manager", "label": "possibly",
                   "description": "Required qualifications: Sitecore"}], fixture_config())
    except ValueError as exc:
        assert "Unknown benchmark label" in str(exc)
    else:
        raise AssertionError("Unrecognised benchmark label should be rejected")
