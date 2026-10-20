"""Identity, publication provenance and persistence for personal CLI scans."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from .models import Job
from .utils import canonical_company, iso_now, parse_dt

FEED_SOURCES = frozenset({"remoteok", "jobicy", "himalayas", "wwr"})
CONFIDENCE = {"unknown": 0, "first_seen": 0, "relative_estimate": 1,
              "feed_timestamp": 2, "employer_timestamp": 3}


def publication_basis(job: Job) -> str:
    if not parse_dt(job.published_at):
        return "first_seen"
    if job.publication_basis:
        return job.publication_basis
    if job.source == "workday":
        return "relative_estimate"
    return "feed_timestamp" if job.source in FEED_SOURCES else "employer_timestamp"


def requisition_key(job: Job) -> str:
    company = canonical_company(job.company)
    for raw in (job.job_url, job.apply_url):
        try:
            uri = urlsplit(raw or "")
        except ValueError:
            continue
        host, path = (uri.hostname or "").lower(), uri.path.rstrip("/").lower()
        q = parse_qs(uri.query)
        if "greenhouse.io" in host:
            m = re.search(r"/jobs/(\d+)", path)
            number = (q.get("gh_jid") or [None])[0] or (m.group(1) if m else "")
            if number:
                return f"{company}:greenhouse:{number}"
        if host.endswith("lever.co"):
            m = re.search(r"/([0-9a-f]{8}-[0-9a-f-]{27,})(?:/apply)?$", path)
            if m:
                return f"{company}:lever:{m.group(1)}"
        if host.endswith(".myworkdayjobs.com") and "/job/" in path:
            rid = path.rsplit("_", 1)[-1]
            if re.fullmatch(r"[a-z0-9-]{3,}", rid):
                return f"{company}:workday:{rid}"
        if "ashbyhq.com" in host:
            m = re.search(r"/([0-9a-f]{8}-[0-9a-f-]{27,})$", path)
            if m:
                return f"{company}:ashby:{m.group(1)}"
    if job.uid:
        return f"{company}:id:{job.uid.strip().lower()}"
    return f"{company}:unknown"
