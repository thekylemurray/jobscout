"""Local evidence integration and conservative alert regression tests."""
import json
from datetime import datetime, timezone

import pytest

from jobscout import app
from jobscout.models import Job
from jobscout.paths import RuntimePaths
from jobscout.utils import iso_now


def candidate(**kwargs):
    stamp = iso_now()
    base = dict(uid="phase2", company="Example", source="greenhouse",
                title="Director, Website Operations", location="Remote - US",
                workplace="Remote", employment_type="Full time",
                description="Required Qualifications: Sitecore and technical SEO. "
                            "Responsibilities: Website publishing and CMS migration.",
                job_url="https://example.org/jobs/phase2",
                apply_url="https://example.org/jobs/phase2", published_at=stamp,
                first_seen_at=stamp, compensation="")
    return Job(**(base | kwargs))


def test_candidate_profile_loaded_from_private_runtime_home(tmp_path, monkeypatch, config):
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    config["boards"] = []
    paths.config.write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "candidate_evidence.json").write_text(
        json.dumps({"demonstrated": ["sitecore"], "transferable": ["drupal"],
                    "not_demonstrated": []}), encoding="utf-8")
    seen = []
    def fake_fetch(conf, state, cache, log):
        seen.append(conf.get("_candidate_evidence"))
        return [], []
    monkeypatch.setattr(app, "fetch_all", fake_fetch)
    assert app.run_once(paths, quiet=True) == 0
    assert seen[0]["demonstrated"] == ["sitecore"]


def test_invalid_private_evidence_fails_loudly(tmp_path, config):
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    config["boards"] = []
    paths.config.write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "candidate_evidence.json").write_text(
        json.dumps({"demonstrated": ["sitecore"], "transferable": ["sitecore"]}),
        encoding="utf-8")
    with pytest.raises(ValueError, match="both demonstrated and transferable"):
        app.run_once(paths, quiet=True)


def test_fresh_verified_leadership_scope_does_not_alert_due_to_low_fit(tmp_path, config):
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    config.update(alert_threshold=82, min_alert_fit_score=75)
    state = {"jobs": {}, "requisitions": {}}
    role = candidate(fit_score=69, priority_score=95, fresh=True,
                     availability="Available", discovery_status="published")
    alerts = app.write_outputs([role], [], config, state, paths)
    assert alerts == []


def test_report_explains_required_evidence_and_scope(tmp_path, config):
    from jobscout.scoring import score_job, apply_freshness
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    role = candidate()
    config["_candidate_evidence"] = {
        "demonstrated": ["sitecore"],
        "transferable": [],
        "not_demonstrated": ["technical seo"],
    }
    score_job(role, config)
    apply_freshness(role, config, board_initialized=True, is_new=True)
    page = app.render_html([role])
    assert "Requirement evidence" in page
    assert "technical seo" in page
    assert "Director-level" in page
    state = {"jobs": {}, "requisitions": {}}
    app.write_outputs([role], [], config, state, paths)
    import csv
    with paths.eligible_csv.open(encoding="utf-8", newline="") as fp:
        row = next(csv.DictReader(fp))
    assert row["required_gaps"] == "technical seo"
    assert row["requirement_coverage"]
    assert "Director-level" in row["scope_flags"]



def test_doctor_confirms_valid_private_evidence(tmp_path, config, capsys):
    from jobscout.cli import _doctor
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    config["boards"] = []
    paths.config.write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "candidate_evidence.json").write_text(
        json.dumps({"demonstrated": ["sitecore"], "transferable": [],
                    "not_demonstrated": []}), encoding="utf-8")
    assert _doctor(paths) == 0
    assert "PASS local candidate evidence" in capsys.readouterr().out


def test_doctor_rejects_conflicting_private_evidence(tmp_path, config, capsys):
    from jobscout.cli import _doctor
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    config["boards"] = []
    paths.config.write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "candidate_evidence.json").write_text(
        json.dumps({"demonstrated": ["sitecore"], "transferable": ["sitecore"]}),
        encoding="utf-8")
    assert _doctor(paths) == 1
    assert "FAIL candidate evidence" in capsys.readouterr().out


def test_phase2_1_high_fit_needs_manual_review_before_alert_or_apply_now(tmp_path, config):
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    config.update(alert_threshold=82, min_alert_fit_score=75, dashboard_threshold=52)
    role = candidate(title="Senior Website Manager", fit_score=96, priority_score=98,
                     availability="Available", fresh=True,
                     discovery_status="published",
                     assessment_confidence="Low", qualification_review_required=True,
                     qualification_review_reasons=["High fit score but no explicit required skills identified"])
    state = {"jobs": {}, "requisitions": {}}
    alerts = app.write_outputs([role], [], config, state, paths)
    assert alerts == []
    page = paths.dashboard.read_text(encoding="utf-8")
    assert "Qualification review required" in page
    assert "Low assessment confidence" in page
    assert "Worth reviewing" in page
    assert "Apply now" not in page
    import csv
    with paths.eligible_csv.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["assessment_confidence"] == "Low"
    assert row["qualification_review_required"] == "True"
    assert "explicit required skills" in row["qualification_review_reasons"]


def test_phase2_1_clear_required_skills_still_allow_verified_alert(tmp_path, config):
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    config.update(alert_threshold=82, min_alert_fit_score=75)
    role = candidate(title="Senior Web Producer", fit_score=90, priority_score=95,
                     availability="Available", fresh=True,
                     discovery_status="published",
                     assessment_confidence="High", qualification_review_required=False,
                     qualification_review_reasons=[])
    state = {"jobs": {}, "requisitions": {}}
    alerts = app.write_outputs([role], [], config, state, paths)
    assert len(alerts) == 1
    assert len(app.write_outputs([role], [], config, state, paths)) == 0
