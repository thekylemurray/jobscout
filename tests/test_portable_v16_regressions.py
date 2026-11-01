"""v1.6 regression checks: actual failure classes from Haley's first scans.

Cases use synthetic excerpts, not representations of complete employer postings.
"""
from __future__ import annotations
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jobscout.app import write_outputs
from jobscout.config import default_config, validate_config
from jobscout.models import Job
from jobscout.portable_compensation import location_compensation_review
from jobscout.profiles import blank_profile
from jobscout.scoring import score_job
from jobscout.paths import RuntimePaths
from jobscout.profile_constraints import constraint_result


def config():
    c = default_config()
    p = blank_profile()
    p.update(
        name="Synthetic WA senior IC", title_terms=["program manager"],
        adjacent_title_terms=["sales operations manager", "senior manager gtm operations"],
        core_skills=["operating cadence", "process improvement", "governance",
                     "kpi dashboards", "workflow automation", "stakeholder alignment"],
        remote_only=True, home_state="Washington", allow_contract=False,
        require_full_time=True, exclude_people_management=True,
        max_travel_percent=9.99, capability_evidence={
            "ethics_compliance": "unassessed",
            "channel_distribution": "unassessed",
            "public_sector_procurement": "unassessed",
        },
    )
    c.update(profile=p, salary_floor=150000, salary_target=165000,
             local_regions=[], dashboard_threshold=52, dashboard_age_hours=336,
             boards=[])
    assert not validate_config(c)
    return c


def job(**changes):
    data = dict(uid="test", company="Example", source="manual",
                title="Senior Program Manager", location="Remote - United States",
                workplace="Remote", employment_type="Full time",
                description="Lead cross-functional stakeholder alignment and operating cadence.",
                compensation="", job_url="https://example.com/req",
                apply_url="https://example.com/req", published_at=None,
                first_seen_at="2026-10-31T00:00:00Z")
    data.update(changes)
    return Job(**data)


def sample_compensation():
    return ("The compensation ranges for this role's annual base salary by location are: "
            "San Francisco, California: $122,000 - $153,000 USD. "
            "Seattle, WA: $114,000 - $146,000 USD. "
            "Other U.S. locations: $106,000 - $133,000 USD.")


def test_location_band_excludes_sf_maximum_inapplicable_to_wa():
    reason, notes = location_compensation_review(sample_compensation(),150000,"Washington")
    assert "below required base" in reason
    assert "146000" in reason
    assert notes
    evaluated = score_job(job(title="Sales Operations Manager",
                              description=sample_compensation()),config())
    assert not evaluated.eligible
    assert "Washington-compatible" in evaluated.veto_reason


def test_seattle_band_at_floor_keeps_role_for_review():
    s=("Annual base salary compensation ranges: "
       "San Francisco: $169,000 - $211,000 USD. "
       "Seattle: $162,000 - $202,000 USD. "
       "Other U.S. locations: $147,000 - $184,000 USD.")
    reason, notes=location_compensation_review(s,150000,"Washington")
    assert reason==""
    assert notes


def test_unknown_geography_is_not_automatically_rejected():
    s="Annual base salary $100,000 - $149,000 in selected high-cost locations."
    reason, _ = location_compensation_review(s,150000,"Washington")
    assert not reason  # Existing unambiguous annual_salary parser may veto independently.


def test_ote_below_required_base_is_rejected_not_labeled_base():
    s="U.S. on-target earnings (OTE) range: $125,000 - $148,000 USD annually."
    reason, _ = location_compensation_review(s,150000,"Washington")
    assert "on-target earnings" in reason
    evaluated=score_job(job(description=s),config())
    assert not evaluated.eligible and "on-target earnings" in evaluated.veto_reason
    assert "annual base" not in evaluated.compensation.lower()


