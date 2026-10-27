"""v2.2.1 regressions: verified Workable requisitions, intermediary trust,
priority of questionable sources, and safe board migration.
"""
import json
import urllib.error
from datetime import datetime, timezone

from jobscout.cli import _repair_sources
from jobscout.models import Job
from jobscout.paths import RuntimePaths
from jobscout.scoring import apply_freshness
from jobscout.source_repairs import repair_sources
from jobscout.source_trust import is_intermediary, source_class
from jobscout.verification import (
    _structured_ats_endpoint, apply_trust_priority, check_application,
    select_verification_candidates
)


def posting(**kwargs):
    stamp = datetime.now(timezone.utc).isoformat()
    base = dict(uid="workable:example:AB123", company="Example", source="workable",
                title="Website Manager", location="Remote - US", workplace="Remote",
                employment_type="Full time",
                description="Sitecore, SEO, digital experience, web QA, CMS migration",
                job_url="https://apply.workable.com/example/j/AB123/",
                apply_url="https://apply.workable.com/example/j/AB123/apply/",
                published_at=stamp, publication_basis="employer_timestamp",
                first_seen_at=stamp, compensation="", fit_score=90,
                priority_score=95, fresh=True)
    return Job(**(base | kwargs))


class Response:
    def __init__(self, data, url):
        self.data = data
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, *args):
        return json.dumps(self.data).encode("utf-8")

    def geturl(self):
        return self.url


def test_workable_exact_account_shortcode_title_and_application(monkeypatch):
    url = "https://apply.workable.com/api/v1/widget/accounts/example?details=true"
    listing = {
        "shortcode": "AB123", "title": "Website Manager",
        "url": "https://apply.workable.com/example/j/AB123/apply/",
        "application_url": "https://apply.workable.com/example/j/AB123/",
        "published_on": "2026-10-20",
    }
    calls = []
    def fetch(req, **kw):
        calls.append(req.full_url)
        assert req.full_url == url
        return Response({"jobs": [listing]}, url)
    monkeypatch.setattr("urllib.request.urlopen", fetch)
    j = check_application(posting())
    assert j.availability == "Available"
    assert "Workable" in j.availability_note
    assert calls == [url]


def test_workable_global_shortcode_urls_confirmed_by_account_feed(monkeypatch):
    url = "https://apply.workable.com/api/v1/widget/accounts/example?details=true"
    listing = {
        "shortcode": "AB123", "title": "Website Manager",
        "url": "https://apply.workable.com/j/AB123",
        "application_url": "https://apply.workable.com/j/AB123/apply",
    }
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, **kw: Response({"jobs": [listing]}, url))
    result = check_application(posting(
        job_url="https://apply.workable.com/j/AB123",
        apply_url="https://apply.workable.com/j/AB123/apply"))
    assert result.availability == "Available"


def test_workable_same_title_different_shortcode_is_not_verified(monkeypatch):
    api = "https://apply.workable.com/api/v1/widget/accounts/example?details=true"
    original = "https://apply.workable.com/example/j/AB123/"
    def fetch(req, **kw):
        if req.full_url == api:
            return Response({"jobs": [{"shortcode": "ZZ999", "title": "Website Manager",
                                      "url": "https://apply.workable.com/example/j/ZZ999/"}]}, api)
        # Even a landing page mentioning Apply Now is not a matching job.
        return Response({"not": "html"}, original)
    monkeypatch.setattr("urllib.request.urlopen", fetch)
    assert check_application(posting()).availability != "Available"


def test_workable_rejects_cross_account_application_link(monkeypatch):
    api = "https://apply.workable.com/api/v1/widget/accounts/example?details=true"
    original = "https://apply.workable.com/example/j/AB123/"
    def fetch(req, **kw):
        if req.full_url == api:
            return Response({"jobs": [{"shortcode": "AB123", "title": "Website Manager",
                    "url": "https://apply.workable.com/other-company/j/AB123/"}]}, api)
        return Response({}, original)
    monkeypatch.setattr("urllib.request.urlopen", fetch)
    assert check_application(posting()).availability != "Available"


def test_workable_403_not_construed_as_closed(monkeypatch):
    api = "https://apply.workable.com/api/v1/widget/accounts/example?details=true"
    url = "https://apply.workable.com/example/j/AB123/"
    def forbidden(req, **kw):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", None, None)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    result = check_application(posting())
    assert result.availability == "Unverified"
    assert _structured_ats_endpoint(result) == api


def test_huzzle_is_intermediary_and_never_auto_verified(monkeypatch, config):
    j = posting(uid="workable:huzzle:Q123", company="Huzzle", intermediary=True,
                job_url="https://apply.workable.com/huzzle/j/Q123/",
                apply_url="https://apply.workable.com/huzzle/j/Q123/apply/")
    assert is_intermediary(j)
    assert source_class(j) == "Recruiting intermediary"
    assert j not in select_verification_candidates([j], config)
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch")))
    assert check_application(j).availability == "Unverified"
    apply_freshness(j, config, board_initialized=True, is_new=True)
    assert "direct employer source +4" not in j.priority_reasons
    assert any("intermediary" in s.lower() for s in j.priority_reasons)


