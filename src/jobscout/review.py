"""Conservative availability checks and portable review labels."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .http import UA
from .utils import iso_now, strip_html


def review_status(job):
    if not job.eligible:
        return 'Excluded'
    if job.risks or job.availability != 'Available':
        return 'Needs verification'
    return 'Worth reviewing'



def _smartrecruiters_public_check(job):
    """Verify the exact requisition is on the public ACTIVE list.

    A detail endpoint alone can persist after a role closes. Not finding a
    listing in a text-filtered page is inconclusive, never a closure signal.
    """
    parts = (job.uid or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "smartrecruiters":
        return job
    board, posting_id = parts[1:]
    if not re.fullmatch(r"[\w.-]{1,100}", board) or not re.fullmatch(r"[\w-]{1,100}", posting_id):
        job.availability_note = "Invalid SmartRecruiters requisition identifier."
        return job
    base = (f"https://api.smartrecruiters.com/v1/companies/"
            f"{urllib.parse.quote(board, safe='')}/postings")
    try:
        query = urllib.parse.urlencode({"q": job.title, "limit": 100, "offset": 0, "destination": "PUBLIC"})
        request = urllib.request.Request(base + "?" + query,
                                         headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=8) as response:
            listing = json.loads(response.read(2_000_000).decode("utf-8"))
        found = any(str(row.get("id") or row.get("uuid") or "") == posting_id
                    for row in listing.get("content") or [])
        if not found:
            job.availability_note = ("Exact requisition not confirmed in filtered public active list; "
                                     "search coverage may be incomplete.")
            return job
        request = urllib.request.Request(base + "/" + urllib.parse.quote(posting_id, safe=''),
                                         headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=8) as response:
            detail = json.loads(response.read(2_000_000).decode("utf-8"))
        normalized = lambda value: re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
        if (str(detail.get("id") or detail.get("uuid") or "") != posting_id
                or normalized(detail.get("name", "")) != normalized(job.title)):
            job.availability_note = "Public listing and posting details do not agree on requisition/title."
            return job
        apply_url = detail.get("applyUrl") or detail.get("postingUrl") or job.apply_url or job.job_url
        parsed = urllib.parse.urlparse(str(apply_url))
        if parsed.scheme != "https" or parsed.hostname != "jobs.smartrecruiters.com":
            job.availability_note = "Public requisition confirmed, but employer-facing application link is unverified."
            return job
        # Only replace links with an employer-returned canonical page for this ID.
        if not re.search(r"/" + re.escape(posting_id) + r"(?:[-/?#]|$)", parsed.path + "/"):
            job.availability_note = "Public requisition confirmed, but application URL does not match its ID."
            return job
        job.apply_url = str(apply_url)
        job.availability = "Available"
        job.availability_note = ("Exact requisition confirmed on active public SmartRecruiters list and "
                                 "in employer detail; application submission not tested.")
    except urllib.error.HTTPError as exc:
        # A missing detail or a restricted/failed list is not proof of closure.
        job.availability_note = f"SmartRecruiters public verification HTTP {exc.code}; availability unverified."
    except (OSError, ValueError, KeyError, TypeError) as exc:
        job.availability_note = f"SmartRecruiters public verification inconclusive ({type(exc).__name__})."
    return job


def check_availability(job):
    job.availability_checked_at = iso_now()
    job.availability = 'Unverified'
    job.availability_note = 'Could not confirm that this specific posting is accepting applications.'
    url = job.apply_url or job.job_url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname:
        job.availability_note = 'No valid posting URL.'
        return job
    if job.source == 'smartrecruiters':
        return _smartrecruiters_public_check(job)
    is_workday = job.source == 'workday' and parsed.hostname.endswith('.myworkdayjobs.com')
    if is_workday:
        parts = parsed.path.strip('/').split('/')
        if parts and re.fullmatch('[a-z]{2}-[A-Z]{2}', parts[0]):
            parts.pop(0)
        if len(parts) < 3 or parts[1] != 'job':
            return job
        site = parts.pop(0)
        url = f'{parsed.scheme}://{parsed.netloc}/wday/cxs/{parsed.hostname.split(".")[0]}/{site}/' + '/'.join(parts)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json' if is_workday else 'text/html'})
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read(2_000_000).decode('utf-8', errors='replace')
            final_url = response.geturl()
        if is_workday:
            info = json.loads(raw).get('jobPostingInfo', {})
            if info.get('canApply') is False:
                job.availability = 'Closed'
                job.availability_note = 'Employer detail explicitly disables applications.'
            elif info.get('title') and info.get('jobDescription'):
                job.availability = 'Available'
                job.availability_note = 'Employer posting detail returned during this check; verify on application.'
        else:
            text = strip_html(raw)
            closed = re.search(
                r'(?:this\s+(?:job(?:\s+post(?:ing)?)?|position|posting)\s+'
                r'(?:is\s+)?(?:no\s+longer\s+(?:available|exists|accepting\s+applications)|'
                r'has\s+been\s+(?:filled|closed))|'
                r'(?:job|position|posting)\s+(?:not\s+found|does\s+not\s+exist)|'
                r'(?:this\s+)?(?:job|position|posting)\s+has\s+expired|'
                r'no\s+longer\s+accepting\s+applications)',
                text, re.I,
            )
            # Generic career-page redirects are not proof that a posting closed.
            same_path = urllib.parse.urlparse(final_url).path.rstrip('/') == parsed.path.rstrip('/')
            def normalize(s):
                return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()
            if closed and same_path:
                job.availability = 'Closed'
                job.availability_note = 'Posting page explicitly says it is closed or unavailable.'
            elif same_path and normalize(job.title) in normalize(text) and re.search(r'apply (?:now|for|to|for this job)|submit application', text, re.I):
                job.availability = 'Available'
                job.availability_note = 'Posting title and application text found on its page.'
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            job.availability = 'Closed'
            job.availability_note = f'Posting endpoint returned HTTP {exc.code}.'
        else:
            job.availability_note = f'Availability unverified: HTTP {exc.code}; this is not evidence of closure.'
    except (OSError, ValueError) as exc:
        job.availability_note = f'Availability unverified: {type(exc).__name__}; this is not evidence of closure.'
    return job


def verify_candidates(jobs, rejected, progress=None):
    if progress:
        progress(f'Checking availability of {len(jobs)} candidate postings…')
    with ThreadPoolExecutor(max_workers=4) as pool:
        checked = list(pool.map(check_availability, jobs))
    remaining = []
    for job in checked:
        if job.availability == 'Closed':
            job.eligible = False
            job.veto_reason = 'Posting closed/unavailable: ' + job.availability_note
            job.risks = (job.risks or []) + [job.veto_reason]
            rejected.append(job)
        else:
            remaining.append(job)
    return remaining, rejected
