"""Portable, local-only search preferences; independent of the legacy web scorer."""
from __future__ import annotations

import re
from typing import Any

from .models import Job
from .utils import as_text, has_any, has_term, matched_terms, strip_html

LIST_FIELDS = (
    'title_terms', 'seniority_terms', 'core_skills', 'industry_terms', 'excluded_title_terms',
    'excluded_companies', 'preferred_companies', 'review_terms',
)


def blank_profile() -> dict[str, Any]:
    return dict(name='My search', **{key: [] for key in LIST_FIELDS},
                allow_contract=False, allow_remote=True)


def validate_profile(profile: Any) -> list[str]:
    if not isinstance(profile, dict):
        return ['profile must be an object']
    errors = []
    if not isinstance(profile.get('name'), str) or not profile['name'].strip():
        errors.append('profile name is required')
    for key in LIST_FIELDS:
        if not isinstance(profile.get(key), list) or any(
            not isinstance(x, str) or not x.strip() for x in profile.get(key, [])
        ):
            errors.append(f'{key} must be a list of nonempty text values')
    if not profile.get('title_terms'):
        errors.append('at least one target title is required')
    for key in ('allow_contract', 'allow_remote'):
        if not isinstance(profile.get(key), bool):
            errors.append(f'{key} must be true or false')
    if 'exclude_required_doctorate' in profile and not isinstance(profile['exclude_required_doctorate'], bool):
        errors.append('exclude_required_doctorate must be true or false')
    return errors


def required_doctorate(description: str) -> str:
    """Recognize explicit requirements only; keep alternatives for human review."""
    text = re.sub(r"\bPh\.?\s?D\.?", "PhD", description, flags=re.I)
    text = re.sub(r"\bM\.D\.", "MD", text, flags=re.I)
    degree = r"(?:doctoral(?:[- ]level)?(?: degree)?|doctorate|PhD|MD|medical degree|PharmD|PsyD)"
    for clause in re.split(r"[.!?;]\s+|\n", text):
        if re.search(r"preferred|desirable|not required|equivalent|bachelor|master|\bMPH\b|\bBS\b|\bBA\b|\bMS\b|\bRN\b", clause, re.I):
            continue
        if re.search(degree + r"[^.!?;]{0,100}\b(?:required|mandatory)\b", clause, re.I) or re.search(r"\b(?:requires|must (?:have|hold|possess))\b[^.!?;]{0,70}" + degree, clause, re.I):
            return clause.strip()[:300]
    return ''


