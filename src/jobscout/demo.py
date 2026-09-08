from __future__ import annotations

from .models import Job
from .scoring import apply_freshness, score_job
from .utils import iso_now

def demo_jobs(config: dict) -> list[Job]:
    now = iso_now()
    rows = [
        ("Northstar", "Senior Website Manager", "Required qualifications: headless CMS, Contentful, technical SEO, GA4, WCAG, web operations, stakeholder management, B2B SaaS."),
        ("Atlas AI", "AEO and GEO Marketing Manager", "Required qualifications: SEO, AEO, generative engine optimization, Google Analytics, cross-functional engineering and content, B2B SaaS, RAG and vector search."),
        ("Meridian Health", "Content Governance Strategist", "Required qualifications: content governance, taxonomy, information architecture, structured content, Sitecore, accessibility, healthcare."),
        ("Example Labs", "Growth Marketing Manager", "Responsibilities: demand generation, paid media, campaign optimization, SEO, analytics."),
    ]
    out=[]
    for idx,(company,title,desc) in enumerate(rows,1):
        job=Job(str(idx), company, "demo", title, "Remote - United States", "Remote", "Full time", desc, "https://example.com", "https://example.com", now, now, "$100,000-$140,000")
        score_job(job, config)
        apply_freshness(job, config, board_initialized=True, is_new=True)
        if job.eligible:
            out.append(job)
    return out
