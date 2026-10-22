from jobscout.models import Job
from jobscout.scoring import score_job
from jobscout.utils import iso_now

def make_job(title, description, location="Remote - United States", source="test"):
    now=iso_now()
    return Job("1","Example",source,title,location,"Remote","Full time",description,"","",now,now,"")

def test_explicit_seo_specialist_is_high_fit(config):
    job=make_job("Search Engine Optimization Specialist", "Required qualifications: technical SEO GEO Adobe Experience Manager content strategy Search Console SEMrush cross-functional stakeholder B2B healthcare")
    score_job(job, config)
    assert job.eligible
    assert job.role_lane == "SEO / AEO / GEO"
    assert job.fit_score >= 85

def test_accounting_role_is_vetoed(config):
    job=make_job("Senior Manager, Corporate Accounting", "governance analytics stakeholders automation")
    score_job(job, config)
    assert not job.eligible

def test_geospatial_geo_does_not_create_search_match(config):
    job=make_job("GEO Data Program Manager", "GIS geospatial mapping geographic territory planning stakeholders analytics")
    score_job(job, config)
    assert not job.eligible

def test_chief_revenue_cro_does_not_create_cro_match(config):
    job=make_job("CRO Strategy Manager", "Chief Revenue Officer sales leadership revenue forecasting stakeholders")
    score_job(job, config)
    assert not job.eligible

def test_digital_web_services_precedence(config):
    job=make_job("Manager, Digital Web Services", "Responsibilities: website operations SEO content development stakeholder. Preferred: Drupal content management system user experience artificial intelligence.")
    score_job(job, config)
    assert job.eligible
    assert job.role_lane == "Web / CMS / Digital Experience"


def test_remote_in_the_us_is_allowed_for_explicit_web_role(config):
    role = make_job("AEO and GEO Marketing Manager",
                    "Required: technical SEO, generative engine optimization, CMS, web analytics and internal linking",
                    location="Remote in the US", source="greenhouse")
    score_job(role, config)
    assert role.eligible
    assert role.veto_reason == ""


def test_remote_in_other_country_is_not_automatically_us_eligible(config):
    role = make_job("Web Manager",
                    "Required: CMS content strategy, analytics, technical SEO, publishing workflows",
                    location="Remote in the UK", source="greenhouse")
    score_job(role, config)
    assert not role.eligible
