from __future__ import annotations

import json
import re
import urllib.parse
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
import xml.etree.ElementTree as ET

from .http import UA, request_json, request_json_post, request_text, request_xml
from .models import Job
from .rules import TITLE_TERMS
from .utils import as_text, has_any, has_term, now_utc, strip_html

def ashby_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    board_q = urllib.parse.quote(board, safe="")
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_q}?includeCompensation=true"
    data = request_json(url)
    out: list[Job] = []
    for j in data.get("jobs", []):
        if not j.get("isListed", True):
            continue
        job_url = j.get("jobUrl") or ""
        uid = f"ashby:{board}:{job_url or j.get('title','')}"
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        out.append(Job(
            uid=uid,
            company=company,
            source="ashby",
            title=j.get("title", ""),
            location=j.get("location", ""),
            workplace=j.get("workplaceType", "") or ("Remote" if j.get("isRemote") else ""),
            employment_type=j.get("employmentType", ""),
            description=j.get("descriptionPlain", "") or strip_html(j.get("descriptionHtml", "")),
            job_url=job_url,
            apply_url=j.get("applyUrl") or job_url,
            published_at=j.get("publishedAt"),
            first_seen_at=first_seen,
            compensation=comp,
        ))
    return out

def greenhouse_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    board_q = urllib.parse.quote(board, safe="")
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_q}/jobs?content=true"
    data = request_json(url)
    out: list[Job] = []
    for j in data.get("jobs", []):
        job_url = j.get("absolute_url", "")
        out.append(Job(
            uid=f"greenhouse:{board}:{j.get('id')}",
            company=company,
            source="greenhouse",
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            workplace="",
            employment_type="",
            description=strip_html(j.get("content", "")),
            job_url=job_url,
            apply_url=job_url,
            # Greenhouse exposes first_published on the LIST response. v0.1
            # ignored it and accidentally marked the entire board as 0.0h old.
            published_at=j.get("first_published"),
            updated_at=j.get("updated_at"),
            first_seen_at=first_seen,
            compensation="",
        ))
    return out

def lever_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    board_q = urllib.parse.quote(board, safe="")
    url = f"https://api.lever.co/v0/postings/{board_q}?mode=json"
    data = request_json(url)
    out: list[Job] = []
    for j in data:
        cats = j.get("categories") or {}
        desc = " ".join([
            j.get("descriptionPlain", "") or "",
            strip_html(j.get("additional", "") or ""),
            " ".join(strip_html(x.get("content", "")) for x in (j.get("lists") or [])),
        ])
        sal = j.get("salaryRange") or {}
        comp = ""
        if sal:
            comp = f"{sal.get('currency','')} {sal.get('min','')}-{sal.get('max','')} {sal.get('interval','')}".strip()
        out.append(Job(
            uid=f"lever:{board}:{j.get('id')}",
            company=company,
            source="lever",
            title=j.get("text", ""),
            location=cats.get("location", "") or ", ".join(cats.get("allLocations") or []),
            workplace=j.get("workplaceType", ""),
            employment_type=cats.get("commitment", ""),
            description=desc,
            job_url=j.get("hostedUrl", ""),
            apply_url=j.get("applyUrl", "") or j.get("hostedUrl", ""),
            published_at=None,
            first_seen_at=first_seen,
            compensation=comp,
        ))
    return out

def remoteok_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    """Fetch the newest remote roles from Remote OK's public JSON feed.

    Remote OK includes publication dates, tags, salary fields and direct application
    URLs. The first JSON object is feed metadata rather than a job, so it is skipped.
    """
    data = request_json(board)
    out: list[Job] = []

    if not isinstance(data, list):
        return out

    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue

        title = j.get("position", "") or ""
        employer = j.get("company", "") or "Remote OK"
        location = j.get("location", "") or "Worldwide"
        tags = " ".join(j.get("tags") or [])
        description = " ".join([
            strip_html(j.get("description", "") or ""),
            tags,
        ])

        salary_min = j.get("salary_min")
        salary_max = j.get("salary_max")
        comp = ""
        if salary_min or salary_max:
            comp = f"USD {salary_min or ''}-{salary_max or ''}".strip("-")

        job_url = j.get("url", "") or ""
        apply_url = j.get("apply_url", "") or job_url
        jid = str(j.get("id") or j.get("slug") or apply_url or title)

        out.append(Job(
            uid=f"remoteok:{jid}",
            company=employer,
            source="remoteok",
            title=title,
            location=location,
            workplace="Remote",
            employment_type="",
            description=description,
            job_url=job_url,
            apply_url=apply_url,
            published_at=j.get("date"),
            first_seen_at=first_seen,
            compensation=comp,
        ))
    return out

