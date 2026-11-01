"""Release-candidate presentation regressions: fresh/older/adjacent groups.

The primary selection is purely presentation; it must not change eligibility,
candidate fit, priority, exported full results, or application alerts.
"""
import csv
from datetime import datetime, timedelta, timezone

from jobscout.app import render_html, write_outputs
from jobscout.config import default_config
from jobscout.models import Job
from jobscout.paths import RuntimePaths
from jobscout.profiles import blank_profile


def config():
    c = default_config()
    p = blank_profile()
    p.update(name="Synthetic handoff", title_terms=["program manager"],
             adjacent_title_terms=["sales operations manager"])
    c.update(profile=p, boards=[], local_regions=[], dashboard_threshold=52,
             dashboard_age_hours=336)
    return c


def job(uid, title, *, age, availability="Available", score=74, adjacent=False):
    j = Job(uid=uid, title=title, company="Synthetic",
            source="greenhouse", location="Remote United States", workplace="Remote",
            employment_type="Full time", description="Synthetic operations role",
            job_url=f"https://example.org/{uid}", apply_url=f"https://example.org/{uid}",
            first_seen_at=datetime.now(timezone.utc).isoformat(), published_at=None,
            compensation="USD 160000-180000 annual base")
    j.fit_score = score
    j.operational_alignment_score = min(96, score + (8 if adjacent else 0))
    j.qualification_adjustment = 0
    j.priority_score = max(0, score - 2)
    j.age_hours = age
    j.availability = availability
    j.availability_note = "Specific listing present at last check; applying not tested."
    j.reasons = ["synthetic title match"]
    j.risks = ["confirm Washington remote eligibility and base salary"]
    j.score_breakdown = ["synthetic scoring"]
    j.priority_reasons = ["synthetic ranking"]
    j.review_only = adjacent
    j.match_path = "adjacent review" if adjacent else "target"
    return j


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_recent_and_older_available_primary_are_separate(tmp_path):
    c = config()
    recent = job("recent", "Recent Program Manager", age=48)
    old = job("old", "Older Program Manager", age=1250)
    unverified = job("unverified", "Unverified Old Program Manager", age=1200,
                     availability="Unverified")
    closed = job("closed", "Closed Old Program Manager", age=1300,
                 availability="Closed")
    adjacent = job("adjacent", "Sales Operations Manager", age=1400, adjacent=True, score=60)
    low = job("low", "Low Score Program Manager", age=1100, score=42)

    all_jobs = [recent, old, unverified, closed, adjacent, low]
    scores_before = [(j.fit_score, j.priority_score, j.eligible) for j in all_jobs]
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    alerts = write_outputs(all_jobs, [], c, {}, paths)
    assert alerts == []
    assert [(j.fit_score, j.priority_score, j.eligible) for j in all_jobs] == scores_before

    html = paths.dashboard.read_text(encoding="utf-8")
    for heading in ["Primary matches — recent",
                    "Older primary matches — still listed",
                    "Adjacent — manual review"]:
        assert heading in html
    assert html.index("Primary matches — recent") < html.index("Older primary matches — still listed")
    assert html.index("Older primary matches — still listed") < html.index("Adjacent — manual review")
    assert "Recent Program Manager" in html
    assert "Older Program Manager" in html
    assert "Sales Operations Manager" in html
    assert "Unverified Old Program Manager" not in html
    assert "Closed Old Program Manager" not in html
    assert "Low Score Program Manager" not in html
    assert "were still listed when last checked" in html
    assert "accepting applications" in html

    visible = read_csv(paths.jobs_csv)
    assert {j["title"] for j in visible} == {
        "Recent Program Manager", "Older Program Manager", "Sales Operations Manager"}
    assert len(read_csv(paths.eligible_csv)) == len(all_jobs)
    assert [j["title"] for j in read_csv(paths.output_dir / "adjacent_review.csv")] == [
        "Sales Operations Manager"
    ]


def test_dashboard_shows_older_primary_without_fresh_roles(tmp_path):
    c = config()
    old = job("old_only", "Legacy Program Manager", age=5000)
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    write_outputs([old], [], c, {}, paths)
    html = paths.dashboard.read_text(encoding="utf-8")
    assert "Older primary matches — still listed" in html
    assert "Primary matches — recent</h2>" not in html


def test_dashboard_does_not_show_old_unverified_as_still_listed(tmp_path):
    c = config()
    old = job("u", "Unknown Age Program Manager", age=5000, availability="Unverified")
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    write_outputs([old], [], c, {}, paths)
    html = paths.dashboard.read_text(encoding="utf-8")
    assert "Older primary matches — still listed</h2>" not in html
    # Existing fallback still surfaces a candidate when no other options exist,
    # but it must not label its unverified availability as 'still listed'.
    assert "Unknown Age Program Manager" in html


def test_manual_portable_preview_keeps_review_status_groups():
    a = job("man", "Manual Program Manager", age=None, availability="Unverified")
    output = render_html([a], portable=True)
    assert "Needs verification" in output
    assert "Older primary matches — still listed" not in output


def test_legacy_dashboard_rendering_unchanged():
    a = job("legacy", "Legacy Listing", age=400)
    output = render_html([a], portable=False)
    assert "Older primary matches — still listed" not in output
