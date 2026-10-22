from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .rules import (
    CANDIDATE_HEADINGS, COMPANY_ALIASES, PREFERRED_HEADINGS, REQUIRED_HEADINGS,
    RESPONSIBILITY_HEADINGS, ROLE_LANES,
)

_TERM_CACHE: dict[str, re.Pattern[str]] = {}

def parse_dt(value: str | int | float | None) -> datetime | None:
    """Parse ISO-8601, Unix seconds, or Unix milliseconds into UTC.

    Several job aggregators expose numeric publication timestamps while direct ATS
    feeds usually return ISO strings. Normalizing both here keeps freshness logic
    source-agnostic.
    """
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?", value.strip())):
            numeric = float(value)
            if numeric > 10_000_000_000:  # milliseconds
                numeric /= 1000.0
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso_now() -> str:
    return now_utc().isoformat()

def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def _term_pattern(term: str) -> re.Pattern[str]:
    # Treat spaces flexibly, but require alphanumeric boundaries around the phrase.
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.I)

def as_text(value: Any) -> str:
    """Normalize inconsistent ATS field types into safe text.

    Public job APIs are not consistent: a field such as employment type, location,
    or tags may be a string on one posting and a list/dict on another. Matching
    should never crash because an upstream API changed shape.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " ".join(as_text(v) for v in value if v is not None)
    if isinstance(value, dict):
        return " ".join(as_text(v) for v in value.values() if v is not None)
    return str(value)

def has_term(text: Any, term: str) -> bool:
    if term not in _TERM_CACHE:
        _TERM_CACHE[term] = _term_pattern(term)
    return bool(_TERM_CACHE[term].search(as_text(text)))

def _context_window(text: str, match: re.Match[str], radius: int = 140) -> str:
    lo = max(0, match.start() - radius)
    hi = min(len(text), match.end() + radius)
    return text[lo:hi].lower()

def has_meaningful_term(text: Any, term: str) -> bool:
    """Context-aware matching for ambiguous acronyms.

    GEO and CRO caused a disproportionate share of historical false positives. Exact
    token boundaries solved substring collisions, but an isolated acronym can still
    mean geography or Chief Revenue Officer. v0.8 requires surrounding career-lane
    evidence before those acronyms count.
    """
    raw = as_text(text)
    low = raw.lower()
    if term == "geo":
        if has_term(raw, "generative engine optimization"):
            return True
        pat = _term_pattern("geo")
        for m in pat.finditer(raw):
            w = _context_window(raw, m)
            good = has_any(w, ["seo", "aeo", "search", "content", "marketing", "llm", "generative", "ai"])
            bad = has_any(w, ["geospatial", "geographic", "geography", "territory planning", "mapping", "gis"])
            if good and not bad:
                return True
        return False
    if term == "cro":
        if has_term(raw, "conversion rate optimization"):
            return True
        pat = _term_pattern("cro")
        for m in pat.finditer(raw):
            w = _context_window(raw, m)
            good = has_any(w, ["conversion", "landing page", "website", "web", "ux", "experiment", "a/b test", "optimization"])
            bad = has_any(w, ["chief revenue officer", "revenue organization", "sales leadership", "sales org"])
            if good and not bad:
                return True
        return False
    return has_term(raw, term)

def matched_terms(text: Any, terms: list[str], *, contextual: bool = False) -> list[str]:
    matcher = has_meaningful_term if contextual else has_term
    return [t for t in terms if matcher(text, t)]

def has_any(text: Any, terms: list[str], *, contextual: bool = False) -> bool:
    matcher = has_meaningful_term if contextual else has_term
    return any(matcher(text, t) for t in terms)

def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

def canonical_company(value: str) -> str:
    s = normalize_key(value)
    # Keep meaningful company tokens while removing common legal suffixes that vary
    # between direct ATS and aggregator listings.
    toks = [t for t in s.split() if t not in {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "company", "co"}]
    canonical = " ".join(toks)
    return COMPANY_ALIASES.get(canonical, canonical)

def canonical_title_tokens(value: str) -> set[str]:
    s = normalize_key(value)
    synonyms = {"sr": "senior", "mgr": "manager", "website": "web"}
    stop = {"and", "the", "of", "for", "to", "a", "an"}
    return {synonyms.get(t, t) for t in s.split() if t not in stop}

def title_similarity(a: str, b: str) -> float:
    aa, bb = canonical_title_tokens(a), canonical_title_tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)

def extract_sections(description: str) -> dict[str, str]:
    """Approximate JD sections after HTML has been flattened to text.

    The source adapters intentionally normalize HTML, so section markup is not
    guaranteed. We look for common heading phrases and use the strongest available
    section; otherwise the entire description remains general evidence.
    """
    text = re.sub(r"\s+", " ", as_text(description)).strip()
    if not text:
        return {"required": "", "candidate": "", "preferred": "", "responsibilities": "", "general": ""}
    marks: list[tuple[int, int, str]] = []
    groups = [
        (REQUIRED_HEADINGS, "required"),
        (CANDIDATE_HEADINGS, "candidate"),
        (PREFERRED_HEADINGS, "preferred"),
        (RESPONSIBILITY_HEADINGS, "responsibilities"),
    ]
    for terms, label in groups:
        for term in terms:
            for m in _term_pattern(term).finditer(text):
                marks.append((m.start(), m.end(), label))
    # Select longest heading first at each position, then suppress nested hits:
    # "Qualifications" inside "Preferred Qualifications" must not flip the
    # latter into the required section.
    marks.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    headings: list[tuple[int, int, str]] = []
    last_end = -1
    for st, en, label in marks:
        if st < last_end:
            continue
        headings.append((st, en, label))
        last_end = en
    out = {"required": "", "candidate": "", "preferred": "", "responsibilities": "", "general": text}
    for i, (st, en, label) in enumerate(headings):
        nxt = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        chunk = text[en:nxt].strip(" :-–—")
        if len(chunk) >= 1:
            out[label] += (" " + chunk)
    return out

def classify_role(title: str, description: str) -> tuple[str, int, list[str]]:
    best_lane = "Adjacent / Unclear"
    best_score = 0
    best_evidence: list[str] = []
    for lane, title_terms, body_terms in ROLE_LANES:
        th = matched_terms(title, title_terms, contextual=True)
        bh = matched_terms(description, body_terms, contextual=True)
        raw = len(th) * 28 + min(35, len(bh) * 7)
        # A direct title match is much stronger evidence than body boilerplate.
        if th:
            confidence = min(100, 52 + (len(th) - 1) * 12 + min(24, len(bh) * 4))
        else:
            confidence = min(70, len(bh) * 10)
        if raw > best_score:
            best_score = raw
            best_lane = lane
            best_evidence = (th[:3] + bh[:3])
            best_confidence = confidence
    if best_score == 0:
        return "Adjacent / Unclear", 0, []
    return best_lane, int(best_confidence), best_evidence

def parse_compensation_bounds(text: str) -> tuple[float | None, float | None]:
    raw = as_text(text).lower().replace(",", "")
    nums = []
    for m in re.finditer(r"(?<!\d)(\d{2,6}(?:\.\d+)?)", raw):
        try:
            nums.append(float(m.group(1)))
        except ValueError:
            pass
    if not nums:
        return None, None
    hourly = any(x in raw for x in ["hour", "/hr", "hourly"])
    if hourly:
        nums = [n * 2080 for n in nums if n < 1000]
    else:
        # Ignore years and small incidental numbers.
        nums = [n for n in nums if n >= 10000]
    if not nums:
        return None, None
    return min(nums), max(nums)
