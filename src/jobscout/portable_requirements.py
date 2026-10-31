"""Auditable assessment of specialist requirements for portable candidate profiles.

Only explicit *required* evidence can affect fit. A capability absent from a
resume is not assumed absent from the candidate: unassessed stays reviewable.
"""
from __future__ import annotations

import re

# Deliberately narrow domain signals, not generic phrases such as "operations".
CAPABILITIES: dict[str, str] = {
    "hubspot_admin": r"\bHubSpot\b.{0,35}\b(?:administrat(?:ion|or)|workflows?|certif(?:ied|ication)|operations)\b|\bHubSpot administrator\b",
    "paid_media": r"\b(?:paid media|paid search|performance advertising|paid social|PPC|Google Ads|Meta Ads)\b",
    "data_annotation": r"\b(?:data annotat(?:ion|ing)|data labell?ing|training data|human feedback data|RLHF|taxonomy infrastructure)\b",
    "field_sales_revops": r"\b(?:field sales|sales forecasting|sales operations|revenue operations|revenue forecasting|quota planning|territory planning)\b",
    "partner_ecosystem": r"\b(?:partner economics|partner ecosystem|partner operations|partner programs|channel partners?|partner management platform|Impartner)\b",
    "platform_admin": r"\b(?:Salesforce|ServiceNow|SAP|Adobe Experience Cloud)\s+(?:administrator|admin|architect|developer)\b",
}
VALID_STATUSES = {"demonstrated", "transferable", "unassessed", "not_demonstrated"}
REQUIRED_INTRO = re.compile(
    r"\b(?:minimum|basic|required|must.have|you (?:have|bring|need)|we (?:require|need|expect)|"
    r"qualifications?|what you(?:'ll| will) need)\b", re.I
)
PREFERRED_INTRO = re.compile(r"\b(?:preferred|nice to have|bonus|desirable|a plus)\b", re.I)


def validate_evidence(profile):
    errors = []
    evidence = profile.get("capability_evidence", {})
    if not isinstance(evidence, dict):
        return ["capability_evidence must be an object"]
    for name, status in evidence.items():
        if name not in CAPABILITIES or status not in VALID_STATUSES:
            errors.append(f"capability_evidence.{name} must name a supported capability and evidence status")
    terms = profile.get("adjacent_title_terms", [])
    if not isinstance(terms, list) or any(not isinstance(s, str) or not s.strip() for s in terms):
        errors.append("adjacent_title_terms must be a list of nonempty text")
    return errors


def _required_context(description):
    """Collect explicit mandatory requirements, never preferred/responsibility text.

    Generic "qualifications" embedded in "preferred qualifications" must not be
    treated as a required section. Match longest headings and partition before
    considering individual qualification signals.
    """
    headings = re.compile(
        r"\b(?:preferred qualifications|preferred experience|nice to have|"
        r"required qualifications|minimum qualifications|basic qualifications|"
        r"what you'll need|what you need|what you bring|"
        r"responsibilities|what you'll do|what you will do|"
        r"requirements|qualifications)\b", re.I)
    marks = list(headings.finditer(description))
    required = []
    for i, mark in enumerate(marks):
        heading = mark.group().lower()
        if heading.startswith(("preferred", "nice ", "responsibilities", "what you'll do", "what you will do")):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(description)
        chunk = description[mark.end():end].lstrip(" :-–—")
        if chunk.strip():
            required.append(chunk)
    # Explicit statement-level mandates also work when the source has no sections.
    lines = re.split(r"(?:\n+|(?<=[.!?])\s+)", description)
    explicit = [line.strip() for line in lines
                if REQUIRED_INTRO.search(line) and not PREFERRED_INTRO.search(line)]
    return " ".join(required + explicit)


def assess_required_capabilities(description: str, profile: dict) -> tuple[list[str], int, list[str]]:
    """Return (review notes, bounded fit adjustment, transparent breakdown)."""
    text = _required_context(description)
    p = profile.get("capability_evidence", {})
    notes: list[str] = []
    breakdown: list[str] = []
    adjustment = 0
    for capability, pattern in CAPABILITIES.items():
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        status = p.get(capability, "unassessed")
        # Truncation preserves useful evidence without reproducing the entire posting.
        evidence = match.group(0).strip()[:120]
        if status == "demonstrated":
            breakdown.append(f"required specialty {capability}: demonstrated (+0)")
            continue
        points = {"transferable": -5, "unassessed": -9, "not_demonstrated": -15}[status]
        adjustment += points
        notes.append(f"required specialty {capability} ({status}); review: {evidence}")
        breakdown.append(f"required specialty {capability}: {status} ({points})")
    return notes, max(-24, adjustment), breakdown
