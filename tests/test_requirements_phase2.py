"""Regression cases from reviewed CLI scans and opt-in evidence matching."""
import pytest

from jobscout.models import Job
from jobscout.requirements import assess_requirements, role_scope, validate_candidate_evidence
from jobscout.scoring import score_job
from jobscout.utils import iso_now


def job(title, description, *, company="Example", **kwargs):
    ts = iso_now()
    base = dict(uid="synthetic", company=company, source="greenhouse", title=title,
                location="Remote - US", workplace="Remote", employment_type="Full-time",
                description=description, job_url="https://example.org/job/synthetic",
                apply_url="https://example.org/job/synthetic", published_at=ts,
                first_seen_at=ts, compensation="")
    return Job(**(base | kwargs))


SUITABLE = (
    "Required qualifications: Technical SEO, Sitecore content management system, "
    "CMS migration, web analytics, search console, content governance, accessibility. "
    "Responsibilities: Coordinate marketing and engineering, manage website publishing, "
    "perform website QA and UAT."
)


@pytest.mark.parametrize("title", [
    "Senior Full Stack Engineer, Website Development",
    "Senior Software Engineer, Web Platform",
    "Front-end Developer — Web Experience",
    "Back End Engineer, Content Platform",
])
def test_software_development_occupations_are_not_rescued_by_web_terms(config, title):
    candidate = score_job(job(title, SUITABLE), config)
    assert not candidate.eligible
    assert candidate.fit_score == 0


def test_unpaid_internship_excluded_from_senior_career_lane(config):
    candidate = score_job(job("Web Content Writer Internship (UNPAID)", SUITABLE), config)
    assert not candidate.eligible


@pytest.mark.parametrize("title,maximum", [
    ("Head of AEO & SEO", 68),
    ("Sr. Director, Marketing Web Product, UX, and Digital Experience", 62),
    ("Director, Web Operations", 72),
    ("Senior SEO Manager & Account Manager (with AIO Expertise)", 72),
    ("Creative Design & Website Associate", 68),
    ("Digital Experience Developer", 62),
])
def test_role_scope_caps_overly_high_keyword_scores(config, title, maximum):
    candidate = score_job(job(title, SUITABLE), config)
    assert candidate.eligible
    assert candidate.fit_score <= maximum
    assert candidate.scope_flags
    assert any("cap " in x for x in candidate.score_breakdown)


def test_true_web_producer_stays_a_high_match(config):
    candidate = score_job(job("Senior Web Producer", SUITABLE), config)
    assert candidate.eligible
    assert candidate.fit_score >= 80
    assert not candidate.scope_flags


def test_true_technical_seo_specialist_stays_a_high_match(config):
    candidate = score_job(job("Senior Technical SEO Specialist", SUITABLE), config)
    assert candidate.eligible
    assert candidate.fit_score >= 85
    assert not candidate.scope_flags


def test_explicit_people_management_requirement_lowers_priority_without_proof(config):
    desc = SUITABLE + " Required qualifications: manage a team of 10 and oversee direct reports."
    candidate = score_job(job("Manager, Web Operations", desc), config)
    assert candidate.eligible
    assert candidate.fit_score <= 69
    assert any("personnel management" in flag for flag in candidate.scope_flags)


def test_known_not_demonstrated_requirement_is_penalized_not_assumed(config):
    desc = ("Required qualifications: Sitecore, Adobe Experience Manager and Salesforce Marketing Cloud. "
            "Preferred qualifications: HubSpot experience. Responsibilities: Website operations and CMS migration.")
    data = {"demonstrated": ["sitecore"],
            "transferable": ["adobe experience manager"],
            "not_demonstrated": ["salesforce marketing cloud", "hubspot"]}
    config["_candidate_evidence"] = data
    result = score_job(job("Website Manager", desc), config)
    assert result.eligible
    findings = {(f["requirement"], f["importance"]): f["assessment"] for f in result.requirements}
    assert findings["sitecore", "Required"] == "Demonstrated"
    assert findings["adobe experience manager", "Required"] == "Transferable"
    assert findings["salesforce marketing cloud", "Required"] == "Not demonstrated"
    assert findings["hubspot", "Preferred"] == "Not demonstrated"
    assert result.requirement_gaps == ["salesforce marketing cloud"]
    assert "not demonstrated" in result.requirement_coverage


def test_unknown_candidate_skills_are_unassessed_not_imagined_as_missing():
    desc = "Required qualifications: Sitecore, Drupal and AEM. Responsibilities: Build website content."
    findings, coverage, gaps, delta = assess_requirements(desc, None)
    assert gaps == []
    assert delta == 0
    assert findings
    assert all(f["assessment"].startswith("Not assessed") for f in findings)
    assert "not configured" in coverage


def test_preferred_missing_skills_have_no_penalty():
    desc = "Required qualifications: Sitecore. Preferred qualifications: Marketo and HubSpot."
    findings, coverage, gaps, delta = assess_requirements(
        desc, {"demonstrated": [], "transferable": [],
               "not_demonstrated": ["hubspot"]})
    assert gaps == []
    assert delta == 0
    assert "HubSpot" not in coverage


def test_unrecognised_profile_term_rejected():
    problems = validate_candidate_evidence({"demonstrated": ["unknown magical CMS"]})
    assert any("unknown" in x for x in problems)


def test_duplicate_assertions_are_rejected():
    problems = validate_candidate_evidence({
        "demonstrated": ["sitecore"], "transferable": ["sitecore"]})
    assert any("both" in x for x in problems)


def test_geo_not_counted_in_geospatial_context():
    descriptions = ("Required qualifications: GEO geospatial mapping GIS surveying data. "
                    "Responsibilities: Map geographic coordinates.")
    findings, _, _, _ = assess_requirements(descriptions)
    assert not any(x["requirement"] == "aeo/geo" for x in findings)


def test_requirement_groups_use_section_priority():
    text = ("Required qualifications: Sitecore. "
            "Responsibilities: CMS migration, accessibility checks. "
            "Preferred qualifications: Drupal and Adobe Experience Manager.")
    findings, _, _, _ = assess_requirements(text)
    indexed = {x["requirement"]: x["importance"] for x in findings}
    assert indexed["sitecore"] == "Required"
    assert indexed["cms migration"] == "Responsibility"
    assert indexed["drupal"] == "Preferred"
