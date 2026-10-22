"""Phase 2.1: confidence is evidence completeness, never hiring probability."""
from jobscout.models import Job
from jobscout.requirements import assess_requirements, review_assessment
from jobscout.scoring import score_job, apply_freshness
from jobscout.utils import extract_sections, iso_now


def role(title, description):
    now = iso_now()
    return Job(uid="example:123", company="Example", source="greenhouse",
               title=title, location="Remote - US", workplace="Remote",
               employment_type="Full time", description=description,
               job_url="https://example.org/roles/123", apply_url="https://example.org/roles/123",
               published_at=now, first_seen_at=now, compensation="")


def test_candidate_background_is_not_mandatory():
    text = ("Responsibilities: Own web content launches, releases, and SEO. "
            "Who You Are: Experience with Sitecore, AEM, and Figma. "
            "Preferred Qualifications: HubSpot expertise.")
    chunks = extract_sections(text)
    assert "Sitecore" in chunks["candidate"]
    assert "Sitecore" not in chunks["required"]
    findings, _, gaps, adjustment = assess_requirements(text, {
        "demonstrated": [], "transferable": [],
        "not_demonstrated": ["sitecore", "hubspot"]})
    m = {item["requirement"]: item["importance"] for item in findings}
    assert m["sitecore"] == "Candidate criteria"
    assert m["hubspot"] == "Preferred"
    assert gaps == []
    assert adjustment == 0


def test_required_preferred_and_candidate_headings_do_not_overlap():
    text = ("Minimum Requirements: Sitecore and CMS migration. "
            "Who You Are: Familiar with AEM. "
            "Nice to Have: HubSpot and Webflow.")
    chunks = extract_sections(text)
    assert "Sitecore" in chunks["required"]
    assert "AEM" in chunks["candidate"]
    assert "HubSpot" in chunks["preferred"]
    findings, _, _, _ = assess_requirements(text)
    assert {x["requirement"]: x["importance"] for x in findings}["sitecore"] == "Required"
    assert {x["requirement"]: x["importance"] for x in findings}["hubspot"] == "Preferred"


def test_strong_fit_without_explicit_required_terms_triggers_review(config):
    s = ("What You'll Do: Lead web experience and SEO strategy, manage"
         " content governance and CMS migrations, drive analytics and website operations. "
         "Who You Are: Figma, WordPress, Sitecore, and technical SEO experience.")
    j = score_job(role("Sr. Digital Experience Manager", s), config)
    assert j.eligible and j.fit_score >= 80
    assert j.assessment_confidence in {"Low", "Medium"}
    assert j.qualification_review_required
    assert any("no explicit required" in x.lower()
               for x in j.qualification_review_reasons)


def test_multi_unknown_mandatory_categories_trigger_review(config):
    config["_candidate_evidence"] = {"demonstrated": ["seo"], "transferable": [],
                                     "not_demonstrated": []}
    desc = ("Required Qualifications: technical SEO, HubSpot, marketing automation,"
            " Google Analytics. Responsibilities: Site content strategy, analytics, web operations.")
    job = score_job(role("SEO Manager", desc), config)
    assert job.eligible
    assert job.qualification_review_required
    assert any("required skill categories still unassessed" in x
               for x in job.qualification_review_reasons)


def test_explicit_gap_triggers_review_without_automatic_disqualification(config):
    config["_candidate_evidence"] = {"demonstrated": ["sitecore", "seo"],
                                     "transferable": [],
                                     "not_demonstrated": ["salesforce marketing cloud"]}
    desc = ("Required qualifications: Sitecore, SEO, Salesforce Marketing Cloud. "
            "Responsibilities: Enterprise website management and CMS migration.")
    j = score_job(role("Website Manager", desc), config)
    assert j.eligible
    assert j.qualification_review_required
    assert any("not demonstrated" in x for x in j.qualification_review_reasons)


def test_high_assessment_confidence_can_still_have_manual_review_gap():
    findings = [{"requirement": "sitecore", "importance": "Required",
                 "assessment": "Demonstrated"},
                {"requirement": "seo", "importance": "Required",
                 "assessment": "Demonstrated"},
                {"requirement": "hubspot", "importance": "Required",
                 "assessment": "Not demonstrated"}]
    confidence, reasons = review_assessment(findings, 96, [])
    assert confidence == "High"
    assert any("not demonstrated" in text for text in reasons)


def test_fully_demonstrated_required_terms_allow_review_free_match(config):
    config["_candidate_evidence"] = {"demonstrated": ["sitecore", "seo",
                                                      "content governance", "web qa"],
                                     "transferable": [], "not_demonstrated": []}
    desc = ("Required qualifications: Sitecore, SEO, content governance, website QA. "
            "Responsibilities: Enterprise CMS content publishing and release workflows.")
    j = score_job(role("Senior Web Producer", desc), config)
    assert j.fit_score >= 75
    assert j.assessment_confidence == "High"
    assert not j.qualification_review_required
    assert j.qualification_review_reasons == []


def test_unassessed_not_synonymous_with_missing():
    fields = [{"requirement": "hubspot", "importance": "Required",
               "assessment": "Unassessed"}]
    quality, reasons = review_assessment(fields, 90, [])
    assert quality == "Medium"
    assert reasons == []  # Single unassessed category is context, not assumed a gap.


def test_people_management_requires_review_even_if_section_is_candidate():
    fields = [{"requirement": "people management", "importance": "Candidate criteria",
               "assessment": "Unassessed"}]
    quality, reasons = review_assessment(fields, 85, [])
    assert any("Direct-report" in x for x in reasons)
