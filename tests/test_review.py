import json
import urllib.error
from dataclasses import replace

import pytest

from jobscout.models import Job
from jobscout.review import check_availability, review_status, verify_candidates


def posting(**kw):
    values = dict(uid='one', company='Example', source='greenhouse', title='Clinical Director',
                  location='Remote US', workplace='Remote', employment_type='Full time',
                  description='', job_url='https://example.org/jobs/1', apply_url='https://example.org/jobs/1',
                  published_at=None, first_seen_at='', compensation='', risks=[])
    return Job(**(values | kw))


class Response:
    def __init__(self, text, url='https://example.org/jobs/1'):
        self.text, self.url = text, url
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, *args): return self.text.encode()
    def geturl(self): return self.url


def test_successful_response_needs_specific_posting_evidence(monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: Response('<h1>Careers</h1>'))
    assert check_availability(posting()).availability == 'Unverified'
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: Response('<h1>Clinical Director</h1>Apply now'))
    j = check_availability(posting())
    assert j.availability == 'Available' and j.availability_checked_at
    assert review_status(j) == 'Worth reviewing'
    assert review_status(replace(j, risks=['Salary unknown'])) == 'Needs verification'


@pytest.mark.parametrize('code, expected', [(404, 'Closed'), (410, 'Closed'), (403, 'Unverified'), (429, 'Unverified'), (500, 'Unverified')])
def test_http_failure_classification(monkeypatch, code, expected):
    def fail(*a, **k): raise urllib.error.HTTPError('https://example.org/jobs/1', code, 'test', None, None)
    monkeypatch.setattr('urllib.request.urlopen', fail)
    assert check_availability(posting()).availability == expected


def test_timeout_and_generic_redirect_are_unverified(monkeypatch):
    def timeout(*a, **k): raise TimeoutError()
    monkeypatch.setattr('urllib.request.urlopen', timeout)
    assert check_availability(posting()).availability == 'Unverified'
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: Response('This job is no longer available', 'https://example.org/careers'))
    assert check_availability(posting()).availability == 'Unverified'


def test_closed_posting_removed_before_dashboard(monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: Response('This position has been filled'))
    jobs, rejected = verify_candidates([posting()], [])
    assert not jobs and review_status(rejected[0]) == 'Excluded'


def test_workday_uses_uncached_detail_endpoint(monkeypatch):
    urls = []
    def fetch(req, **kw):
        urls.append(req.full_url)
        return Response(json.dumps({'jobPostingInfo': {'title': 'Clinical Director', 'jobDescription': 'Study leadership'}}))
    monkeypatch.setattr('urllib.request.urlopen', fetch)
    j = posting(source='workday', apply_url='https://example.wd1.myworkdayjobs.com/en-US/Careers/job/Remote/Director_R123')
    assert check_availability(j).availability == 'Available'
    assert urls == ['https://example.wd1.myworkdayjobs.com/wday/cxs/example/Careers/job/Remote/Director_R123']


def test_high_score_does_not_hide_unresolved_requirements():
    j = posting(fit_score=96, priority_score=100, risks=['Required specialty unverified'], availability='Available')
    from jobscout.app import render_html
    page = render_html([j], portable=True)
    assert 'Needs verification' in page and 'Apply now' not in page
