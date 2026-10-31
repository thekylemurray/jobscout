"""Optional conservative eligibility checks for portable candidate profiles.

A confirmed violation is excluded; ambiguous language is kept for human review.
This module does not infer a hiring promise or eligibility from unknown metadata.
"""
from __future__ import annotations

import re
from typing import Any


STATE_CODES = {"washington": "WA"}


def validate_extended_profile(profile: dict[str, Any]) -> list[str]:
    errors = []
    for key in ("remote_only", "require_full_time", "exclude_people_management",
                "exclude_agencies", "exclude_required_platform_certifications"):
        if key in profile and not isinstance(profile[key], bool):
            errors.append(f"{key} must be true or false")
    state = profile.get("home_state")
    if state is not None and (not isinstance(state, str) or not state.strip()):
        errors.append("home_state must be nonempty text")
    travel = profile.get("max_travel_percent")
    if travel is not None and (isinstance(travel, bool) or not isinstance(travel, (int, float))
                               or not 0 <= travel <= 100):
        errors.append("max_travel_percent must be between 0 and 100")
    lanes = profile.get("career_lanes", [])
    if not isinstance(lanes, list):
        errors.append("career_lanes must be a list")
    else:
        for idx, lane in enumerate(lanes):
            if not isinstance(lane, dict) or not isinstance(lane.get("name"), str) or not lane["name"].strip():
                errors.append(f"career_lanes[{idx}].name must be text")
                continue
            for key in ("title_terms", "core_skills"):
                terms = lane.get(key)
                if not isinstance(terms, list) or any(not isinstance(t, str) or not t.strip() for t in terms):
                    errors.append(f"career_lanes[{idx}].{key} must be a list of nonempty text")
    return errors


