"""Cases harvested from Haley's first live scan; synthetic copies omit candidate PII."""
from jobscout.config import default_config
from jobscout.models import Job
from jobscout.profiles import blank_profile, salary_from_description
from jobscout.scoring import score_job


def make_job(**update):
    args=dict(uid="check", company="Example", source="manual",
        title="Strategic Initiatives Manager", location="United States - Remote",
        workplace="Remote", employment_type="Full Time",
        description="", job_url="https://example.com", apply_url="https://example.com",
        published_at=None, first_seen_at="2026-10-31T00:00:00Z", compensation="")
    args.update(update)
    return Job(**args)


def config():
    c=default_config()
    p=blank_profile()
    p.update(name="Sample senior remote IC", title_terms=["strategic initiatives manager"],
        core_skills=["cross-functional leadership"], home_state="Washington",
        remote_only=True, require_full_time=True)
    c.update(profile=p, local_regions=[], salary_floor=150000, salary_target=165000)
    return c


def test_below_floor_motive_style_automatically_excluded():
    text = """Pay Transparency. The compensation range for this position will depend on
    where you reside. For this role, the compensation range is:
    United States $106,000 - $146,000 USD."""
    assert salary_from_description(text) == "USD 106000-146000 annual base"
    j=score_job(make_job(description=text), config())
    assert not j.eligible and "below minimum" in j.veto_reason


def test_multiple_geographic_bands_do_not_pick_inapplicable_salary():
    text="""The compensation ranges are:
    San Francisco, California $169,000 - $211,000 USD
    U.S. metropolitan areas: New York City and Seattle, WA $162,000 - $202,000 USD
    Other locations in the United States $147,000 - $184,000 USD"""
    pay = salary_from_description(text)
    assert pay.startswith("USD 147000-211000 annual base")
    j=score_job(make_job(description=text), config())
    assert j.eligible
    assert any("geographic pay bands" in r for r in j.risks)
    assert any("overlaps minimum" in r for r in j.risks)


def test_gitlab_base_salary_range_keeps_overlapping_but_not_guaranteed():
    text="""The base salary range for this role's listed level is currently for residents of
    the United States only. This range is intended to reflect the role's base salary rate
    in locations throughout the US. United States Salary Range $139,200 - $235,200 USD."""
    assert salary_from_description(text) == "USD 139200-235200 annual base"
    j=score_job(make_job(description=text), config())
    assert j.eligible
    assert any("overlaps minimum" in r for r in j.risks)


def test_non_usd_and_bonus_unverified():
    assert salary_from_description("The annual base salary is CAD 120000-180000.") == ""
    assert salary_from_description("Annual bonus range $50,000-$70,000 USD.") == ""
    assert salary_from_description("Hourly pay range $40-$60 USD per hour.") == ""


def test_existing_annual_base_regression():
    assert salary_from_description("Annual base salary USD 175000-215000.") == "USD 175000-215000 annual base"
