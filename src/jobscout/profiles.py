"""Portable, local-only search preferences; independent of the legacy web scorer."""
from __future__ import annotations

import re
from typing import Any

from .models import Job
from .utils import as_text, has_any, has_term, matched_terms

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
    return errors


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


def profile_location(job: Job, config: dict[str, Any]) -> tuple[bool, str]:
    loc = as_text(job.location).lower()
    work = as_text(job.workplace).lower()
    if any(has_term(loc, x) for x in config.get('local_regions', []) if x):
        return True, 'configured local region; confirm office attendance'
    # Hybrid must never inherit remote eligibility from a remote keyword.
    if has_any(work + ' ' + loc, ['hybrid', 'on-site', 'onsite', 'on site']):
        return False, 'on-site or hybrid location outside configured cities'
    if not config['profile']['allow_remote']:
        return False, 'outside configured cities; remote disabled'
    if 'remote' not in work + ' ' + loc:
        return False, 'location unclear or outside configured cities'
    if has_any(loc, ['united states', 'usa', 'u.s.', 'us', 'worldwide', 'anywhere', 'global']):
        return True, 'remote; verify eligibility from your home state and any restrictions'
    if loc.strip() in ('', 'remote', 'fully remote'):
        return True, 'remote eligibility unspecified; verify permitted states/countries'
    return False, 'remote role restricted to another or unconfirmed location'


def score_profile(job: Job, config: dict[str, Any]) -> Job:
    p = config['profile']
    title, desc = as_text(job.title), as_text(job.description)
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
    if not has_any(title, p['title_terms']):
        return reject('title outside selected career profile')
    if p['seniority_terms'] and not has_any(title, p['seniority_terms']):
        return reject('seniority outside selected levels')
    if not p['allow_contract'] and has_any(as_text(job.employment_type) + ' ' + title,
                                         ['contract', 'contractor', 'temporary', 'freelance', 'fixed term']):
        return reject('contract or temporary employment excluded')
    allowed, location_reason = profile_location(job, config)
    if not allowed:
        return reject(location_reason)
    job.risks.append(location_reason)
    if not as_text(job.employment_type).strip():
        job.risks.append('employment type missing; confirm permanent employment')
    if p['industry_terms'] and not has_any(desc, p['industry_terms']):
        job.risks.append('industry not established from posting; verify employer sector')
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
        job.risks.append(f'qualification to review: {term}')
    hits = matched_terms(desc, p['core_skills'])
    job.fit_score = min(96, 50 + 6 * len(hits))
    job.lane_confidence = 0  # portable matcher does not estimate lane confidence
    job.reasons = ['target title matched'] + [f'experience signal: {x}' for x in hits[:7]]
    job.score_breakdown = ['target title +50', f'{len(hits)} skill signals +{6 * len(hits)} (cap 96)']
    if any(has_term(job.company, x) for x in p['preferred_companies']):
        job.reasons.append('preferred employer')
    return job
