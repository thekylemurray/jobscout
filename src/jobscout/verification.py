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
from .rules import DIRECT_SOURCES
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


def _title_in_heading(html_text: str, title: str) -> bool:
    """Require job-specific title evidence, not a phrase in global navigation."""
    wanted = _norm(title)
    if not wanted:
        return False
    headings = re.findall(r"<(?:h1|h2|title)\b[^>]*>(.*?)</(?:h1|h2|title)>",
                          html_text, flags=re.I | re.S)
    for heading in headings:
        actual = _norm(strip_html(heading))
        if actual == wanted or actual.startswith(wanted + " ") or actual.endswith(" " + wanted):
            return True
    return False


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


def _structured_ats_endpoint(job):
    """Identify the exact public ATS detail URL from a normalized source ID."""
    source = job.source
    if source not in {"greenhouse", "smartrecruiters"}:
        return None
    parts = (job.uid or "").split(":")
    if len(parts) < 3 or parts[0] != source:
        return None
    board = ":".join(parts[1:-1])
    job_id = parts[-1]
    if not board or not job_id:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", board):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", job_id):
        return None
    quoted_board = urllib.parse.quote(board, safe="")
    quoted_id = urllib.parse.quote(job_id, safe="")
    if source == "greenhouse":
        return (f"https://boards-api.greenhouse.io/v1/boards/{quoted_board}/jobs/{quoted_id}"
                "?content=true")
    return (f"https://api.smartrecruiters.com/v1/companies/{quoted_board}/postings/{quoted_id}")


def _structured_ats_check(job, timeout: int):
    """Return positive exact-ID evidence or None when public data is inconclusive.

    A missing/blocked API record falls back to the actual application page;
    a 404 from an API alone is not sufficient proof that hiring closed.
    """
    endpoint = _structured_ats_endpoint(job)
    if not endpoint:
        return None
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
        if not isinstance(data, dict):
            return None
        if job.source == "greenhouse":
            actual_id = str(data.get("id", ""))
            actual_title = data.get("title") or ""
            apply_url = data.get("absolute_url") or ""
            expected_id = (job.uid or "").split(":")[-1]
            if (actual_id == expected_id and _norm(actual_title) == _norm(job.title)
                    and _safe_public_url(apply_url)):
                return ("Available", "Matching requisition and employer application URL confirmed by Greenhouse API.")
        elif job.source == "smartrecruiters":
            actual_id = str(data.get("id", ""))
            actual_title = data.get("name") or ""
            expected_id = (job.uid or "").split(":")[-1]
            apply_url = data.get("applyUrl") or data.get("postingUrl") or ""
            if (actual_id == expected_id and _norm(actual_title) == _norm(job.title)
                    and _safe_public_url(apply_url)):
                return ("Available", "Matching requisition and application URL confirmed by SmartRecruiters API.")
    except (urllib.error.URLError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


def check_application(job, timeout: int = 8):
    """Return Available, Closed or Unverified; do not infer closure from 403/429."""
    job.availability = "Unverified"
    job.availability_checked_at = iso_now()
    job.availability_note = "Could not independently verify this exact application."
    original = job.job_url or job.apply_url
    # For aggregator discoveries, check the employer application if one exists.
    aggregator_hosts = ("remoteok.com", "jobicy.com", "himalayas.app",
                        "weworkremotely.com", "startup.jobs")
    employer_application = False
    if job.source in {"remoteok", "jobicy", "himalayas", "wwr", "startupjobs"}:
        application = job.apply_url or ""
        if _safe_public_url(application):
            host = (urllib.parse.urlsplit(application).hostname or "").lower()
        else:
            host = ""
        if host and not any(
                host == root or host.endswith("." + root) for root in aggregator_hosts):
            original = application
            employer_application = True
    if not _safe_public_url(original):
        job.availability_note = "No safe, valid posting URL."
        return job
    structured = _structured_ats_check(job, timeout)
    if structured is not None:
        job.availability, job.availability_note = structured
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
        elif (_same_posting(original, resolved) and _title_in_heading(raw, job.title)
                and APPLY.search(raw)):
            if job.source in {"remoteok", "jobicy", "himalayas", "wwr"} and not employer_application:
                job.availability_note = "Aggregator page available; employer application unverified."
            else:
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


AGGREGATOR_SOURCES = frozenset({"remoteok", "jobicy", "himalayas", "wwr"})
AGGREGATOR_HOSTS = ("remoteok.com", "jobicy.com", "himalayas.app",
                    "weworkremotely.com", "startup.jobs")


def _has_external_application(job) -> bool:
    """Aggregator job-list pages are not proof an employer is accepting applications."""
    if job.source not in AGGREGATOR_SOURCES:
        return True
    apply_url = job.apply_url or ""
    if not _safe_public_url(apply_url):
        return False
    host = (urllib.parse.urlsplit(apply_url).hostname or "").lower()
    return not any(host == root or host.endswith("." + root) for root in AGGREGATOR_HOSTS)


def select_verification_candidates(jobs, config: dict):
    """Verify plausible employer applications, not aggregator search results.

    Source coverage is not a target: 10 meaningful checks are better than 40
    HTTP 403s. Unsupported aggregators remain in results for manual review.
    """
    max_checks = max(0, min(int(config.get("verification_max_per_scan", 40)), 100))
    min_fit = float(config.get("dashboard_threshold", 52))
    eligible = [j for j in jobs if j.eligible and j.fit_score >= min_fit]
    ranking = lambda j: (j.fresh, j.priority_score, j.fit_score)
    direct = sorted((j for j in eligible if j.source in DIRECT_SOURCES),
                    key=ranking, reverse=True)
    linked = sorted((j for j in eligible if j.source not in DIRECT_SOURCES
                     and _has_external_application(j)), key=ranking, reverse=True)
    # Prefer employer-sourced records; never burn a check on aggregator-only URLs.
    return (direct + linked)[:max_checks]


def verify_shortlist(jobs, config: dict, log: list[str]):
    """Check the strongest matches in parallel without slowing every feed query."""
    candidates = select_verification_candidates(jobs, config)
    ids = {id(j) for j in candidates}
    for job in jobs:
        if (id(job) not in ids and job.source in AGGREGATOR_SOURCES
                and not _has_external_application(job)):
            job.availability_note = "Aggregator-only link; employer application not independently verifiable."
    skipped = sum(j.source in AGGREGATOR_SOURCES and not _has_external_application(j)
                  for j in jobs)
    log.append(f"APPLICATION_CHECK_SCOPE {len(candidates)} requested / "
               f"{sum(j.source in DIRECT_SOURCES for j in candidates)} employer-hosted / "
               f"{len(candidates) - sum(j.source in DIRECT_SOURCES for j in candidates)} employer-linked aggregators / "
               f"{skipped} aggregator-only skipped")
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
