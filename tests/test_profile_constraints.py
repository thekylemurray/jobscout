"""Regression checks for opt-in portable job constraints and career lanes."""
from types import SimpleNamespace

import pytest

from jobscout.config import default_config, validate_config
from jobscout.models import Job
from jobscout.profile_constraints import (
    constraint_result, matching_lane, state_excluded, validate_extended_profile,
)
from jobscout.profiles import blank_profile
from jobscout.scoring import score_job


def posting(**kwargs):
    defaults = dict(
        title="Senior Program Manager", description="Lead strategic initiatives and operating cadence.",
        location="Remote - United States", workplace="Remote", employment_type="Full time",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def checks(**overrides):
    settings = dict(remote_only=True, require_full_time=True, home_state="Washington",
                    exclude_people_management=True, max_travel_percent=9.99,
                    exclude_agencies=True, exclude_required_platform_certifications=True)
    settings.update(overrides)
    return settings


@pytest.mark.parametrize("location,expected", [
    ("Remote - US except CA, CO, WA and NY", True),
    ("Remote - not hiring in Washington", True),
    ("Remote - Washington State", False),
    ("Remote - United States", False),
])
def test_wa_exclusions(location, expected):
    assert state_excluded(location, "Washington") is expected


def test_individual_contributor_manager_remains_reviewable():
    violation, notes = constraint_result(posting(
        title="Marketing Operations Manager",
        description="Manage cross-functional programs. No direct reports. "
                    "Operate dashboards. Travel up to 5%."), checks())
    assert not violation
    assert any("direct reports" in x for x in notes)


@pytest.mark.parametrize("description", [
    "Manage a team of 6 professionals.",
    "This position has 4 direct reports.",
    "Supervisory experience required for this role.",
    "Responsible for hiring and managing staff.",
])
def test_people_management_excluded(description):
    violation, _ = constraint_result(posting(description=description), checks())
    assert "people-management" in violation


@pytest.mark.parametrize("description", [
    "Travel required: 10%",
    "Up to 15% travel is required.",
    "Travel up to 25% of the time.",
])
def test_travel_at_or_above_ten_excluded(description):
    violation, _ = constraint_result(posting(description=description), checks())
    assert "travel" in violation


def test_mandatory_office_attendance_excluded():
    violation, _ = constraint_result(posting(description="Must work in the office two days each month."), checks())
    assert "office" in violation


def test_explicit_required_technical_cert_excluded_but_pmp_preferred_is_not():
    violation, _ = constraint_result(posting(description="Salesforce Architect certification required."), checks())
    assert "certification" in violation
    violation, _ = constraint_result(posting(description="PMP certification preferred."), checks())
    assert not violation


def test_consulting_firm_excluded_but_partnering_with_agencies_not():
    violation, _ = constraint_result(posting(description="We are a marketing agency delivering brand strategy."), checks())
    assert "agency" in violation
    violation, _ = constraint_result(posting(description="Partner with outside creative agencies."), checks())
    assert not violation


def test_remote_washington_allowed_and_hybrid_not():
    cfg = default_config()
    p = blank_profile()
    p.update(name="Synthetic", title_terms=["program manager"], core_skills=["operating cadence"], home_state="Washington",
             career_lanes=[dict(name="Business/Program Operations", title_terms=["program manager"],
                                core_skills=["stakeholder alignment"])])
    cfg.update(profile=p, local_regions=[], salary_floor=150000, salary_target=165000, boards=[])
    assert not validate_config(cfg)
    job_data = dict(uid="one", company="Synthetic Co", source="manual", title="Senior Program Manager",
                    location="Remote - Washington", workplace="Remote", employment_type="Full time",
                    description="Operating cadence and stakeholder alignment.", job_url="https://example.org",
                    apply_url="https://example.org", published_at=None, first_seen_at="", compensation="")
    accepted = score_job(Job(**job_data), cfg)
    assert accepted.eligible
    assert accepted.role_lane == "Business/Program Operations"
    assert accepted.fit_score == 62
    blocked = score_job(Job(**(job_data | dict(location="Seattle WA", workplace="Hybrid"))), cfg)
    assert not blocked.eligible


def test_lanes_choose_longest_specific_phrase():
    lanes = [
        dict(name="Program", title_terms=["program manager"], core_skills=[]),
        dict(name="Marketing", title_terms=["marketing operations manager"], core_skills=[]),
    ]
    assert matching_lane("Senior Marketing Operations Manager", lanes)["name"] == "Marketing"


def test_invalid_opt_in_settings_reported():
    assert validate_extended_profile(dict(max_travel_percent="ten", remote_only="yes",
                                          career_lanes=[dict(name="Ops", title_terms="program manager",
                                                             core_skills=[])]))
