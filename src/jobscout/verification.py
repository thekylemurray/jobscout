"""Conservative HTTP checks of the exact employer application for CLI searches."""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .http import UA
from .utils import iso_now, strip_html

CLOSED = re.compile(
    r"(?:this\s+(?:job(?:\s+post(?:ing)?)?|position|posting)\s+"
    r"(?:is\s+)?(?:no\s+longer\s+(?:available|exists|accepting\s+applications)|"
    r"has\s+been\s+(?:filled|closed))|"
    r"(?:job|position|posting)\s+(?:not\s+found|does\s+not\s+exist)|"
    r"(?:this\s+)?(?:job|position|posting)\s+has\s+expired|"
    r"no\s+longer\s+accepting\s+applications)", re.I
)
APPLY = re.compile(r"(?:apply\s+(?:now|for\s+this\s+(?:job|position)|for|to)|submit\s+application|job_application)", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _safe_public_url(url: str) -> bool:
    try:
        uri = urllib.parse.urlsplit(url)
        host = (uri.hostname or "").lower()
        if uri.scheme not in ("http", "https") or not host:
            return False
        if host == "localhost" or host.endswith((".local", ".internal")):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


def _same_posting(start: str, final: str) -> bool:
    a, b = urllib.parse.urlsplit(start), urllib.parse.urlsplit(final)
    if a.hostname == b.hostname and a.path.rstrip("/") == b.path.rstrip("/"):
        return True
    ma, mb = re.search(r"/jobs/(\d+)", a.path), re.search(r"/jobs/(\d+)", b.path)
    return bool(ma and mb and ma.group(1) == mb.group(1))


def _workday_endpoint(url: str) -> str | None:
    uri = urllib.parse.urlsplit(url)
    if not (uri.hostname or "").endswith(".myworkdayjobs.com"):
        return None
    parts = [urllib.parse.unquote(p) for p in uri.path.split("/") if p]
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        parts.pop(0)
    if len(parts) < 3 or parts[1] != "job":
        return None
    site = parts[0]
    tail = "/".join(parts[1:])
    tenant = uri.hostname.split(".")[0]
    return f"{uri.scheme}://{uri.netloc}/wday/cxs/{tenant}/{site}/{tail}"


def check_application(job, timeout: int = 8):
    """Return Available, Closed or Unverified; do not infer closure from 403/429."""
    job.availability = "Unverified"
    job.availability_checked_at = iso_now()
    job.availability_note = "Could not independently verify this exact application."
    original = job.job_url or job.apply_url
    if not _safe_public_url(original):
        job.availability_note = "No safe, valid posting URL."
        return job
    endpoint = _workday_endpoint(original)
    requested = endpoint or original
    try:
        headers = {"User-Agent": UA, "Accept": "application/json" if endpoint else "text/html"}
        req = urllib.request.Request(requested, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(1_000_000).decode("utf-8", errors="replace")
            resolved = response.geturl()
        if not _safe_public_url(resolved):
            job.availability_note = "Posting redirected to an unverifiable destination."
            return job
        if endpoint:
            data = json.loads(raw)
            info = data.get("jobPostingInfo", {})
            if info.get("canApply") is False:
                job.availability = "Closed"
                job.availability_note = "Employer ATS explicitly disabled applications."
            elif (_norm(job.title) == _norm(info.get("title") or "")
                    and info.get("jobDescription")):
                job.availability = "Available"
                job.availability_note = "Matching employer ATS job detail is accessible."
            else:
                job.availability_note = "Employer ATS detail could not confirm this posting."
            return job

        text = strip_html(raw)
        if CLOSED.search(text) and _same_posting(original, resolved):
            job.availability = "Closed"
            job.availability_note = "Posting page explicitly reports an unavailable job."
        elif (_same_posting(original, resolved) and _norm(job.title) in _norm(text)
                and APPLY.search(raw)):
            job.availability = "Available"
            job.availability_note = "Matching job title and application call-to-action found."
        else:
            job.availability_note = "Posting could not be confirmed; check manually."
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410) and not endpoint:
            job.availability = "Closed"
            job.availability_note = f"Posting URL returned HTTP {exc.code}."
        else:
            job.availability_note = f"Unverified HTTP {exc.code}; not evidence of closure."
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        job.availability_note = f"Unverified {type(exc).__name__}; not evidence of closure."
    return job


def verify_shortlist(jobs, config: dict, log: list[str]):
    """Check the strongest matches in parallel without slowing every feed query."""
    max_checks = max(0, min(int(config.get("verification_max_per_scan", 40)), 100))
    candidates = sorted(jobs, key=lambda job: (job.priority_score, job.fit_score), reverse=True)[:max_checks]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(check_application, candidates))
    retained, closed = [], []
    for job in jobs:
        if job.availability == "Closed":
            job.eligible = False
            job.veto_reason = "Verified unavailable: " + job.availability_note
            job.risks = (job.risks or []) + [job.veto_reason]
            closed.append(job)
        else:
            retained.append(job)
    stats = {s: sum(j.availability == s for j in jobs) for s in ("Available", "Closed", "Unverified")}
    log.append(f"APPLICATION_CHECKS {stats['Available']} available / {stats['Closed']} closed / {stats['Unverified']} unverified")
    return retained, closed
