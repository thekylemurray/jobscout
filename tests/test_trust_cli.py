"""Offline regressions for personal CLI application trust and freshness."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import urllib.error

from jobscout.app import write_outputs
from jobscout.models import Job
from jobscout.paths import RuntimePaths
from jobscout.scoring import apply_freshness
from jobscout.trust import observe_requisition, requisition_key
from jobscout.utils import iso_now
from jobscout.verification import check_application, select_verification_candidates


def posting(**kwargs):
    fields = dict(uid="workday:amgen:site:R-258549", company="Amgen", source="workday",
                  title="Web Manager", location="Remote - United States", workplace="Remote",
                  employment_type="Full time", description="Enterprise CMS website management",
                  job_url="https://amgen.wd5.myworkdayjobs.com/en-US/External/job/Remote/Web-Manager_R-258549",
                  apply_url="https://amgen.wd5.myworkdayjobs.com/en-US/External/job/Remote/Web-Manager_R-258549",
                  published_at=None, first_seen_at=iso_now(), compensation="")
    return Job(**(fields | kwargs))


class Response:
    def __init__(self, body, url):
        self.body, self.url = body, url
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, *args): return self.body.encode("utf-8")
    def geturl(self): return self.url


def test_identical_requisition_survives_title_change():
    first = posting()
    second = posting(title="Website Operations Manager",
                     job_url="https://amgen.wd5.myworkdayjobs.com/fr-FR/External/job/Remote/Website-Operations_R-258549")
    assert requisition_key(first) == requisition_key(second)


def test_old_requisition_remains_old_even_if_feed_republishes():
    state = {}
    older = posting(first_seen_at="2026-10-10T12:00:00Z",
                    published_at="2026-10-10T12:00:00Z")
    assert observe_requisition(older, state)
    state["requisitions"][older.history_key]["alerted"] = True
    newer = posting(uid="another-uid", published_at="2026-10-20T12:00:00Z")
    assert not observe_requisition(newer, state)
    assert newer.first_seen_at == older.first_seen_at
    assert newer.published_at == older.published_at
    assert state["requisitions"][newer.history_key]["alerted"]


def test_no_employer_date_does_not_mean_new_posting(config):
    j = posting()
    apply_freshness(j, config, board_initialized=True, is_new=True)
    assert j.age_hours is None
    assert j.publication_basis == "first_seen"
    assert not j.fresh


def test_workday_relative_date_cannot_trigger_strict_alert(config):
    one_hour = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    j = posting(published_at=one_hour)
    apply_freshness(j, config, board_initialized=True, is_new=True)
    assert j.age_hours is not None and j.age_hours < 24
    assert j.publication_basis == "relative_estimate"
    assert not j.fresh


def test_explicit_employer_date_is_eligible_for_recent_alert(config):
    one_hour = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    j = posting(source="greenhouse", published_at=one_hour)
    apply_freshness(j, config, board_initialized=True, is_new=True)
    assert j.fresh


def test_amgen_closed_html_is_detected(monkeypatch):
    url = "https://careers.amgen.com/en/job/web-manager"
    text = "<h1>Job Not Found</h1>We are sorry this job post no longer exists."
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(text, url))
    j = posting(job_url=url, apply_url=url)
    checked = check_application(j)
    assert checked.availability == "Closed"
    assert "unavailable" in checked.availability_note


def test_blocked_website_and_generic_redirect_remain_unverified(monkeypatch):
    url = "https://employer.org/jobs/web-manager"
    j = posting(job_url=url, apply_url=url)
    def forbidden(*args, **kwargs):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    assert check_application(j).availability == "Unverified"
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(
        "<h1>Careers</h1><p>Web Manager — Apply now</p>", "https://employer.org/careers"))
    assert check_application(j).availability == "Unverified"


def test_career_navigation_does_not_count_as_live_application(monkeypatch):
    url = "https://employer.org/jobs/web-manager"
    html = "<h1>Careers</h1><p>Web Manager</p><p>Apply now</p>"
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(html, url))
    assert check_application(posting(job_url=url, apply_url=url)).availability == "Unverified"


def test_employer_posting_with_matching_application_is_available(monkeypatch):
    url = "https://employer.org/jobs/web-manager"
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(
        "<h1>Web Manager</h1><form id='job_application'>Apply now</form>", url))
    j = posting(job_url=url, apply_url=url)
    assert check_application(j).availability == "Available"


def test_aggregator_requires_employer_application_check(monkeypatch):
    source_page = "https://remoteok.com/remote-jobs/web-manager"
    employer_page = "https://employer.org/jobs/web-manager"
    visits = []
    def fetch(req, **kwargs):
        visits.append(req.full_url)
        return Response("<h1>Web Manager</h1><button>Apply now</button>", req.full_url)
    monkeypatch.setattr("urllib.request.urlopen", fetch)
    j = posting(source="remoteok", job_url=source_page, apply_url=employer_page)
    assert check_application(j).availability == "Available"
    assert visits == [employer_page]
    only_aggregator = posting(source="remoteok", job_url=source_page, apply_url=source_page)
    assert check_application(only_aggregator).availability == "Unverified"


def test_alert_requires_verified_job_and_fresh_employer_date(config, tmp_path):
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=2)).isoformat()
    config.update(alert_threshold=0, dashboard_threshold=0, max_alert_age_hours=24)
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    base = posting(uid="new-greenhouse-1", source="greenhouse", published_at=recent,
                   first_seen_at=recent, publication_basis="employer_timestamp",
                   fit_score=90, priority_score=95, fresh=True,
                   discovery_status="published", availability="Unverified")
    unknown_state = {"jobs": {}, "requisitions": {}}
    observe_requisition(base, unknown_state)
    assert write_outputs([base], [], config, unknown_state, paths) == []
    active = replace(base, availability="Available")
    assert len(write_outputs([active], [], config, unknown_state, paths)) == 1
    assert write_outputs([active], [], config, unknown_state, paths) == []
    other = replace(active, uid="new-greenhouse-2", history_key=active.history_key)
    assert write_outputs([other], [], config, unknown_state, paths) == []


def test_verification_prioritizes_employer_sources_and_fit(config):
    config["verification_max_per_scan"] = 12
    config["dashboard_threshold"] = 52
    direct = [posting(uid=f"gh-{n}", source="greenhouse",
                      fit_score=75, priority_score=80, fresh=False)
              for n in range(20)]
    aggregator = [posting(uid=f"agg-{n}", source="himalayas",
                          fit_score=90, priority_score=99, fresh=False)
                  for n in range(20)]
    unrelated = [posting(uid="engineering", source="greenhouse",
                         fit_score=48, priority_score=63, fresh=True)]
    checked = select_verification_candidates(aggregator + direct + unrelated, config)
    assert len(checked) == 12
    assert sum(j.source == "greenhouse" for j in checked) == 9
    assert sum(j.source == "himalayas" for j in checked) == 3
    assert unrelated[0] not in checked


def test_verification_fills_unused_employer_quota(config):
    config["verification_max_per_scan"] = 8
    config["dashboard_threshold"] = 52
    direct = [posting(uid=f"direct-{n}", source="greenhouse",
                      fit_score=70, priority_score=75) for n in range(2)]
    aggregator = [posting(uid=f"agg-{n}", source="himalayas",
                          fit_score=80, priority_score=90) for n in range(20)]
    checked = select_verification_candidates(aggregator + direct, config)
    assert len(checked) == 8
    assert sum(j.source == "greenhouse" for j in checked) == 2
