"""Persistent, conservative identity and provenance for employer requisitions.

The canonical requisition record is scoped to a user's local profile. URLs and
ATS IDs are identifiers, not evidence of job availability or publication.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from .models import Job
from .utils import canonical_company, iso_now, parse_dt


def requisition_key(job: Job) -> str:
    """Keep the same employer requisition stable across scans and title changes."""
    company = canonical_company(job.company)
    for url in (job.job_url, job.apply_url):
        try:
            parsed = urlsplit(url or "")
        except ValueError:
            continue
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/").lower()
        params = parse_qs(parsed.query)
        if "greenhouse" in host:
            match = re.search(r"/jobs/(\d+)", path)
            number = (params.get("gh_jid") or [None])[0] or (match.group(1) if match else None)
            if number:
                return f"{company}:greenhouse:{number}"
        if host.endswith("lever.co"):
            match = re.search(r"/([0-9a-f]{8}-[0-9a-f-]{27,})$", path)
            if match:
                return f"{company}:lever:{match.group(1)}"
        if host.endswith("myworkdayjobs.com"):
            match = re.search(r"/job/.+?_([a-z0-9-]+)$", path)
            if match:
                return f"{company}:workday:{match.group(1)}"
        if "ashbyhq.com" in host:
            match = re.search(r"/([0-9a-f]{8}-[0-9a-f-]{27,})$", path)
            if match:
                return f"{company}:ashby:{match.group(1)}"
    # A stable upstream ID is stronger than a title or a URL tracking parameter.
    if job.uid:
        return f"{company}:{job.uid.lower()}"
    url = urlsplit(job.job_url or job.apply_url or "")
    return f"{company}:url:{url.netloc.lower()}{url.path.rstrip('/').lower()}"


def reconcile_requisition(job: Job, state: dict, *, seen_at: str | None = None) -> bool:
    """Restore original first-seen/publication dates; never re-age a repost.

    Returns True only when this requisition is absent from both new and legacy
    state. This keeps a previously seen role from being announced as brand new.
    """
    stamp = seen_at or iso_now()
    key = requisition_key(job)
    history = state.setdefault("requisitions", {})
    legacy = state.setdefault("jobs", {})
    original = history.get(key)
    previous = legacy.get(job.uid, {})
    is_new = original is None and not previous
    record = history.setdefault(key, {})
    first = record.get("first_seen_at") or previous.get("first_seen_at") or job.first_seen_at or stamp
    job.first_seen_at = first
    record["first_seen_at"] = first
    record["last_seen_at"] = stamp
    record["observations"] = int(record.get("observations", 0)) + 1
    record["last_title"] = job.title
    record["last_uid"] = job.uid
    record["alerted"] = bool(record.get("alerted") or previous.get("alerted", False))
    if job.published_at and parse_dt(job.published_at):
        original_pub = record.get("first_published_at")
        if not original_pub or (parse_dt(original_pub) and parse_dt(job.published_at) < parse_dt(original_pub)):
            record["first_published_at"] = job.published_at
    if record.get("first_published_at"):
        job.published_at = record["first_published_at"]
    job.history_key = key
    legacy.setdefault(job.uid, {"first_seen_at": first, "alerted": record["alerted"]})
    return is_new


def record_verification(job: Job, state: dict) -> None:
    """Preserve verification history without treating missing feed data as closure."""
    key = job.history_key or requisition_key(job)
    record = state.setdefault("requisitions", {}).setdefault(key, {})
    if job.availability_checked_at:
        record["last_checked_at"] = job.availability_checked_at
        record["last_verification"] = job.availability
        record["last_verification_note"] = job.availability_note
        if job.availability == "Closed":
            record.setdefault("first_closed_at", job.availability_checked_at)