def test_unverified_updated_aggregator_is_prioritized_below_verified_ats():
    feed = posting(uid="himalayas:123", company="Amgen", source="himalayas",
                   priority_score=100, fit_score=96,
                   publication_basis="feed_updated_timestamp",
                   availability="Unverified")
    employer = posting(uid="greenhouse:example:123", company="Example",
                       source="greenhouse", priority_score=82,
                       availability="Available")
    changed = apply_trust_priority([feed, employer], {}, [])
    assert changed[0].fit_score == 96
    assert changed[0].priority_score <= 56
    assert changed[1].priority_score == 82
    assert changed[1].priority_score > changed[0].priority_score


def test_old_closed_requisition_stays_cautioned_until_reverified():
    j = posting(uid="himalayas:old-123", source="himalayas",
                priority_score=96, history_key="amgen:old-123")
    history = {"requisitions": {"amgen:old-123": {"first_closed_at": "2026-10-21T00:00:00Z"}}}
    apply_trust_priority([j], history)
    assert j.priority_score == 40
    assert "previously confirmed closed" in "; ".join(j.priority_reasons)
    verified = posting(uid=j.uid, source=j.source, history_key=j.history_key,
                       priority_score=96, availability="Available")
    apply_trust_priority([verified], history)
    assert verified.priority_score == 96


def test_repair_migrates_only_exact_company_old_ats_and_keeps_flags():
    conf = {"boards": [
        {"company": "Amplitude", "source": "greenhouse", "board": "old-amplitude", "enabled": False},
        {"company": "Postman", "source": "greenhouse", "board": "postman", "enabled": True},
        {"company": "Huzzle", "source": "workable", "board": "huzzle", "enabled": True},
        {"company": "Other", "source": "greenhouse", "board": "other", "enabled": True},
    ], "salary_floor": 80000}
    changed, updates = repair_sources(conf)
    assert len(updates) == 2
    assert changed["boards"][0]["source"] == "ashby"
    assert changed["boards"][0]["board"] == "amplitude"
    assert changed["boards"][0]["enabled"] is False
    assert changed["boards"][1]["source"] == "workday"
    assert changed["boards"][1]["board"] == "https://postman.wd108.myworkdayjobs.com/careers"
    assert changed["boards"][2:] == conf["boards"][2:]
    assert conf["boards"][0]["source"] == "greenhouse"
    again, updates2 = repair_sources(changed)
    assert again == changed and updates2 == []


def test_repair_cli_dry_run_backup_idempotent_preserves_history(config, tmp_path):
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    config["boards"].append({
        "company": "Amplitude", "source": "greenhouse", "board": "amplitude-old",
        "enabled": False})
    config["boards"].append({
        "company": "Postman", "source": "greenhouse", "board": "postman",
        "enabled": True})
    paths.config.write_text(json.dumps(config), encoding="utf-8")
    paths.state.write_text('{"jobs":{"x":{"alerted":true}}}', encoding="utf-8")
    (tmp_path / "candidate_evidence.json").write_text('{"demonstrated":["sitecore"]}')
    before = paths.state.read_text()
    assert _repair_sources(paths, dry_run=True) == 0
    assert json.loads(paths.config.read_text()) == config
    assert _repair_sources(paths) == 0
    updated = json.loads(paths.config.read_text())
    assert len(updated["boards"]) == len(config["boards"])
    assert updated["boards"][-2]["source"] == "ashby"
    assert updated["boards"][-2]["enabled"] is False
    assert updated["boards"][-1]["source"] == "workday"
    assert paths.state.read_text() == before
    assert json.loads((tmp_path / "candidate_evidence.json").read_text()) == {
        "demonstrated": ["sitecore"]}
    assert len(list(tmp_path.glob("config.backup-*.json"))) == 1
    assert _repair_sources(paths) == 0
    assert len(list(tmp_path.glob("config.backup-*.json"))) == 1



def test_csv_output_writers_accept_source_class_for_rejected_and_near_miss(config, tmp_path):
    """Regression: real scan failed after successful fetch/score on CSV writerow."""
    import csv

    from jobscout.app import write_outputs

    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    good = posting(title="Website Manager", availability="Unverified",
                   fit_score=88, priority_score=64, discovery_status="baseline")
    # These both appear in rejected.csv; web title also in near_miss.csv.
    review = posting(uid="workable:huzzle:r1", company="Huzzle",
                     title="Web Content Writer Internship",
                     intermediary=True, fit_score=0, priority_score=0,
                     eligible=False, veto_reason="Internship outside target seniority")
    outside = posting(uid="workable:other:r2", company="Example",
                      title="Finance Officer", fit_score=0, priority_score=0,
                      eligible=False, veto_reason="Outside selected career lane")
    state = {"jobs": {}, "requisitions": {}}
    write_outputs([good], [review, outside], config, state, paths)

    for filename, expected_count in ((paths.eligible_csv, 1),
                                     (paths.jobs_csv, 1),
                                     (paths.near_miss_csv, 1),
                                     (paths.rejected_csv, 2)):
        with filename.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        assert len(rows) == expected_count, filename
        assert "source_class" in reader.fieldnames, filename
        assert all(row["source_class"] for row in rows)
        assert all(None not in row for row in rows)  # no surprise CSV keys
    with paths.near_miss_csv.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
        assert row["source_class"] == "Recruiting intermediary"
        assert row["source"] == "workable"
