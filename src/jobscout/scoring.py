from __future__ import annotations

import re
from typing import Any

from .models import Job
from .requirements import assess_requirements, role_scope
from .trust import publication_basis
from .rules import (
    ADJACENT_OWNERSHIP_SIGNALS, AGGREGATOR_SOURCES, CORE_GROUPS, DIRECT_SOURCES,
    FOREIGN_MARKERS, HARD_VETO_TITLE_TERMS, HEAVY_ADJACENT_TERMS, REMOTE_US_MARKERS,
    RESCUE_TITLE_TERMS, TITLE_TERMS, TOO_SENIOR_TERMS, US_MARKERS,
)
from .utils import (
    _term_pattern, as_text, canonical_company, classify_role, extract_sections,
    has_any, has_meaningful_term, has_term, matched_terms, now_utc,
    parse_compensation_bounds, parse_dt, title_similarity,
)

def title_lane_score(title: str) -> tuple[int, list[str]]:
    t = title or ""
    best = 0
    hits: list[str] = []
    for term, pts in TITLE_TERMS.items():
        if has_meaningful_term(t, term):
            hits.append(term)
            best = max(best, pts)
    return best, hits

def title_veto(title: str) -> str:
    t = title or ""

    if has_any(t, ["web designer", "visual designer", "product designer", "brand designer",
                   "motion designer", "graphic designer"]) or has_term(t, "designer"):
        return "occupation outside target lane: design specialist"

    # A website/SEO term is not sufficient to rescue a full-stack/software engineer.
    if (re.search(r"\b(?:full[ -]?stack|back[ -]?end|front[ -]?end)\s+"
                  r"(?:software\s+)?(?:engineer|developer)\b", t, re.I)
            or has_any(t, ["software engineer", "software developer", "application developer"])):
        return "occupation outside target lane: software engineering"
    if re.search(r"\b(?:unpaid|internship|intern)\b", t, re.I):
        return "internship or unpaid role outside target seniority"

    if has_any(t, RESCUE_TITLE_TERMS, contextual=True):
        return ""
    hits = matched_terms(t, HARD_VETO_TITLE_TERMS)
    if hits:
        return f"occupation outside target lane: {hits[0]}"
    if has_term(t, "engineer") or has_term(t, "engineering"):
        return "engineering role without explicit web/content/search ownership"
    if has_term(t, "architect"):
        return "architecture role outside content/information architecture"
    return ""

def core_group_hits_by_section(description: str) -> list[tuple[int, str, list[str], str, float]]:
    sections = extract_sections(description)
    out: list[tuple[int, str, list[str], str, float]] = []
    for pts, label, terms in CORE_GROUPS:
        candidates: list[tuple[float, str, list[str]]] = []
        for section, factor in [("required", 1.0), ("responsibilities", 0.85), ("preferred", 0.60)]:
            hits = matched_terms(sections[section], terms, contextual=True)
            if hits:
                candidates.append((factor, section, hits))
        general_hits = matched_terms(sections["general"], terms, contextual=True)
        if general_hits:
            candidates.append((0.50, "general", general_hits))
        if candidates:
            factor, section, hits = max(candidates, key=lambda x: x[0])
            out.append((pts, label, hits, section, factor))
    return out

def region_status(job: Job, config: dict[str, Any]) -> tuple[bool, str]:
    loc = as_text(job.location).lower().strip()
    workplace = as_text(job.workplace).lower().strip()
    combined = f"{loc} {workplace}".strip()

    # Local Triangle / NC roles.
    if any(has_term(loc, r.lower()) for r in config.get("local_regions", [])):
        return True, "configured local region"

    # Explicit US-remote markers always win.
    if any(m in combined for m in REMOTE_US_MARKERS):
        return True, "US remote"

    # Global remote feeds frequently publish location as Worldwide/Anywhere.
    if combined in {"worldwide remote", "worldwide", "anywhere remote", "anywhere",
                    "global remote", "remote worldwide"}:
        return True, "worldwide remote"

    has_us = any(m in combined for m in US_MARKERS)
    foreign = [m for m in FOREIGN_MARKERS if m in combined]

    # If the structured ATS location explicitly names a foreign country/region and
    # does not also name the US, reject it. Do not let generic "remote" language in
    # the description turn "Pakistan - Remote" into a US-remote match.
    if loc and foreign and not has_us:
        return False, "remote/location restricted outside the US"

    # A structured US-wide location without a city is reasonable to review.
    if has_us and not foreign:
        if "remote" in combined:
            return True, "US remote"
        # Some Greenhouse boards simply publish "United States" for nationwide roles.
        if loc in {"united states", "usa", "us", "u.s."}:
            return True, "US-wide location"

    # Bare generic Remote can be reviewed only when the ATS did not name another country.
    if combined in {"remote", "remote -", "fully remote"} or (not loc and "remote" in workplace):
        return True, "remote location"

    # If the structured location is present and specific, trust it over prose in the
    # description. This avoids false positives from global boilerplate.
    if loc:
        return False, "location is outside configured geography"

    # Last-resort fallback only when ATS location metadata is missing.
    head = (job.description or "")[:6000].lower()
    if any(m in head for m in REMOTE_US_MARKERS):
        return True, "US remote (description)"

    return False, "location is outside configured geography"