def test_ote_above_floor_is_not_treated_as_confirmed_base():
    s="U.S. on-target earnings (OTE) range: $165,000 - $225,000 USD annually."
    reason, notes=location_compensation_review(s,150000,"Washington")
    assert not reason and any("base salary" in n for n in notes)


@pytest.mark.parametrize("description", [
    "Qualifications: 5+ years of direct people management experience required.",
    "Must have 6 years of personnel management experience.",
    "Responsibilities: Managing a team of systems administrators.",
    "Direct reports: 4; accountable for performance reviews.",
    "Responsible for hiring and managing staff.",
    "Coach and develop a team of specialists.",
])
def test_real_supervision_cannot_enter_adjacent_reviews(description):
    evaluated=score_job(job(title="Senior Manager GTM Operations",
                            description=description),config())
    assert not evaluated.eligible
    assert "people-management" in evaluated.veto_reason


@pytest.mark.parametrize("description",[
    "Lead cross-functional teams without direct reports.",
    "Influence program teams without formal authority.",
    "No people management responsibilities. Coordinate marketing workstreams.",
    "In the future, as the team grows, may manage a program manager.",
])
def test_ic_leadership_does_not_get_false_veto(description):
    evaluated=score_job(job(description=description),config())
    assert evaluated.eligible


def test_future_management_flagged_not_vetoed():
    j=score_job(job(description="In the future we may manage new team members."),config())
    assert j.eligible
    assert any("future people-management scope" in n for n in j.risks)


def test_necessary_ethics_compliance_domain_not_drowned_out():
    c=config()
    text=("Required qualifications: Foundational knowledge of ethics and compliance, "
          "including anti-corruption, trade compliance and conflicts of interest. "
          "Responsibilities: drive operating cadence, process improvement, governance, "
          "dashboards, workflow automation and stakeholder alignment.")
    evaluated=score_job(job(description=text),c)
    assert evaluated.eligible
    assert evaluated.fit_score <= 74
    assert any("ethics_compliance" in n for n in evaluated.requirement_notes)
    assert any("fit cap 74" in n for n in evaluated.score_breakdown)


def test_required_public_procurement_and_channel_experience_explicit():
    s=("Required qualifications: government procurement and distributor operations "
       "expertise required. Responsibilities: build operating cadences.")
    evaluated=score_job(job(description=s),config())
    assert evaluated.eligible
    assert any("public_sector_procurement" in n for n in evaluated.requirement_notes)
    assert any("channel_distribution" in n for n in evaluated.requirement_notes)


def test_preferred_domain_only_not_score_capped():
    text=("Responsibilities: Create operating cadence and stakeholder alignment. "
          "Preferred qualifications: Familiarity with ethics and compliance.")
    evaluated=score_job(job(description=text),config())
    assert evaluated.eligible and not evaluated.requirement_notes


def test_old_adjacent_visible_in_dashboard_and_dedicated_csv(tmp_path):
    c=config()
    now=datetime.now(timezone.utc)
    j=score_job(job(title="Sales Operations Manager"),c)
    assert j.eligible and j.review_only
    j.priority_score=49
    j.age_hours=45*24
    j.first_seen_at=(now-timedelta(days=45)).isoformat()
    j.availability="Unverified"
    j.published_at=j.first_seen_at
    paths=RuntimePaths.from_home(tmp_path)
    paths.ensure()
    write_outputs([j],[],c,{},paths)
    dashboard=paths.dashboard.read_text(encoding="utf-8")
    assert "Sales Operations Manager" in dashboard
    assert "Adjacent" in dashboard
    adjacent_csv=paths.output_dir/"adjacent_review.csv"
    with adjacent_csv.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==1 and rows[0]["review_only"]=="True"


def test_primary_exclusions_still_apply_to_adjacent():
    c=config()
    j=score_job(job(title="Sales Operations Manager",workplace="Hybrid"),c)
    assert not j.eligible
    j=score_job(job(title="Sales Operations Manager",compensation="USD 100000-125000 annual base"),c)
    assert not j.eligible
