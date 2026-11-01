"""Calibration regressions: distinguish operational alignment from unknown specialties."""
from datetime import datetime, timezone

from jobscout.config import default_config, validate_config
from jobscout.models import Job
from jobscout.profiles import blank_profile
from jobscout.scoring import apply_freshness, score_job


def make_config():
    c = default_config()
    p = blank_profile()
    p.update(
        name="Example senior IC", title_terms=["program manager"],
        adjacent_title_terms=["sales operations manager"],
        core_skills=["operating cadence", "process improvement", "governance",
                     "kpi dashboards", "workflow automation", "stakeholder alignment"],
        career_lanes=[], remote_only=True, home_state="Washington",
        require_full_time=True, exclude_people_management=True,
        capability_evidence={"ethics_compliance": "unassessed",
                             "data_annotation": "not_demonstrated",
                             "field_sales_revops": "transferable"},
    )
    c.update(profile=p, salary_floor=150000, salary_target=165000,
             local_regions=[], boards=[])
    assert not validate_config(c)
    return c


def make_job(**kwargs):
    fields = dict(uid="calibrated", company="Example Employer", source="greenhouse",
                  title="Senior Program Manager", location="Remote - United States",
                  workplace="Remote", employment_type="Full Time",
                  description="", job_url="https://example.com/job",
                  apply_url="https://example.com/job", published_at=None,
                  first_seen_at="2026-10-31T00:00:00+00:00",
                  compensation="USD 165000-190000 annual base")
    fields.update(kwargs)
    return Job(**fields)


def operations_text():
    return ("Build operating cadences, improve processes, develop governance, "
            "create KPI dashboards, automate workflows, and align stakeholders.")


def test_operational_alignment_retained_when_required_specialty_unassessed():
    cfg=make_config()
    baseline=score_job(make_job(description=operations_text()),cfg)
    specialized=score_job(make_job(description=(
        "Required qualifications: Familiarity with ethics and compliance, "
        "anti-corruption and trade compliance. Responsibilities: " + operations_text())),cfg)
    assert specialized.eligible
    assert specialized.operational_alignment_score == baseline.operational_alignment_score
    assert specialized.operational_alignment_score >= 80
    assert specialized.qualification_adjustment == -9
    assert specialized.fit_score == baseline.fit_score - 9
    assert specialized.fit_score > 74  # no artificial ceiling
    assert specialized.requirement_notes
    assert any("unassessed" in x for x in specialized.requirement_notes)


def test_priority_starts_from_adjusted_fit_not_another_requirement_penalty():
    cfg=make_config()
    raw=score_job(make_job(description=operations_text()),cfg)
    flagged=score_job(make_job(description=(
        "Required qualifications: Ethics and compliance experience. Responsibilities: " +
        operations_text())),cfg)
    raw=apply_freshness(raw,cfg,board_initialized=False,is_new=False)
    flagged=apply_freshness(flagged,cfg,board_initialized=False,is_new=False)
    assert raw.priority_score-flagged.priority_score == 9
    assert "qualifications -9" in flagged.priority_reasons[0]
    assert any("adjusted fit" in x for x in flagged.score_breakdown)


def test_preferred_skill_not_penalized():
    cfg=make_config()
    j=score_job(make_job(description=(
        "Responsibilities: " + operations_text() +
        " Preferred qualifications: ethics and compliance background.")),cfg)
    assert j.qualification_adjustment == 0
    assert j.fit_score == j.operational_alignment_score


def test_adjacent_separate_review_not_capped_or_alerted():
    cfg=make_config()
    j=score_job(make_job(title="Sales Operations Manager",
                         description=operations_text()),cfg)
    assert j.eligible and j.review_only
    assert j.fit_score == j.operational_alignment_score - 8
    assert j.match_path == "adjacent review"


def test_confirmed_people_management_still_excluded():
    cfg=make_config()
    j=score_job(make_job(description=(
        "Required qualifications: 5 years of direct people management experience. "
        + operations_text())),cfg)
    assert not j.eligible
    assert "people-management" in j.veto_reason


def test_previous_scores_reset_on_rescoring_same_object():
    cfg=make_config()
    j=make_job(description="Required qualifications: ethics and compliance.")
    score_job(j,cfg)
    assert j.qualification_adjustment == -9
    j.description=operations_text()
    score_job(j,cfg)
    assert j.qualification_adjustment == 0
    assert j.operational_alignment_score == j.fit_score