def adjacent_specialization_strength(title: str, description: str, term: str) -> str:
    """Return ``core``, ``supporting`` or ``incidental`` for an adjacent specialty.

    v0.8 treated any mention of terms such as ecommerce or demand generation as if
    that specialty defined the role. That was too coarse: an AEO job serving
    ecommerce customers is not an ecommerce job. v0.8.1 requires title evidence,
    repeated ownership, or nearby ownership language before applying a fit penalty.
    """
    if has_term(title, term):
        return "core"

    sections = extract_sections(description)
    weighted_text = " ".join([sections.get("required", ""), sections.get("responsibilities", "")]).strip()
    if not weighted_text or not has_term(weighted_text, term):
        # Preferred/general mentions are useful as a watch item, but not enough to
        # subtract fit on their own.
        return "incidental" if has_term(description, term) else ""

    pat = _term_pattern(term)
    matches = list(pat.finditer(weighted_text))
    if len(matches) >= 2:
        return "core"
    for m in matches:
        # Judge ownership inside the local sentence/clause rather than a broad
        # character window. Otherwise nearby SEO phrases such as "optimization"
        # can incorrectly make an incidental ecommerce mention look central.
        left_candidates = [weighted_text.rfind(mark, 0, m.start()) for mark in [".", ";", "!", "?"]]
        left = max(left_candidates) + 1
        right_candidates = [weighted_text.find(mark, m.end()) for mark in [".", ";", "!", "?"]]
        right_candidates = [x for x in right_candidates if x >= 0]
        right = min(right_candidates) if right_candidates else len(weighted_text)
        clause = weighted_text[left:right].strip()
        if has_any(clause, ADJACENT_OWNERSHIP_SIGNALS):
            return "core"
    return "supporting"

