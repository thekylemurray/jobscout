"""Phase 1 trust regression checks: dead links, provenance, and requisition history."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from jobscout.models import Job
from jobscout.review import check_availability
from jobscout.scoring import apply_freshness
from jobscout.trust import reconcile_requisition, requisition_key, record_verification
from jobscout.utils import iso_now


def job(**extra):
    fields = dict(uid="workday:example:external:R-258549", company="Amgen",
                  source="workday", title="Web Manager", location="Remote - United States",
                  workplace="Remote", employment_type="Full time", description="website management",
                  job_url="https://example.myworkdayjobs.com/en-US/Careers/job/Remote/Web-Manager_R-258549",
                  apply_url="https://example.myworkdayjobs.com/en-US/Careers/job/Remote/Web-Manager_R-258549",
                  published_at=None, first_seen_at=iso_now(), compensation="")
    return Job(**(fields | extra))


def test_requisition_identity_ignores_workday_title_and_locale():
    first = job()
    second = job(uid="other", title="Manager, Website Operations",
                 job_url="https://example.myworkdayjobs.com/fr-FR/Careers/job/Remote/Manager-Website_R-258549",
                 apply_url="https://example.myworkdayjobs.com/fr-FR/Careers/job/Remote/Manager-Website_R-258549")
    assert requisition_key(first) == requisition_key(second)


def test_reposting_preserves_first_observation_and_alert_history():
    old = "2026-10-10T12:00:00+00:00"
    state = {"jobs": {}, "boards": {}}
    first = job(first_seen_at=old, published_at=old, publication_basis="relative_estimate")
    assert reconcile_requisition(first, state, seen_at=old)
    state["requisitions"][first.history_key]["alerted"] = True
    fresh_time = "2026-10-20T12:00:00+00:00"
    newer = job(uid="a-second-feed-id", published_at=fresh_time,
                publication_basis="relative_estimate")
    assert not reconcile_requisition(newer, state, seen_at=fresh_time)
    assert newer.first_seen_at == old
    assert newer.published_at == old
    assert newer.publication_basis == "relative_estimate"
    assert state["requisitions"][newer.history_key]["alerted"] is True


def test_relative_date_is_not_alert_fresh(config):
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    estimated = job(published_at=recent, publication_basis="relative_estimate")
    apply_freshness(estimated, config, board_initialized=True, is_new=True)
    assert estimated.age_hours < 24
    assert not estimated.fresh


def test_precise_employer_date_may_be_fresh(config):
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    exact = job(published_at=recent, publication_basis="employer_timestamp")
    apply_freshness(exact, config, board_initialized=True, is_new=True)
    assert exact.fresh


def test_amgen_style_withdrawn_page_is_closed(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args):
            return b"<html><h1>Job Not Found</h1><p>We are sorry this job post no longer exists. Luckily, we have other jobs.</p></html>"
        def geturl(self): return "https://example.org/job/123"
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kw: Response())
    j = job(source="greenhouse", job_url="https://example.org/job/123", apply_url="https://example.org/job/123")
    checked = check_availability(j)
    assert checked.availability == "Closed"
    state = {"requisitions": {}}
    record_verification(checked, state)
    assert state["requisitions"][requisition_key(checked)]["last_verification"] == "Closed"


def test_requisition_verification_only_records_checked_postings():
    state = {}
    j = job()
    reconcile_requisition(j, state)
    record_verification(j, state)
    assert "last_verification" not in state["requisitions"][j.history_key]