def smartrecruiters_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    """SmartRecruiters public Posting API.

    releasedDate is an authoritative publication timestamp. Full descriptions are
    fetched only for plausible titles or Marketing/Communications functions.
    """
    out: list[Job] = []
    offset = 0
    limit = 100
    seen_ids: set[str] = set()

    while True:
        list_url = (
            f"https://api.smartrecruiters.com/v1/companies/"
            f"{urllib.parse.quote(board, safe='')}/postings"
            f"?limit={limit}&offset={offset}&destination=PUBLIC"
        )
        data = request_json(list_url)
        rows = data.get("content") or []
        total = int(data.get("totalFound") or 0)
        if not rows:
            break

        for j in rows:
            jid = str(j.get("id") or j.get("uuid") or "")
            if not jid or jid in seen_ids:
                continue
            seen_ids.add(jid)

            title = j.get("name", "") or ""
            function = ((j.get("function") or {}).get("label") or "")
            department = ((j.get("department") or {}).get("label") or "")
            should_detail = (
                title_might_be_relevant(title)
                or has_any(function, ["marketing", "communications", "content"])
                or has_any(department, ["marketing", "communications", "content", "digital"])
            )
            if not should_detail:
                # Still emit a lightweight record; hard filters will dispose of it.
                detail = j
            else:
                detail_url = (
                    f"https://api.smartrecruiters.com/v1/companies/"
                    f"{urllib.parse.quote(board, safe='')}/postings/{urllib.parse.quote(jid, safe='')}"
                )
                try:
                    detail = request_json(detail_url)
                except Exception:
                    detail = j

            loc = detail.get("location") or j.get("location") or {}
            city = loc.get("city") or ""
            region = loc.get("region") or ""
            country = (loc.get("country") or "").upper()
            remote = bool(loc.get("remote"))
            loc_parts = [x for x in [city, region, country] if x]
            location = ", ".join(loc_parts)
            if remote and country in {"US", "USA"}:
                location = "Remote - US" + (f" | {location}" if location else "")
            elif remote and not location:
                location = "Remote"

            sections = ((detail.get("jobAd") or {}).get("sections") or {})
            desc_parts: list[str] = []
            for key in ["companyDescription", "jobDescription", "qualifications", "additionalInformation"]:
                sec = sections.get(key) or {}
                if isinstance(sec, dict):
                    desc_parts.append(strip_html(sec.get("text", "") or ""))
            desc = " ".join(x for x in desc_parts if x)
            if not desc:
                desc = " ".join([title, function, department])

            posting_url = detail.get("postingUrl") or ""
            apply_url = detail.get("applyUrl") or posting_url or (detail.get("ref") or "")
            emp = ((detail.get("typeOfEmployment") or {}).get("label")
                   or (j.get("typeOfEmployment") or {}).get("label") or "")

            out.append(Job(
                uid=f"smartrecruiters:{board}:{jid}",
                company=(detail.get("company") or {}).get("name") or company,
                source="smartrecruiters",
                title=title,
                location=location,
                workplace="Remote" if remote else "",
                employment_type=emp,
                description=desc,
                job_url=posting_url or apply_url,
                apply_url=apply_url,
                published_at=detail.get("releasedDate") or j.get("releasedDate"),
                first_seen_at=first_seen,
                compensation="",
            ))

        offset += len(rows)
        if offset >= total or len(rows) < limit:
            break

    return out