def score_job(job: Job, config: dict[str, Any]) -> Job:
    title = as_text(job.title)
    description = as_text(job.description)
    text = f"{title}\n{description}"
    score = 10.0
    reasons: list[str] = []
    risks: list[str] = []
    breakdown: list[str] = ["baseline +10"]

    job.role_lane, job.lane_confidence, lane_evidence = classify_role(title, description)

    veto = title_veto(title)
    if veto:
        job.eligible = False
        job.veto_reason = veto
        job.fit_score = 0
        job.priority_score = 0
        job.reasons = []
        job.risks = [veto]
        job.score_breakdown = [f"veto: {veto}"]
        return job

    title_pts, title_hits = title_lane_score(title)
    if title_pts:
        score += title_pts
        reasons.append(f"title is directly in target lane ({job.role_lane})")
        breakdown.append(f"title lane +{title_pts}")

    groups = core_group_hits_by_section(description)
    for pts, label, hits, section, factor in groups:
        contribution = max(1, round(pts * factor))
        score += contribution
        suffix = "" if section == "general" else f" ({section})"
        reasons.append(f"{label}{suffix}: {', '.join(hits[:3])}")
        breakdown.append(f"{label} +{contribution} [{section}]")

    strong_group_count = sum(1 for pts, _, _, section, factor in groups if pts >= 10 and factor >= 0.5)
    explicit_title_lane = title_pts >= 15

    # Two-stage gate: the role needs either a genuine target-lane title or enough
    # coherent content evidence to classify into one of the configured lanes.
    broad_marketing_title = has_any(title, ["marketing", "brand", "communications", "campaign", "digital"])
    coherent_generic = (
        (strong_group_count >= 2 and job.lane_confidence >= 35)
        or (broad_marketing_title and strong_group_count >= 1 and len(groups) >= 3 and job.lane_confidence >= 20)
    )
    if not explicit_title_lane and not coherent_generic:
        job.eligible = False
        job.veto_reason = "insufficient coherent web/content/search signal for a generic title"
        job.fit_score = 0
        job.priority_score = 0
        job.reasons = reasons
        job.risks = [job.veto_reason]
        job.score_breakdown = breakdown + [f"veto: lane confidence {job.lane_confidence}%"]
        return job

    for term, penalty in HEAVY_ADJACENT_TERMS:
        strength = adjacent_specialization_strength(title, description, term)
        if strength == "core":
            score -= penalty
            risks.append(term)
            breakdown.append(f"adjacent specialization -{penalty}: {term} [core]")
        elif strength == "supporting":
            # A genuine responsibility, but not clearly the center of gravity. Keep
            # it visible without allowing one mention to dominate an otherwise
            # excellent web/search/content match.
            soft_penalty = max(4, round(penalty * 0.25))
            score -= soft_penalty
            risks.append(f"{term} (supporting)")
            breakdown.append(f"adjacent specialization -{soft_penalty}: {term} [supporting]")

    if has_term(title, "product manager") and not has_any(title, ["website", "web", "content", "cms"]):
        score -= 20
        risks.append("formal product-management ownership")
        breakdown.append("formal product management -20")

    if has_any(title, TOO_SENIOR_TERMS):
        score -= 35
        risks.append("above target leadership scope")
        breakdown.append("leadership scope -35")
    elif has_term(title, "director") and not has_any(title, ["associate director"]):
        score -= 18
        risks.append("director-level scope")
        breakdown.append("director scope -18")

    if has_any(title, ["senior", "sr", "lead", "manager"]):
        score += 4
        reasons.append("appropriate seniority band")
        breakdown.append("seniority +4")

    # Location remains a hard eligibility constraint but no longer inflates fit.
    loc_ok, loc_reason = region_status(job, config)
    if not loc_ok:
        job.eligible = False
        job.veto_reason = loc_reason
        job.fit_score = 0
        job.priority_score = 0
        job.reasons = reasons
        job.risks = [loc_reason]
        job.score_breakdown = breakdown + [f"veto: {loc_reason}"]
        return job

    if not explicit_title_lane:
        score = min(score, 76)
        risks.append("generic title; verify role ownership")
        breakdown.append("generic-title cap 76")

    # Requirement evidence stays separate from raw keyword relevance. Only user-
    # asserted not-demonstrated skills create skill penalties. Unassessed != missing.
    findings, coverage, gaps, evidence_adjustment = assess_requirements(
        description, config.get("_candidate_evidence"))
    job.requirements = findings
    job.requirement_coverage = coverage
    job.requirement_gaps = gaps
    score += evidence_adjustment
    if evidence_adjustment:
        breakdown.append(f"candidate evidence {evidence_adjustment:+d}")
    if gaps:
        risks.append("required skills explicitly not demonstrated: " + ", ".join(gaps[:3]))

    scope_cap, scope_flags = role_scope(title, findings)
    job.scope_flags = scope_flags
    if scope_flags:
        risks.extend(scope_flags)
    if scope_cap is not None:
        score = min(score, scope_cap)
        breakdown.append(f"role scope cap {scope_cap}")

    # Avoid fake 100% certainty from keyword density. A 96 is deliberately reserved
    # for an unusually complete match; most strong jobs should land in the 70s/80s.
    score = max(0, min(96, round(score)))
    job.fit_score = int(score)
    job.reasons = list(dict.fromkeys(reasons))[:8]
    # Surface occupational blockers before less important adjacent-specialty notes.
    job.risks = list(dict.fromkeys(scope_flags + risks))[:8]
    job.score_breakdown = (breakdown[:11] + breakdown[-3:] if len(breakdown) > 14 else breakdown)
    return job

