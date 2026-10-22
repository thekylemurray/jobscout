"""Auditable requirement matching against optional, locally stored career evidence.

Neither a keyword in a job description nor an absent résumé keyword proves
qualification. Profile gaps are explicit user assertions, not model guesses.
"""
from __future__ import annotations

import re
from typing import Any

from .utils import extract_sections, has_meaningful_term

# Purposefully conservative: job descriptions mention many tools incidentally.
# Categories are normalized and reusable across candidates and industries.
PATTERNS: dict[str, tuple[str, ...]] = {
    "sitecore": (r"\bsitecore\b",),
    "sanity": (r"\bsanity(?:\.io|\s+cms)?\b",),
    "wordpress": (r"\bwordpress\b",),
    "adobe experience manager": (r"\badobe experience manager\b", r"\bAEM\b"),
    "drupal": (r"\bdrupal\b",),
    "contentful": (r"\bcontentful\b",),
    "webflow": (r"\bwebflow\b",),
    "headless cms": (r"\bheadless\s+(?:cms|content management)\b",),
    "cms publishing": (r"\b(?:cms|content management system)\s+(?:publishing|authoring)\b",
                       r"\bweb(?:site)?\s+publishing\b", r"\bpublishing workflows?\b"),
    "cms migration": (r"\b(?:cms|web(?:site)?|site|content|platform)\s+migrations?\b",
                      r"\breplatform(?:ing)?\b", r"\bsitecore\s+\d+\s+to\s+\d+\b"),
    "web qa": (r"\b(?:website|web|release|content)\s+(?:qa|quality assurance)\b",
               r"\buser acceptance testing\b", r"\bUAT\b", r"\blaunch validation\b"),
    "seo": (r"\bsearch engine optimization\b", r"\bSEO\b", r"\borganic search\b"),
    "technical seo": (r"\btechnical SEO\b", r"\btechnical search (?:engine )?optimization\b",),
    "aeo/geo": (r"\banswer engine optimization\b", r"\bgenerative engine optimization\b",
                r"\bAEO\b", r"\bGEO\b"),
    "analytics": (r"\bweb analytics\b", r"\bdigital analytics\b", r"\b(?:matomo|piwik)\b",),
    "google analytics": (r"\bgoogle analytics\b", r"\bGA4\b",),
    "accessibility": (r"\b(?:WCAG|web accessibility|accessibility compliance)\b",),
    "figma": (r"\bfigma\b",),
    "jira": (r"\bjira\b",),
    "workfront": (r"\bworkfront\b",),
    "html/css": (r"\bhtml\s*(?:and|/|&)\s*css\b", r"\bhtml5\b", r"\bcss3\b"),
    "stakeholder coordination": (r"\bcross.functional\s+(?:coordination|collaboration)\b",
                                 r"\b(?:marketing|content)\s+(?:and|to|with)\s+engineering\b",
                                 r"\bstakeholder management\b"),
    "content governance": (r"\bcontent governance\b", r"\bcontent standards\b",
                           r"\bcontent lifecycle\b",),
    "structured content": (r"\bstructured content\b", r"\bcontent modeling\b",
                           r"\bcontent models?\b",),
    "roadmap ownership": (r"\b(?:own|manage|lead|set|drive)\s+(?:the\s+|a\s+)?(?:website|web|digital)?\s*roadmaps?\b",),
    "people management": (r"\b(?:direct reports?|people management|personnel management)\b",
                          r"\b(?:manage|supervise|mentor|hire|lead)\s+(?:a\s+|the\s+)?(?:team of \d+|staff|employees|people)\b",
                          r"\bperformance reviews?\s+(?:for|of)\s+(?:employees|staff|direct reports)\b"),
    "budget ownership": (r"\b(?:own|manage|oversee|control)\s+(?:the\s+|a\s+)?(?:annual\s+|departmental\s+|marketing\s+|web\s+)?budget\b",
                         r"\bbudget ownership\b",),
    "paid media": (r"\b(?:paid media|paid search|PPC|media buying|paid social)\b",),
    "account management": (r"\b(?:client|customer)\s+account management\b",
                           r"\b(?:manage|own)\s+(?:client\s+|customer\s+)?accounts\b",
                           r"\bclient relationship management\b",),
    "software development": (r"\b(?:full.stack|back.end|front.end)\s+(?:software\s+)?development\b",
                             r"\bwrite production code\b", r"\bsoftware engineering\b",),
    "marketing automation": (r"\bmarketing automation\b", r"\bmarketo\b",
                             r"\bpardot\b",),
    "salesforce marketing cloud": (r"\bsalesforce marketing cloud\b",),
    "hubspot": (r"\bhubspot\b",),
    "seo platforms": (r"\b(?:semrush|ahrefs|conductor|screaming frog)\b",),
}

_SECTIONS = ("required", "responsibilities", "preferred", "general")
_IMPORTANCE = {"required": "Required", "responsibilities": "Responsibility",
               "preferred": "Preferred", "general": "Mentioned"}
_STATUS = {"demonstrated": "Demonstrated", "transferable": "Transferable",
           "not_demonstrated": "Not demonstrated", "unassessed": "Unassessed"}


