"""Public employer/job-feed adapters added after JobScout 2.1.

These endpoints are read-only and require no private credentials. Each adapter
produces the existing Job model and leaves classification to the scorer.
"""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import timezone
from typing import Any

from .http import request_json, request_xml
from .models import Job
from .utils import as_text, strip_html


def _account(board: str) -> str:
    """Accept a bare public careers account slug, not arbitrary fetch URLs."""
    board = board.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,78}", board):
        raise ValueError("Expected a public ATS account slug using letters, digits and hyphens")
    return board


def workable_jobs(company: str, board: str, first_seen: str,
                  cache: dict[str, Any] | None = None) -> list[Job]:
    """Workable's published-jobs widget API (no employer admin token)."""
    account = _account(board)
    payload = request_json(
        f"https://apply.workable.com/api/v1/widget/accounts/{account}?details=true"
    )
    if not isinstance(payload, dict):
        raise ValueError("Workable response missing jobs envelope")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Workable response missing jobs list")

    out: list[Job] = []
    for row in jobs:
        if not isinstance(row, dict):
            continue
        title = as_text(row.get("title")).strip()
        job_id = str(row.get("shortcode") or row.get("code") or "").strip()
        if not title or not job_id:
            continue
        location = ", ".join(str(row.get(key)).strip()
                             for key in ("city", "state", "country") if row.get(key))
        locations: list[str] = []
        if location:
            locations.append(location)
        for extra in (row.get("locations") or []):
            if isinstance(extra, dict):
                label = ", ".join(as_text(extra.get(k)).strip()
                                  for k in ("city", "state", "country") if extra.get(k))
            elif isinstance(extra, str):
                label = extra.strip()
            else:
                label = ""
            if label and label not in locations:
                locations.append(label)
        location = " | ".join(locations)
        workplace = as_text(row.get("workplace_type", "")).strip().title()
        remote = row.get("telecommuting") is True or workplace.lower() == "remote"
        if remote:
            location = ("Remote - " + location) if location else "Remote"
            workplace = "Remote"
        job_url = as_text(row.get("application_url") or row.get("shortlink")
                          or row.get("url") or "").strip()
        apply_url = as_text(row.get("url") or row.get("application_url")
                            or job_url).strip()
        # Some widget configurations omit one of the two URL fields.
        if not (job_url.startswith("https://") or job_url.startswith("http://")):
            continue
        out.append(Job(
            uid=f"workable:{account}:{job_id}",
            company=as_text(company or payload.get("name") or "Workable"),
            source="workable",
            title=title, location=location,
            workplace=workplace,
            employment_type=as_text(row.get("employment_type", "")),
            description=strip_html(as_text(row.get("description", ""))),
            job_url=job_url, apply_url=apply_url,
            published_at=row.get("published_on") or None,
            first_seen_at=first_seen,
            compensation="",
            publication_basis="employer_timestamp" if row.get("published_on") else "",
        ))
    return out


def _xml_text(parent: ET.Element, name: str) -> str:
    return (parent.findtext(name) or "").strip()