def apply_freshness(job: Job, config: dict[str, Any], *, board_initialized: bool, is_new: bool) -> Job:
    pub = parse_dt(job.published_at)
    first = parse_dt(job.first_seen_at)

    job.publication_basis = publication_basis(job)
    if pub:
        job.discovery_status = "published"
        age = max(0.0, (now_utc() - pub).total_seconds() / 3600)
    elif board_initialized:
        job.discovery_status = "new" if is_new else "seen_before"
        age = None  # Discovery date is not evidence of posting date.
    else:
        job.discovery_status = "baseline"
        age = None

    job.age_hours = age
    if not job.eligible:
        job.priority_score = 0
        job.fresh = False
        return job

    priority = float(job.fit_score)
    why: list[str] = [f"fit {job.fit_score}"]

    if age is None:
        fresh_adj = -3
        why.append("unknown posting age -3")
    elif job.publication_basis == "relative_estimate":
        fresh_adj = 0
        why.append("relative posting-date estimate; no freshness bonus")
    elif job.publication_basis == "feed_timestamp" and age <= 24:
        fresh_adj = 2
        why.append("recent feed timestamp (original posting age unverified) +2")
    elif age <= 3:
        fresh_adj = 10
        why.append("posted ≤3h +10")
    elif age <= 12:
        fresh_adj = 7
        why.append("posted ≤12h +7")
    elif age <= 24:
        fresh_adj = 4
        why.append("posted today +4")
    elif age <= 72:
        fresh_adj = 0
        why.append("posted ≤3d +0")
    elif age <= 168:
        fresh_adj = -5
        why.append("posted 3–7d -5")
    else:
        fresh_adj = -10
        why.append("older than 7d -10")
    priority += fresh_adj

    if job.source in DIRECT_SOURCES:
        priority += 4
        why.append("direct employer source +4")
    elif job.source in AGGREGATOR_SOURCES:
        priority -= 2
        why.append("aggregator source -2")

    loc_ok, loc_reason = region_status(job, config)
    if loc_ok:
        if loc_reason == "configured local region":
            priority += 5
            why.append("configured local region +5")
        elif "US remote" in loc_reason:
            priority += 4
            why.append("US remote +4")
        elif "worldwide" in loc_reason:
            priority += 1
            why.append("worldwide remote +1")
        else:
            priority += 2
            why.append("remote +2")

    lo, hi = parse_compensation_bounds(job.compensation)
    floor = float(config.get("salary_floor", 75000))
    target = float(config.get("salary_target", 100000))
    if hi is not None and hi < floor:
        priority -= 7
        why.append(f"comp below ${floor:,.0f} floor -7")
    elif lo is not None and lo >= target:
        priority += 5
        why.append(f"comp starts ≥${target:,.0f} +5")
    elif hi is not None and hi >= target:
        priority += 2
        why.append(f"comp reaches ${target:,.0f} +2")

    if has_term(job.employment_type or "", "contract"):
        priority += float(config.get("contract_priority_bonus", 1))
        why.append("contract +1")

    job.priority_score = max(0, min(100, round(priority)))
    job.priority_reasons = why[:8]
    job.fresh = bool(age is not None and age <= config.get("max_alert_age_hours", 24) and job.publication_basis == "employer_timestamp")
    return job

def freshness_label(job: Job) -> str:
    if job.discovery_status == "baseline":
        return "BASELINE"
    if job.publication_basis in ("first_seen", "unknown"):
        return "DATE UNKNOWN"
    if job.publication_basis == "relative_estimate":
        return "ESTIMATED AGE"
    age = job.age_hours
    if age is None:
        return "NEWLY SEEN"
    if age <= 3:
        return "🔥 NOW"
    if age <= 12:
        return "NEW"
    if age <= 24:
        return "TODAY"
    if age <= 72:
        return "RECENT"
    return "OLDER"

def _record_rank(job: Job, config: dict[str, Any]) -> tuple[int, int, int, int]:
    direct = 1 if job.source in DIRECT_SOURCES else 0
    loc = 1 if region_status(job, config)[0] else 0
    published = 1 if job.published_at else 0
    return direct, loc, published, job.fit_score

def dedupe_jobs(jobs: list[Job], config: dict[str, Any]) -> list[Job]:
    """Merge cross-source duplicates while preferring authoritative employer ATS data."""
    groups: dict[str, list[Job]] = {}
    for j in jobs:
        groups.setdefault(canonical_company(j.company), []).append(j)

    out: list[Job] = []
    for _, company_jobs in groups.items():
        clusters: list[list[Job]] = []
        for job in company_jobs:
            placed = False
            for cluster in clusters:
                if title_similarity(job.title, cluster[0].title) >= 0.82:
                    cluster.append(job)
                    placed = True
                    break
            if not placed:
                clusters.append([job])
        for cluster in clusters:
            best = max(cluster, key=lambda j: _record_rank(j, config))
            sources = sorted({j.source for j in cluster if j.source != best.source})
            best.also_found_on = sources
            # Preserve the earliest trustworthy publication timestamp found anywhere.
            pubs = [(j, parse_dt(j.published_at)) for j in cluster if parse_dt(j.published_at)]
            if pubs and not best.published_at:
                # Don't present an aggregator or relative estimate as an ATS timestamp.
                origin, _ = sorted(pubs, key=lambda pair: (
                    {"employer_timestamp": 0, "feed_timestamp": 1, "relative_estimate": 2}.get(publication_basis(pair[0]), 3),
                    pair[1],
                ))[0]
                best.published_at = origin.published_at
                best.publication_basis = publication_basis(origin)
                apply_freshness(best, config, board_initialized=True, is_new=False)
            out.append(best)
    return out

def application_tier(job: Job) -> str:
    if job.priority_score >= 82 and job.fit_score >= 76:
        return "🔥 Apply now"
    if job.priority_score >= 70 and job.fit_score >= 66:
        return "🟢 Strong matches"
    if job.priority_score >= 58 and job.fit_score >= 55:
        return "🟡 Worth reviewing"
    return "🔵 Discovery"