def validate_candidate_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["candidate_evidence.json must contain a JSON object"]
    errors: list[str] = []
    seen: dict[str, str] = {}
    for field in ("demonstrated", "transferable", "not_demonstrated"):
        entries = evidence.get(field, [])
        if not isinstance(entries, list) or not all(isinstance(x, str) for x in entries):
            errors.append(f"{field} must be a list of requirement category strings")
            continue
        for raw in entries:
            key = raw.strip().lower()
            if key not in PATTERNS:
                errors.append(f"unknown candidate evidence category: {raw}")
            if key in seen:
                errors.append(f"{raw} appears in both {seen[key]} and {field}")
            seen[key] = field
    return errors


def _matches(text: str, label: str) -> bool:
    if label == "aeo/geo":
        # GEO can mean geography; only count it in search/AI context.
        return bool(re.search(r"\banswer engine optimization\b|\bgenerative engine optimization\b|\bAEO\b",
                              text, re.I) or has_meaningful_term(text, "geo"))
    return any(re.search(pattern, text, re.I) for pattern in PATTERNS[label])


def assess_requirements(description: str, evidence: dict | None = None
                        ) -> tuple[list[dict[str, str]], str, list[str], int]:
    """Return requirements, required-coverage explanation, gaps and scoring adjustment.

    Only an explicit not_demonstrated assertion can cause a negative skill score.
    Unknown requirements remain Unassessed and do not silently become disqualifiers.
    """
    chunks = extract_sections(description or "")
    supplied = evidence is not None
    evidence = evidence or {}
    asserted = {
        category: {str(x).strip().lower() for x in evidence.get(category, [])}
        for category in ("demonstrated", "transferable", "not_demonstrated")
    }
    findings: list[dict[str, str]] = []
    for label in PATTERNS:
        section = next((s for s in _SECTIONS if _matches(chunks.get(s, ""), label)), None)
        if not section:
            continue
        status = next((name for name in ("demonstrated", "transferable", "not_demonstrated")
                       if label in asserted[name]), "unassessed")
        findings.append({
            "requirement": label,
            "importance": _IMPORTANCE[section],
            "assessment": _STATUS[status] if supplied else "Not assessed (no local profile)",
        })

    required = [f for f in findings if f["importance"] == "Required"]
    counts = {v: sum(f["assessment"] == v for f in required) for v in _STATUS.values()}
    if not supplied:
        coverage = f"{len(required)} explicit requirement categories detected; personal evidence not configured"
    elif required:
        coverage = (f"{counts['Demonstrated']} demonstrated, {counts['Transferable']} transferable, "
                    f"{counts['Not demonstrated']} not demonstrated, "
                    f"{counts['Unassessed']} unassessed / {len(required)} required")
    else:
        coverage = "No explicit required categories recognized; manual review needed"

    gaps = [f["requirement"] for f in required if f["assessment"] == "Not demonstrated"]
    # Modest bonuses for positive documented evidence, meaningful but bounded gaps.
    plus = min(8, counts["Demonstrated"] * 2 + counts["Transferable"])
    minus = min(24, len(gaps) * 8)
    return findings, coverage, gaps, plus - minus


def role_scope(title: str, requirements: list[dict[str, str]]) -> tuple[int | None, list[str]]:
    """Apply scope caps after keyword scoring, before any alert decision."""
    t = title.lower()
    flags: list[str] = []
    caps: list[int] = []
    if re.search(r"\b(?:vice president|vp|chief digital officer|chief marketing officer)\b", t):
        caps.append(58)
        flags.append("Executive-level scope requires review")
    if re.search(r"\b(?:senior|sr\.?)\s+director\b", t):
        caps.append(62)
        flags.append("Senior-director scope beyond target career lane")
    elif re.search(r"\bdirector\b", t):
        caps.append(72)
        flags.append("Director-level people and program ownership must be verified")
    if re.search(r"(^|[,/ ]+)head of\b|\bhead,\s*", t):
        caps.append(68)
        flags.append("Head-of-function leadership scope requires verification")
    if re.search(r"\baccount manager\b|\baccount management\b", t):
        caps.append(72)
        flags.append("Client account ownership may outweigh hands-on web/search work")
    if re.search(r"\bcreative design\b|\bvisual design\b", t):
        caps.append(68)
        flags.append("Creative design appears central to the role")
    if re.search(r"\b(?:developer|development engineer)\b", t):
        caps.append(62)
        flags.append("Hands-on development ownership may be outside web production")
    if re.search(r"\b(?:performance marketing|performance\s*&\s*seo)\b", t):
        caps.append(73)
        flags.append("Performance-marketing specialization needs closer review")

    people = [f for f in requirements
              if f["requirement"] == "people management" and
              f["importance"] in {"Required", "Responsibility"}]
    if people:
        if people[0]["assessment"] != "Demonstrated":
            caps.append(69)
        flags.append("Explicit personnel management duties; verify direct-report experience")
    return (min(caps) if caps else None), list(dict.fromkeys(flags))