def recruitee_jobs(company: str, board: str, first_seen: str,
                   cache: dict[str, Any] | None = None) -> list[Job]:
    """Only published offers from Recruitee's separate no-token XML feed."""
    account = _account(board)
    raw = request_xml(f"https://{account}.recruitee.com/api/feeds/offers.xml")
    root = ET.fromstring(raw)
    if root.tag != "jobs":
        raise ValueError("Unexpected Recruitee XML feed structure")

    out: list[Job] = []
    for offer in root.findall("job"):
        req_id = _xml_text(offer, "reference")
        title = _xml_text(offer, "title")
        job_url = _xml_text(offer, "url")
        apply_url = _xml_text(offer, "apply_url") or job_url
        if not title or not req_id or not job_url.startswith(("https://", "http://")):
            continue
        locations: list[str] = []
        for node in offer.findall("./locations/location"):
            parts = [_xml_text(node, key) for key in ("city", "state", "country")]
            label = ", ".join(p for p in parts if p)
            if label and label not in locations:
                locations.append(label)
        if not locations:
            parts = [_xml_text(offer, key) for key in ("city", "state", "country")]
            location = ", ".join(p for p in parts if p)
            if location:
                locations.append(location)
        remote = _xml_text(offer, "remote").lower() == "true"
        hybrid = _xml_text(offer, "hybrid").lower() == "true"
        loc = " | ".join(locations)
        if remote:
            loc = f"Remote - {loc}" if loc else "Remote"
        workplace = "Remote" if remote else ("Hybrid" if hybrid else "On-site")
        salary = offer.find("salary")
        compensation = ""
        if salary is not None:
            low = _xml_text(salary, "min_salary")
            high = _xml_text(salary, "max_salary")
            currency = _xml_text(salary, "currency")
            period = _xml_text(salary, "period")
            if low or high:
                compensation = f"{currency} {low}-{high} {period}".strip()
        pub = _xml_text(offer, "posted")
        out.append(Job(
            uid=f"recruitee:{account}:{req_id}",
            company=_xml_text(offer, "company") or company,
            source="recruitee",
            title=title,
            location=loc,
            workplace=workplace,
            employment_type=_xml_text(offer, "contract_type"),
            description=strip_html(_xml_text(offer, "description_requirements")),
            job_url=job_url, apply_url=apply_url,
            published_at=pub or None,
            updated_at=_xml_text(offer, "updated") or None,
            first_seen_at=first_seen,
            compensation=compensation,
            publication_basis="employer_timestamp" if pub else "",
        ))
    return out


def startupjobs_jobs(company: str, board: str, first_seen: str,
                     cache: dict[str, Any] | None = None) -> list[Job]:
    """Startup Jobs' no-key RSS feed, not a verified employer ATS application.

    Source attribution remains visible, and the job page is not represented
    as a direct employer application unless an independently supplied link exists.
    """
    parsed = urllib.parse.urlsplit(board)
    if parsed.scheme != "https" or parsed.hostname != "startup.jobs" or parsed.path != "/feeds/jobs":
        raise ValueError("Startup Jobs board must be https://startup.jobs/feeds/jobs with optional filters")
    raw = request_xml(board)
    root = ET.fromstring(raw)
    if root.tag not in ("rss", "RDF"):
        raise ValueError("Unexpected Startup Jobs RSS response")
    out: list[Job] = []
    for item in root.findall(".//item"):
        raw_title = _xml_text(item, "title")
        job_url = _xml_text(item, "link")
        guid = _xml_text(item, "guid") or job_url
        if not raw_title or not guid or not job_url.startswith(("https://", "http://")):
            continue
        # Recognize employer-prefixed RSS titles; avoid inventing a company.
        employer = ""
        title = raw_title
        if ": " in raw_title:
            maybe_company, maybe_title = raw_title.split(": ", 1)
            if maybe_company and maybe_title:
                employer, title = maybe_company.strip(), maybe_title.strip()
        elif " at " in raw_title:
            maybe_title, maybe_company = raw_title.rsplit(" at ", 1)
            if maybe_title and maybe_company:
                employer, title = maybe_company.strip(), maybe_title.strip()
        description = strip_html(_xml_text(item, "description"))
        published = None
        date_text = _xml_text(item, "pubDate")
        if date_text:
            try:
                published = parsedate_to_datetime(date_text).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                pass
        # No U.S. restriction is inferred merely because the remote filter matched.
        location = _xml_text(item, "location") or _xml_text(item, "region")
        out.append(Job(
            uid=f"startupjobs:{guid}",
            company=employer or "Startup Jobs (employer unlisted)",
            source="startupjobs",
            title=title,
            location=location,
            workplace="Remote" if "workplace=remote" in parsed.query else "",
            employment_type="",
            description=description,
            job_url=job_url,
            apply_url=job_url,
            published_at=published,
            first_seen_at=first_seen,
            compensation="",
            publication_basis="feed_timestamp" if published else "",
        ))
    return out
