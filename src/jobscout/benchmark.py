"""Repeatable, offline ranking check on *synthetic* labeled job descriptions.

These tests deliberately are not claimed as real-world precision estimates.
To test personal real-world precision, label reviewed postings in a private copy
of this JSON schema. Never commit a personal resume, application status or profile.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jobscout.models import Job
from jobscout.scoring import score_job

LABELS = {"good", "review", "exclude"}


def evaluate(cases: list[dict], config: dict) -> dict:
    outcomes = []
    for idx, row in enumerate(cases):
        label = row["label"]
        if label not in LABELS:
            raise ValueError(f"Unknown benchmark label: {label}")
        stamp = datetime.now(timezone.utc).isoformat()
        job = Job(uid=f"benchmark:{idx}", company="Synthetic benchmark",
                  source="greenhouse", title=row["title"],
                  location=row.get("location", "Remote - US"),
                  workplace="Remote", employment_type="Full time",
                  description=row["description"], job_url="", apply_url="",
                  published_at=stamp, first_seen_at=stamp, compensation="")
        result = score_job(job, config)
        ready = bool(result.eligible and result.fit_score >= 75 and
                     not result.qualification_review_required)
        outcomes.append({"title": row["title"], "label": label,
                         "fit": result.fit_score, "eligible": result.eligible,
                         "review": result.qualification_review_required,
                         "confidence": result.assessment_confidence,
                         "ready": ready})
    ranked = sorted((r for r in outcomes if r["ready"]),
                    key=lambda r: r["fit"], reverse=True)
    good = [r for r in outcomes if r["label"] == "good"]
    k = min(5, len(ranked))
    return {
        "cases": len(outcomes),
        "good": len(good),
        "ready": len(ranked),
        "precision_at_5": (sum(r["label"] == "good" for r in ranked[:k]) / k
                           if k else 0.0),
        "good_ready_recall": (sum(r["ready"] for r in good) / len(good)
                              if good else 0.0),
        "excluded_correctly": sum(not r["eligible"] for r in outcomes
                                   if r["label"] == "exclude"),
        "excluded_total": sum(r["label"] == "exclude" for r in outcomes),
        "review_flagged": sum(r["review"] or not r["eligible"] or r["fit"] < 75
                              for r in outcomes if r["label"] == "review"),
        "review_total": sum(r["label"] == "review" for r in outcomes),
        "outcomes": outcomes,
    }


def fixture_config() -> dict:
    return {
        "local_regions": ["raleigh", "durham", "cary", "north carolina"],
        "_candidate_evidence": {
            # Generic synthetic profile: never publish an actual user's résumé.
            "demonstrated": [
                "sitecore", "sanity", "wordpress", "cms publishing",
                "cms migration", "web qa", "seo", "technical seo",
                "aeo/geo", "analytics", "google analytics", "figma",
                "stakeholder coordination", "content governance",
                "structured content", "accessibility", "html/css"
            ],
            "transferable": ["adobe experience manager", "contentful"],
            "not_demonstrated": [],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path,
                        default=Path(__file__).parents[2] / "benchmarks" / "phase2_1_cases.json")
    parser.add_argument("--json", action="store_true", help="Output complete machine-readable results")
    args = parser.parse_args()
    with args.cases.open(encoding="utf-8") as handle:
        cases = json.load(handle)
    result = evaluate(cases, fixture_config())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Synthetic cases: {result['cases']}; review-ready: {result['ready']}")
        print(f"Precision@5: {result['precision_at_5']:.0%}; good-ready recall: {result['good_ready_recall']:.0%}")
        print(f"Correctly excluded: {result['excluded_correctly']}/{result['excluded_total']}")
        print(f"Review cases not auto-ready: {result['review_flagged']}/{result['review_total']}")


if __name__ == "__main__":
    main()