def matching_lane(title: str, lanes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer the most specific matching title phrase; no substring word fragments."""
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    matches = []
    for index, lane in enumerate(lanes):
        for phrase in lane.get("title_terms", []):
            term = re.sub(r"[^a-z0-9]+", " ", phrase.lower()).strip()
            if term and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized):
                matches.append((len(term), -index, lane))
    return max(matches, key=lambda x: (x[0], x[1]))[2] if matches else None


def state_excluded(text: str, state: str) -> bool:
    code = STATE_CODES.get(state.lower(), state.strip().upper() if len(state.strip()) == 2 else "")
    names = [state.strip()]
    if code:
        names.append(code)
    state_re = r"(?:\b" + r"\b|\b".join(re.escape(n) for n in names) + r"\b)"
    snippets = re.split(r"[.\n;]", text)
    for snippet in snippets:
        if not re.search(state_re, snippet, re.I):
            continue
        # An explicit exclusion list may contain multiple states, e.g. "except CA, CO, WA, NY".
        if re.search(r"\b(?:excluding|except|not available in|not eligible in|not hiring in|cannot hire in|unable to hire in|ineligible in|excluded states?|not open to)\b.{0,160}" + state_re, snippet, re.I):
            return True
        if re.search(state_re + r".{0,60}\b(?:not eligible|excluded|ineligible)\b", snippet, re.I):
            return True
    return False


def _clauses(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[\n.;!?]+", text) if s.strip()]


def _nonnegated(clause: str) -> bool:
    return not re.search(r"\b(?:no direct reports|zero direct reports|without direct reports|no people management|no supervisory|not responsible for managing people|individual contributor with no)\b", clause, re.I)


def _people_management(text: str) -> bool:
    patterns = (
        r"\b(?:have|has|with|supervise|manage|managing|lead|leading|oversee)\s+(?:\w+\s+){0,5}direct reports?\b",
        r"\bdirect reports?\s*:\s*[1-9]\d*\b",
        r"\b(?:manage|supervise|hire|develop|lead)\s+(?:a |the )?(?:team of|staff of|group of)\s*\d+\b",
        r"\b(?:people management|line management|supervisory experience|personnel management)\s+(?:is\s+)?(?:required|mandatory|responsibility)\b",
        r"\bresponsib(?:le|ility)\s+for\s+(?:hiring|managing|supervising)\s+(?:employees|staff|direct reports)\b",
    )
    return any(_nonnegated(clause) and any(re.search(p, clause, re.I) for p in patterns)
               for clause in _clauses(text))


def _travel_percent(text: str) -> float | None:
    amounts = []
    for clause in _clauses(text):
        for pattern in (r"\btravel\b.{0,70}?\b(\d{1,3})\s*%",
                        r"\b(\d{1,3})\s*%\s*(?:domestic |international )?travel\b"):
            for m in re.finditer(pattern, clause, re.I):
                val = int(m.group(1))
                if val <= 100:
                    amounts.append(val)
    return max(amounts) if amounts else None


def constraint_result(job: Any, profile: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (confirmed exclusion reason, unresolved review notes)."""
    title = str(job.title or "")
    desc = str(job.description or "")
    loc = str(job.location or "")
    workplace = str(job.workplace or "")
    job_type = str(job.employment_type or "")
    text = desc + "\n" + loc + "\n" + workplace
    notes: list[str] = []

    if profile.get("remote_only"):
        if re.search(r"\b(?:hybrid|on.site|onsite)\b", workplace, re.I):
            return "remote-only requirement violated: hybrid/on-site work arrangement", notes
        if re.search(r"(?:must|required|expected)\s+(?:to\s+)?(?:work|be|come)\s+(?:in|at|on.site)\s+(?:the\s+)?office\b|\bin.office\s+(?:days?|attendance)\s+(?:required|expected)\b", desc, re.I):
            return "remote-only requirement violated: office attendance required", notes
        notes.append("verify fully remote status and absence of required office visits")

    if profile.get("home_state"):
        if state_excluded(text, profile["home_state"]):
            return f"employer explicitly excludes {profile['home_state']} from remote eligibility", notes
        notes.append(f"verify employer may hire remote employees residing in {profile['home_state']}")

    if profile.get("require_full_time"):
        if re.search(r"\b(?:part.time|internship|intern|1099|corp.to.corp|c2c|contract.to.hire|fixed.term|temporary|freelance)\b",
                     title + " " + job_type, re.I):
            return "permanent full-time employment requirement violated", notes
        if not re.search(r"\bfull.time\b", job_type, re.I):
            notes.append("verify permanent full-time employee status")

    if profile.get("exclude_people_management"):
        if _people_management(desc):
            return "explicit direct-report / people-management duties", notes
        notes.append("verify role has no direct reports or people-management obligations")

    ceiling = profile.get("max_travel_percent")
    if ceiling is not None:
        travel = _travel_percent(desc)
        if travel is not None and travel > ceiling:
            return f"advertised travel {travel:g}% exceeds permitted {ceiling:g}%", notes
        if travel is None and re.search(r"\b(?:frequent|regular|significant|extensive)\s+travel\b|\btravel\s+(?:frequently|regularly)\b", desc, re.I):
            notes.append("travel requirement unclear; verify percentage")

    if profile.get("exclude_agencies"):
        if re.search(r"\b(?:we are|we're|our company is|is a)\s+(?:an? )?(?:full.service |digital |creative |marketing |management )*(?:agency|consulting firm|consultancy)\b", desc[:1800], re.I):
            return "employer describes itself as an agency/consulting firm", notes
        notes.append("verify employer is not a consulting or agency business")

    if profile.get("exclude_required_platform_certifications"):
        if any(re.search(p, clause, re.I) for clause in _clauses(desc) for p in (
            r"\b(?:Salesforce|AWS|Azure|Google Cloud|SAP|ServiceNow|Adobe|Workday)\b.{0,75}\b(?:certification|certified)\b.{0,35}\b(?:required|mandatory|must have)\b",
            r"\b(?:required|must have|mandatory)\b.{0,55}\b(?:certified|certification)\b.{0,50}\b(?:architect|developer|administrator)\b",
        )):
            return "explicit mandatory platform-specific technical certification", notes
        notes.append("verify technical certification requirements; PMP is in progress")
    return "", notes
