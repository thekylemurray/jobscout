from jobscout.models import Job
from jobscout.scoring import dedupe_jobs, score_job
from jobscout.utils import iso_now

def j(uid, company, source, title):
    now=iso_now()
    return Job(uid,company,source,title,"Remote - United States","Remote","Full time","SEO AEO technical SEO content strategy analytics","","",now,now,"")

def test_direct_source_wins_cross_source_duplicate(config):
    a=j("1","Stripe","himalayas","AEO/GEO Marketing Manager")
    b=j("2","Stripe, Inc.","greenhouse","AEO and GEO Marketing Manager")
    for x in (a,b): score_job(x,config)
    out=dedupe_jobs([a,b],config)
    assert len(out)==1
    assert out[0].source=="greenhouse"
    assert "himalayas" in (out[0].also_found_on or [])

def test_company_alias_duplicate(config):
    a=j("1","EndeavorB2B","himalayas","Digital Content Specialist")
    b=j("2","Endeavor Business Media","jobicy","Digital Content Specialist")
    for x in (a,b): score_job(x,config)
    out=dedupe_jobs([a,b],config)
    assert len(out)==1
