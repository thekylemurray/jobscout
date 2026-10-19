import json
from copy import deepcopy

import pytest

from jobscout import sources
from jobscout.config import default_config, validate_config
from jobscout.desktop import write_config
from jobscout.models import Job
from jobscout.profiles import annual_usd, blank_profile
from jobscout.scoring import score_job


@pytest.fixture
def profile_config():
    c = default_config()
    p = blank_profile()
    p.update(name='Synthetic research leadership', title_terms=['clinical operations'],
             core_skills=['vaccines', 'budget', 'phase iii'], industry_terms=['biotech'],
             excluded_companies=['Excluded Corp'], excluded_title_terms=['sales', 'manufacturing'],
             review_terms=['PhD', 'MD'])
    c.update(profile=p, local_regions=['Example City'], salary_floor=150000, salary_target=180000)
    return c


def job(**changes):
    data = dict(uid='test', company='Example Biotech', source='manual',
                title='Director, Clinical Operations', location='Remote - United States', workplace='Remote',
                employment_type='Full time', description='Biotech vaccines phase III budget leadership.',
                job_url='https://example.com', apply_url='https://example.com',
                published_at=None, first_seen_at='2026-01-01T00:00:00Z', compensation='')
    data.update(changes)
    return Job(**data)


def test_profile_bypasses_web_lane_and_explains_unknowns(profile_config):
    j = score_job(job(), profile_config)
    assert j.eligible and j.fit_score >= 60
    assert any('salary unverified' in r for r in j.risks)
    assert any('home state' in r for r in j.risks)


@pytest.mark.parametrize('changes,reason', [
    ({'company': 'Excluded Corp'}, 'employer'),
    ({'title': 'Director of Sales, Clinical Operations'}, 'function'),
    ({'employment_type': ['Contract']}, 'contract'),
    ({'location': 'Boston, MA', 'workplace': 'Hybrid'}, 'outside'),
    ({'location': 'UK Remote'}, 'restricted'),
    ({'location': 'Charlotte, NC', 'workplace': 'On-site'}, 'outside'),
    ({'compensation': 'USD 100000–140000 annual base'}, 'salary'),
])
def test_profile_exclusions(profile_config, changes, reason):
    j = score_job(job(**changes), profile_config)
    assert not j.eligible and reason in j.veto_reason.lower()


def test_preferred_degree_and_overlapping_salary_are_reviewable(profile_config):
    j = score_job(job(description='Biotech vaccines. MPH accepted, PhD preferred.',
                      compensation='USD 140000–180000 annually'), profile_config)
    assert j.eligible
    assert any('PhD' in r for r in j.risks)
    assert any('overlaps' in r for r in j.risks)


def test_remote_word_in_description_cannot_rescue_hybrid(profile_config):
    j = score_job(job(location='Boston, MA', workplace='Hybrid (Remote & On-site)',
                      description='Biotech vaccines, remote teams worldwide.'), profile_config)
    assert not j.eligible


@pytest.mark.parametrize('text', ['$100k–120k', 'CAD 100000–120000 annual',
                                   'USD 100 hourly', 'USD 10000 monthly',
                                   'USD 100000 base plus 50000 bonus annually'])
def test_salary_ambiguity_never_becomes_hard_exclusion(text):
    assert annual_usd(text) is None


def test_explicit_salary_and_profile_validation(profile_config, tmp_path):
    assert annual_usd('USD 150k–180k annual base') == (150000, 180000)
    path = tmp_path / 'config.json'
    write_config(path, profile_config)
    original = path.read_text()
    bad = deepcopy(profile_config)
    bad['profile']['title_terms'] = []
    with pytest.raises(ValueError):
        write_config(path, bad)
    assert path.read_text() == original
    assert not validate_config(json.loads(original))


def test_workday_profile_filter_fetches_clinical_and_does_not_infer_remote(monkeypatch):
    payload = {'total': 1, 'jobPostings': [{'title': 'Director, Clinical Operations',
               'externalPath': '/job/example/Director_123', 'locationsText': 'Boston, MA'}]}
    monkeypatch.setattr(sources, 'request_json_post', lambda *a, **k: payload)
    url = 'https://example.wd1.myworkdayjobs.com/wday/cxs/example/careers/job/example/Director_123'
    cache = {url: dict(cache_version=2, description='Lead remote teams for vaccines', location='Boston, MA',
                      remote_type='Hybrid', employment_type='Full time')}
    args = ('Example', 'https://example.wd1.myworkdayjobs.com/en-US/careers', '2026-01-01', cache)
    assert sources.workday_jobs(*args) == []
    result = sources.workday_jobs(*args, title_terms=['clinical operations'])
    assert len(result) == 1 and result[0].workplace == 'Hybrid'


def test_head_of_and_title_punctuation(profile_config):
    p = profile_config['profile']
    p['seniority_terms'] = ['director']
    j = score_job(job(title='Head of Clinical-Operations'), profile_config)
    assert j.eligible
    assert any('verify scope' in x for x in j.risks)
    assert not score_job(job(title='Manager, Clinical Operations'), profile_config).eligible


def test_foreign_location_reason_includes_evidence(profile_config):
    j = score_job(job(location='China - Beijing', workplace=''), profile_config)
    assert not j.eligible and 'Beijing' in j.veto_reason


def test_scan_report_includes_exclusions(tmp_path, monkeypatch, profile_config):
    from jobscout.app import run_once
    from jobscout.paths import RuntimePaths
    profile_config['boards'] = [{'company': 'Example', 'source': 'greenhouse', 'board': 'example'}]
    monkeypatch.setitem(sources.SOURCE_FUNCS, 'greenhouse', lambda *a: [job(location='Boston', workplace='Hybrid')])
    write_config(tmp_path/'config.json', profile_config)
    run_once(RuntimePaths.from_home(tmp_path), quiet=True)
    report = (tmp_path/'output'/'scan-report.html').read_text()
    assert 'Boston' in report and 'SOURCE_HEALTH OK 1 / FAIL 0' in report


def test_salary_extraction_requires_annual_base_and_usd():
    from jobscout.profiles import salary_from_description
    assert salary_from_description('The annual base salary is listed. Pay transparency $225,000 - $240,000 USD') == 'USD 225,000-240,000 annual base'
    assert salary_from_description('Annual bonus $25,000-$40,000 USD') == ''
    assert salary_from_description('Annual base salary CAD 225000-240000') == ''