def annual_usd(text: str) -> tuple[float, float] | None:
    """Only use explicit annual USD ranges, never infer currency or annualize."""
    text = text.lower().replace(',', '')
    if not re.search(r'\busd\b|us\$', text) or not re.search(r'annual|year|/yr', text):
        return None
    if re.search(r'hour|month|week|total|bonus|equity|stock', text):
        return None
    nums = [float(x) * (1000 if k else 1)
            for x, k in re.findall(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(k)?\b', text)]
    nums = [x for x in nums if x >= 10000]
    return (min(nums), max(nums)) if nums else None


def salary_from_description(description: str) -> str:
    """Extract only explicit USD ranges near an annual base-salary statement."""
    text = re.sub(r'\s+', ' ', description)
    amount = r'\$?\s*(\d{2,3}(?:,\d{3})?(?:\.\d+)?[kK]?)'
    pattern = re.compile(amount + r'\s*[-–—]\s*' + amount)
    for match in pattern.finditer(text):
        context = text[max(0, match.start()-600):match.end()+80]
        if not re.search(r'annual\s+base\s+salary', context, re.I):
            continue
        nearby = text[max(0, match.start()-30):match.end()+30]
        if not re.search(r'\bUSD\b|US\$', nearby, re.I):
            continue
        candidate = f'USD {match.group(1)}-{match.group(2)} annual base'
        if annual_usd(candidate):
            return candidate
    return ''


def title_matches(title: str, terms: list[str]) -> bool:
    def normalize(value):
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return has_any(normalize(title), [normalize(t) for t in terms])


def seniority_matches(title: str, terms: list[str]) -> bool:
    return not terms or has_any(title, terms) or (
        has_term(title, 'head of') and any(t.lower() == 'director' for t in terms)
    )


def profile_location(job: Job, config: dict[str, Any]) -> tuple[bool, str]:
    loc = as_text(job.location).lower()
    work = as_text(job.workplace).lower()
    if any(has_term(loc, x) for x in config.get('local_regions', []) if x):
        return True, 'configured local region; confirm office attendance'
    # Hybrid must never inherit remote eligibility from a remote keyword.
    if has_any(work + ' ' + loc, ['hybrid', 'on-site', 'onsite', 'on site']):
        return False, f'on-site or hybrid outside selected cities: {as_text(job.location)}'
    if not config['profile']['allow_remote']:
        return False, 'outside configured cities; remote disabled'
    if 'remote' not in work + ' ' + loc:
        return False, f'location outside selected cities; no explicit remote eligibility: {as_text(job.location) or "not provided"}'
    if has_any(loc, ['united states', 'usa', 'u.s.', 'us', 'worldwide', 'anywhere', 'global']):
        return True, 'remote; verify eligibility from your home state and any restrictions'
    if loc.strip() in ('', 'remote', 'fully remote'):
        return True, 'remote eligibility unspecified; verify permitted states/countries'
    return False, f'remote role restricted to another or unconfirmed location: {as_text(job.location)}'


def score_profile(job: Job, config: dict[str, Any]) -> Job:
    p = config['profile']
    title, desc = as_text(job.title), strip_html(strip_html(as_text(job.description)))
    job.reasons, job.risks, job.score_breakdown = [], [], []
    job.role_lane = p['name']
    job.fit_score = job.priority_score = 0
    job.eligible, job.veto_reason = True, ''

    def reject(reason):
        job.eligible = False
        job.veto_reason = reason
        job.risks.append(reason)
        job.score_breakdown.append('excluded: ' + reason)
        return job

    if any(has_term(job.company, x) for x in p['excluded_companies']):
        return reject('excluded employer')
    if has_any(title, p['excluded_title_terms']):
        return reject('excluded job function in title')
    if not title_matches(title, p['title_terms']):
        return reject('title outside selected career profile')
    if not seniority_matches(title, p['seniority_terms']):
        return reject(f'seniority outside selected levels ({", ".join(p["seniority_terms"])}): {title}')
    if not p['allow_contract'] and has_any(as_text(job.employment_type) + ' ' + title,
                                         ['contract', 'contractor', 'temporary', 'freelance', 'fixed term']):
        return reject('contract or temporary employment excluded')
    if p.get('exclude_required_doctorate'):
        evidence = required_doctorate(desc)
        if evidence:
            return reject('explicit required doctorate: ' + evidence)
    allowed, location_reason = profile_location(job, config)
    if not allowed:
        return reject(location_reason)
    job.risks.append(location_reason)
    if has_term(title, 'head of') and not has_any(title, p['seniority_terms']):
        job.risks.append('Head of may be Director-equivalent; verify scope and compensation')
    if not as_text(job.employment_type).strip():
        job.risks.append('employment type missing; confirm permanent employment')
    if p['industry_terms'] and not has_any(desc, p['industry_terms']):
        job.risks.append('industry not established from posting; verify employer sector')
    if not job.compensation:
        job.compensation = salary_from_description(desc)
    salary = annual_usd(as_text(job.compensation))
    if salary and salary[1] < config['salary_floor']:
        return reject('explicit annual USD salary range below minimum')
    if not salary:
        job.risks.append('annual USD base salary unverified; confirm compensation')
    elif salary[0] < config['salary_floor']:
        job.risks.append('salary range overlaps minimum; acceptable offer not assured')
    # Qualification matching is conservative: a degree mention can be preferred,
    # an alternative, or a requirement. Surface the clause rather than inventing eligibility.
    for term in matched_terms(desc, p['review_terms']):
        clauses = re.split(r'[\n.!?;]+', desc)
        evidence = next((x.strip() for x in clauses if has_term(x, term)), term)
        job.risks.append(f'review {term}: {evidence[:260]}')
    hits = matched_terms(desc, p['core_skills'])
    job.fit_score = min(96, 50 + 6 * len(hits))
    job.lane_confidence = 0  # portable matcher does not estimate lane confidence
    job.reasons = ['target title matched'] + [f'experience signal: {x}' for x in hits[:7]]
    job.score_breakdown = ['target title +50', f'{len(hits)} skill signals +{6 * len(hits)} (cap 96)']
    if any(has_term(job.company, x) for x in p['preferred_companies']):
        job.reasons.append('preferred employer')
    return job
