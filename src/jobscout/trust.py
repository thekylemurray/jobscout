"""Identity, publication provenance and persistence for personal CLI scans."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from .models import Job
from .utils import canonical_company, iso_now, parse_dt

FEED_SOURCES = frozenset({"remoteok", "jobicy", "himalayas", "wwr", "startupjobs"})
CONFIDENCE = {"unknown": 0, "first_seen": 0, "relative_estimate": 1,
              "feed_updated_timestamp": 1,
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


def observe_requisition(job: Job, state: dict, checked_at: str | None = None) -> bool:
    """Preserve the first observation and the strongest early posting date."""
    when = checked_at or iso_now()
    key = requisition_key(job)
    rows = state.setdefault("requisitions", {})
    prior = rows.get(key)
    legacy = state.setdefault("jobs", {})
    old_uid = legacy.get(job.uid)
    is_new = prior is None and old_uid is None
    rec = rows.setdefault(key, {})
    previous_first = rec.get("first_seen_at") or (old_uid or {}).get("first_seen_at")
    job.first_seen_at = previous_first or job.first_seen_at or when
    rec["first_seen_at"] = job.first_seen_at
    rec["last_seen_at"] = when
    rec["last_title"] = job.title
    rec["last_uid"] = job.uid
    rec["observations"] = int(rec.get("observations", 0)) + 1
    rec["alerted"] = bool(rec.get("alerted") or (old_uid or {}).get("alerted"))

    newer_date = parse_dt(job.published_at)
    earlier_date = parse_dt(rec.get("first_published_at"))
    new_basis = publication_basis(job)
    old_basis = rec.get("publication_basis", "unknown")
    if newer_date and (not earlier_date or
            CONFIDENCE.get(new_basis, 0) > CONFIDENCE.get(old_basis, 0) or
            (new_basis == old_basis and newer_date < earlier_date)):
        rec["first_published_at"] = job.published_at
        rec["publication_basis"] = new_basis
    if rec.get("first_published_at"):
        job.published_at = rec["first_published_at"]
        job.publication_basis = rec.get("publication_basis", "unknown")
    else:
        job.publication_basis = "first_seen"
    job.history_key = key
    legacy.setdefault(job.uid, {"first_seen_at": job.first_seen_at, "alerted": rec["alerted"]})
    return is_new


def remember_verification(job: Job, state: dict) -> None:
    """A failure to verify is not proof that the employer has closed a job."""
    if not job.availability_checked_at:
        return
    key = job.history_key or requisition_key(job)
    rec = state.setdefault("requisitions", {}).setdefault(key, {})
    rec["last_checked_at"] = job.availability_checked_at
    rec["last_status"] = job.availability
    rec["last_status_note"] = job.availability_note
    if job.availability == "Closed":
        rec.setdefault("first_closed_at", job.availability_checked_at)