def _parse_workday_board(board_url: str) -> tuple[str, str, str, str, str]:
    """Return origin, tenant, site, locale, host from a Workday careers URL."""
    u = urllib.parse.urlparse(board_url)
    host = u.netloc
    origin = f"{u.scheme or 'https'}://{host}"
    tenant = host.split(".")[0]
    parts = [p for p in u.path.split("/") if p]
    locale = "en-US"
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        locale = parts.pop(0)
    site = parts[0] if parts else "External"
    return origin, tenant, site, locale, host

def _workday_posted_iso(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip().lower()
    now = now_utc()
    if "today" in t:
        return now.isoformat()
    if "yesterday" in t:
        return (now - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s+days?\s+ago", t)
    if m:
        return (now - timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s+hours?\s+ago", t)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).isoformat()
    return None

def workday_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None, *, title_terms: list[str] | None = None, search_text: str = "", progress=None, seniority_terms: list[str] | None = None) -> list[Job]:
    """Workday public CXS feed.

    The list endpoint is paged at exactly 20 records. To keep the 15-minute watch
    lightweight, full job details are fetched only for titles plausibly in the configured career lane.
    """
    cache = cache if cache is not None else {}
    origin, tenant, site, locale, _ = _parse_workday_board(board)
    endpoint = f"{origin}/wday/cxs/{tenant}/{site}/jobs"
    referer = f"{origin}/{locale}/{site}"
    offset = 0
    page_size = 20
    out: list[Job] = []
    total: int | None = None
    detail_failures = 0
    detail_skipped = 0

    while True:
        data = request_json_post(
            endpoint,
            {"appliedFacets": {}, "limit": page_size, "offset": offset, "searchText": search_text},
            referer=referer,
        )
        if total is None:
            try:
                total = int(data.get("total") or 0)
            except Exception:
                total = 0
        rows = data.get("jobPostings") or []
        if not rows:
            break

        for j in rows:
            title = j.get("title", "") or ""
            # Full detail pages are the expensive call. The title filter is intentionally
            # broad and includes all marketing/content/web/search/digital/experience titles.
            from .profiles import title_matches
            if not (title_matches(title, title_terms) if title_terms is not None else title_might_be_relevant(title)):
                continue

            ext = j.get("externalPath") or ""
            if not ext:
                continue
            detail_url = f"{origin}/wday/cxs/{tenant}/{site}{ext}"
            public_url = f"{origin}/{locale}/{site}{ext}"
            cached = cache.get(detail_url) or {}

            from .profiles import seniority_matches
            if seniority_terms and not seniority_matches(title, seniority_terms):
                detail_skipped += 1
                info = {"location": j.get("locationsText") or "", "description": "",
                        "additional_locations": "", "employment_type": "", "remote_type": ""}
            elif cached.get("description") and cached.get("cache_version") == 2:
                info = cached
            else:
                try:
                    req = urllib.request.Request(detail_url, headers={
                        "User-Agent": UA,
                        "Accept": "application/json",
                        "Referer": referer,
                    })
                    with urllib.request.urlopen(req, timeout=30) as r:
                        detail_data = json.loads(r.read().decode("utf-8"))
                    ji = detail_data.get("jobPostingInfo") or detail_data
                    desc = strip_html(ji.get("jobDescription", "") or "")
                    add_locs = ji.get("additionalLocations") or []
                    if isinstance(add_locs, list):
                        add_locs_text = ", ".join(
                            (x.get("location") if isinstance(x, dict) else str(x))
                            for x in add_locs if x
                        )
                    else:
                        add_locs_text = str(add_locs)
                    info = {
                        "cache_version": 2,
                        "description": desc,
                        "location": ji.get("location") or j.get("locationsText") or "",
                        "additional_locations": add_locs_text,
                        "employment_type": ji.get("timeType") or "",
                        "remote_type": ji.get("remoteType") or "",
                        "req_id": ji.get("jobReqId") or "",
                    }
                    cache[detail_url] = info
                except Exception:
                    detail_failures += 1
                    info = {
                        "description": "",
                        "location": j.get("locationsText") or "",
                        "additional_locations": "",
                        "employment_type": "",
                        "remote_type": "",
                        "req_id": "",
                    }

            location = ", ".join(
                x for x in [info.get("location", ""), info.get("additional_locations", "")]
                if x
            )
            remote_type = info.get("remote_type", "") or ""
            workplace = "Hybrid" if has_term(remote_type, "hybrid") else "Remote" if (
                has_term(remote_type, "remote")
                or has_term(location, "remote")
            ) else remote_type

            jid = info.get("req_id") or ext.rsplit("_", 1)[-1] or ext
            out.append(Job(
                uid=f"workday:{tenant}:{site}:{jid}",
                company=company,
                source="workday",
                title=title,
                location=location or (j.get("locationsText") or ""),
                workplace=workplace,
                employment_type=info.get("employment_type", "") or "",
                description=info.get("description", "") or title,
                job_url=public_url,
                apply_url=public_url,
                published_at=_workday_posted_iso(j.get("postedOn")),
                first_seen_at=first_seen,
                compensation="",
            ))

        offset += len(rows)
        if progress:
            progress(f"{company}: inspected {offset}/{total or '?'} listings; {len(out)} title candidates")
        if len(rows) < page_size:
            break
        if total and offset >= total:
            break
        if offset >= 5000:  # defensive ceiling for huge tenants
            break

    if progress:
        progress(f"COVERAGE {company}: query={search_text or 'all'}; inspected={offset}; reported={total}; candidates={len(out)}; detail_failures={detail_failures}; detail_skipped_seniority={detail_skipped}")
        if total and offset < total:
            progress(f"WARNING {company}: incomplete listing coverage ({offset}/{total})")
    return out

def icims_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    """Monitor a public iCIMS career portal.

    iCIMS does not expose a reliable publication timestamp on the search listing, so
    first run establishes a baseline; subsequent newly appearing requisitions alert immediately.
    """
    cache = cache if cache is not None else {}
    base = board.rstrip("/")
    links: dict[str, str] = {}

    # Standard iCIMS pagination uses pr=0,1,2... .
    for pr in range(0, 30):
        search_url = f"{base}/jobs/search?ss=1&pr={pr}"
        page = request_text(search_url)
        parser = CareerLinkParser()
        parser.feed(page)
        found_this_page = 0
        for href, anchor in parser.links:
            if not re.search(r"/jobs/\d+/[^/]+/job(?:\?|$)", href):
                continue
            url = urllib.parse.urljoin(base, href)
            title = re.sub(r"^\s*Requisition\s+Title\s*", "", anchor, flags=re.I).strip()
            if not title:
                continue
            if url not in links:
                links[url] = title
                found_this_page += 1
        if found_this_page == 0:
            break

    out: list[Job] = []
    for url, title in links.items():
        cached = cache.get(url) or {}
        if cached.get("description"):
            desc = cached.get("description", "")
            location = cached.get("location", "")
            emp = cached.get("employment_type", "")
        else:
            detail_html = request_text(url)
            desc = strip_html(detail_html)

            location = ""
            m = re.search(r"Job\s+Locations?\s+(.{1,220}?)\s+Requisition\s+ID", desc, re.I)
            if m:
                location = re.sub(r"\s+", " ", m.group(1)).strip()

            # Conservative fallback when a portal renders location metadata oddly.
            # Local-region matching belongs in config, not in a source adapter.
            if not location:
                loc_markers = ["US-Remote", "Remote"]
                hits = [marker for marker in loc_markers if has_term(desc, marker)]
                location = " | ".join(hits[:2])

            emp = "Contract" if has_term(title + " " + desc[:3000], "contract") else ""
            cache[url] = {"description": desc, "location": location, "employment_type": emp}

        jid_m = re.search(r"/jobs/(\d+)/", url)
        jid = jid_m.group(1) if jid_m else url
        out.append(Job(
            uid=f"icims:{urllib.parse.urlparse(base).netloc}:{jid}",
            company=company,
            source="icims",
            title=title,
            location=location,
            workplace="Remote" if has_term(location + " " + desc[:2500], "remote") else "",
            employment_type=emp,
            description=desc,
            job_url=url,
            apply_url=url,
            published_at=None,
            first_seen_at=first_seen,
            compensation="",
        ))
    return out

def jobicy_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    """Latest USA-eligible remote roles from Jobicy's public API."""
    queries = ["seo", "content", "web", "digital", "marketing"]
    dedup: dict[str, dict[str, Any]] = {}
    for tag in queries:
        url = (
            f"{board}?count=200&geo=usa&tag={urllib.parse.quote(tag)}"
        )
        data = request_json(url)
        for j in data.get("jobs") or []:
            key = str(j.get("id") or j.get("url") or j.get("jobTitle") or "")
            if key:
                dedup[key] = j

    out: list[Job] = []
    for jid, j in dedup.items():
        title = j.get("jobTitle", "") or j.get("title", "") or ""
        employer = j.get("companyName", "") or "Jobicy"
        desc = strip_html(j.get("jobDescription", "") or j.get("jobExcerpt", "") or "")
        location = j.get("jobGeo", "") or "Remote - US"
        comp = ""
        lo, hi = j.get("annualSalaryMin"), j.get("annualSalaryMax")
        if lo or hi:
            comp = f"{j.get('salaryCurrency','USD')} {lo or ''}-{hi or ''}".strip("-")
        url = j.get("url", "") or ""
        out.append(Job(
            uid=f"jobicy:{jid}",
            company=employer,
            source="jobicy",
            title=title,
            location=location,
            workplace="Remote",
            employment_type=as_text(j.get("jobType", "")),
            description=desc,
            job_url=url,
            apply_url=url,
            published_at=j.get("pubDate"),
            first_seen_at=first_seen,
            compensation=comp,
        ))
    return out

def himalayas_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    """Keyword-focused recent US remote roles from Himalayas' public search API."""
    queries = ["web", "website", "seo", "content", "digital experience", "cms", "geo", "aeo"]
    dedup: dict[str, dict[str, Any]] = {}

    for q in queries:
        # Two pages per query catches the newest 40 without crawling the whole service.
        for page in (1, 2):
            params = urllib.parse.urlencode({
                "q": q,
                "country": "US",
                "sort": "recent",
                "page": page,
            })
            data = request_json(f"{board}?{params}")
            rows = data.get("jobs") or data.get("data") or []
            if not rows:
                break
            for j in rows:
                key = str(j.get("guid") or j.get("id") or j.get("applicationLink") or "")
                if key:
                    dedup[key] = j

    out: list[Job] = []
    for jid, j in dedup.items():
        restrictions = j.get("locationRestrictions") or j.get("locations") or []
        if isinstance(restrictions, list):
            loc = ", ".join(str(x) for x in restrictions if x)
        else:
            loc = str(restrictions or "")
        if not loc:
            loc = "Remote - US"

        lo, hi = j.get("minSalary"), j.get("maxSalary")
        comp = ""
        if lo or hi:
            comp = f"{j.get('currency','USD')} {lo or ''}-{hi or ''} {j.get('salaryPeriod','')}".strip()

        out.append(Job(
            uid=f"himalayas:{jid}",
            company=j.get("companyName", "") or "Himalayas",
            source="himalayas",
            title=j.get("title", "") or "",
            location=loc,
            workplace="Remote",
            employment_type=as_text(j.get("employmentType", "")),
            description=strip_html(j.get("description", "") or ""),
            job_url=j.get("url", "") or j.get("applicationLink", "") or "",
            apply_url=j.get("applicationLink", "") or j.get("url", "") or "",
            published_at=j.get("pubDate"),
            first_seen_at=first_seen,
            compensation=comp,
        ))
    return out

def wwr_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    """We Work Remotely public RSS feed."""
    root = ET.fromstring(request_xml(board))
    out: list[Job] = []

    for item in root.findall(".//item"):
        raw_title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link or raw_title).strip()
        desc = strip_html(item.findtext("description") or "")
        pub = (item.findtext("pubDate") or "").strip()
        pub_iso = None
        if pub:
            try:
                pub_iso = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
            except Exception:
                pub_iso = None

        # WWR usually formats titles as "Company: Role".
        if ":" in raw_title:
            employer, title = [x.strip() for x in raw_title.split(":", 1)]
        else:
            employer, title = "We Work Remotely", raw_title

        # Some feeds include custom region/category elements with namespaces.
        region = ""
        for child in item:
            local = child.tag.split("}")[-1].lower()
            if local in {"region", "location"} and (child.text or "").strip():
                region = (child.text or "").strip()
                break
        if not region:
            region = "Worldwide"

        out.append(Job(
            uid=f"wwr:{guid}",
            company=employer,
            source="wwr",
            title=title,
            location=region,
            workplace="Remote",
            employment_type="",
            description=desc,
            job_url=link,
            apply_url=link,
            published_at=pub_iso,
            first_seen_at=first_seen,
            compensation="",
        ))
    return out

class CareerLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.current_href = href
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href is not None:
            text = re.sub(r"\s+", " ", " ".join(self.current_text)).strip()
            self.links.append((self.current_href, text))
            self.current_href = None
            self.current_text = []

def title_might_be_relevant(title: str) -> bool:
    t = title or ""
    if has_any(t, list(TITLE_TERMS.keys())):
        return True
    # Generic marketing/brand/comms roles still merit description inspection.
    return has_any(t, ["marketing", "brand", "communications", "content", "web", "website",
                       "search", "editorial", "campaign", "experience", "digital", "cms"])

def stripe_careers_jobs(company: str, board: str, first_seen: str, cache: dict[str, Any] | None = None) -> list[Job]:
    """Stripe's public careers site can contain roles not surfaced by the board token.

    We parse listing links from the public careers page, then fetch/cache details only
    for titles that could plausibly match the career profile. This keeps the 15-minute watch cheap.
    """
    cache = cache if cache is not None else {}
    raw_html = request_text(board)
    parser = CareerLinkParser()
    parser.feed(raw_html)

    unique: dict[str, str] = {}
    for href, anchor_text in parser.links:
        if not re.search(r"/(?:careers|jobs)/listing/[^/]+/\d+", href):
            continue
        url = urllib.parse.urljoin("https://stripe.com", href)
        slug_match = re.search(r"/listing/([^/]+)/(\d+)", url)
        if not slug_match:
            continue
        slug, jid = slug_match.groups()
        # The slug is more reliable than the anchor text on Stripe's search page,
        # where link text can be shortened or wrapped in UI labels.
        slug_title = slug.replace("-", " ").title()
        title = anchor_text.strip() if len(anchor_text.strip().split()) >= 3 else slug_title
        if not title_might_be_relevant(title) and title_might_be_relevant(slug_title):
            title = slug_title
        if title_might_be_relevant(title):
            unique[url] = title

    out: list[Job] = []
    for url, title in unique.items():
        cached = cache.get(url) or {}
        if cached.get("description"):
            desc = cached.get("description", "")
            location = cached.get("location", "")
            emp = cached.get("employment_type", "")
        else:
            page = request_text(url)
            desc = strip_html(page)
            location = ""
            for marker in [
                "Remote in United States", "Remote in the United States",
                "Remote in the US", "Remote, United States", "United States (Remote)",
                "US Remote", "Remote US", "Remote in Canada",
                "Chicago", "New York", "Seattle", "South San Francisco", "Atlanta"
            ]:
                if has_term(desc, marker):
                    location = marker
                    break
            emp = "Full time" if has_term(desc, "Full time") else ""
            cache[url] = {"description": desc, "location": location, "employment_type": emp}

        jid_match = re.search(r"/(\d+)(?:\?.*)?$", url)
        jid = jid_match.group(1) if jid_match else url
        out.append(Job(
            uid=f"stripe_direct:{jid}",
            company=company,
            source="stripe_direct",
            title=title,
            location=location,
            workplace="Remote" if "remote" in location.lower() else "",
            employment_type=emp,
            description=desc,
            job_url=url,
            apply_url=url,
            published_at=None,
            first_seen_at=first_seen,
            compensation="",
        ))
    return out


SOURCE_FUNCS = {
    "ashby": ashby_jobs,
    "greenhouse": greenhouse_jobs,
    "lever": lever_jobs,
    "remoteok": remoteok_jobs,
    "stripe_careers": stripe_careers_jobs,
    "smartrecruiters": smartrecruiters_jobs,
    "workday": workday_jobs,
    "icims": icims_jobs,
    "jobicy": jobicy_jobs,
    "himalayas": himalayas_jobs,
    "wwr": wwr_jobs,
}
