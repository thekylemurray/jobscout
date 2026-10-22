"""Offline contracts for new public ATS and remote-RSS sources."""
import json
from pathlib import Path

import pytest

from jobscout import sources
from jobscout import sources_expansion as adapters
from jobscout.config import validate_config
from jobscout.expansion_catalog import EXPANSION_BOARDS, add_sources, planned_sources
from jobscout.paths import RuntimePaths
from jobscout.cli import _add_sources
from jobscout.rules import DIRECT_SOURCES, AGGREGATOR_SOURCES
from jobscout.trust import publication_basis
from jobscout.verification import _has_external_application, select_verification_candidates

SEEN = "2026-10-22T18:00:00Z"


def test_workable_adapter_uses_public_widget_and_correct_application_urls(monkeypatch):
    observed = []
    def fake_json(url):
        observed.append(url)
        return {"name": "Sample ATS", "jobs": [
            {"title": "Senior Website Manager", "shortcode": "AB123",
             "city": "Raleigh", "state": "North Carolina", "country": "United States",
             "telecommuting": True, "workplace_type": "remote",
             "employment_type": "Full time",
             "description": "<p>Sitecore, SEO and <b>web QA</b>.</p>",
             "url": "https://apply.workable.com/sample/j/AB123/apply/",
             "application_url": "https://apply.workable.com/sample/j/AB123/",
             "published_on": "2026-10-22T12:30:00Z"},
            {"title": "UX Architect", "shortcode": "XY567",
             "telecommuting": False, "workplace_type": "hybrid",
             "country": "United States",
             "application_url": "https://apply.workable.com/sample/j/XY567/"}
        ]}
    monkeypatch.setattr(adapters, "request_json", fake_json)
    jobs = sources.workable_jobs("Sample", "sample", SEEN)
    assert len(jobs) == 2
    assert observed == [
        "https://apply.workable.com/api/v1/widget/accounts/sample?details=true"]
    first = jobs[0]
    assert first.uid == "workable:sample:AB123"
    assert first.published_at == "2026-10-22T12:30:00Z"
    assert first.publication_basis == "employer_timestamp"
    assert first.location.startswith("Remote - Raleigh")
    assert first.workplace == "Remote"
    assert first.description.replace(" .", ".") == "Sitecore, SEO and web QA."
    assert first.job_url.endswith("/AB123/")
    assert first.apply_url.endswith("/AB123/apply/")
    assert jobs[1].workplace == "Hybrid"


def test_workable_rejects_bad_account_and_malformed_envelope(monkeypatch):
    with pytest.raises(ValueError):
        sources.workable_jobs("X", "https://localhost/admin", SEEN)
    monkeypatch.setattr(adapters, "request_json", lambda _url: {})
    with pytest.raises(ValueError, match="missing jobs"):
        sources.workable_jobs("X", "sample", SEEN)


RECRUITEE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<jobs>
 <job><reference>1245</reference><title>Website Operations Manager</title>
 <company>Zensai</company><description_requirements><![CDATA[<p>CMS migrations and SEO</p>]]></description_requirements>
 <remote>true</remote><hybrid>true</hybrid><contract_type>full-time</contract_type>
 <locations>
  <location><city>Raleigh</city><state>NC</state><country>US</country></location>
  <location><city>Boston</city><state>MA</state><country>US</country></location>
 </locations>
 <posted>2026-10-21T11:00:00Z</posted><updated>2026-10-22T12:00:00Z</updated>
 <url>https://zensai.recruitee.com/o/website-operations</url>
 <apply_url>https://zensai.recruitee.com/o/website-operations/c/new</apply_url>
 <salary><min_salary>100000</min_salary><max_salary>135000</max_salary><currency>USD</currency><period>year</period></salary>
 </job>
</jobs>"""


def test_recruitee_xml_feed_preserves_location_posted_date_and_direct_apply(monkeypatch):
    seen = []
    def fetch(url):
        seen.append(url)
        return RECRUITEE_XML.encode()
    monkeypatch.setattr(adapters, "request_xml", fetch)
    j = sources.recruitee_jobs("Zensai", "zensai", SEEN)[0]
    assert seen == ["https://zensai.recruitee.com/api/feeds/offers.xml"]
    assert j.uid == "recruitee:zensai:1245"
    assert j.workplace == "Remote"
    assert "Raleigh" in j.location and "Boston" in j.location
    assert j.published_at == "2026-10-21T11:00:00Z"
    assert j.updated_at == "2026-10-22T12:00:00Z"
    assert "CMS migrations and SEO" in j.description
    assert j.apply_url.endswith("/c/new")
    assert j.compensation == "USD 100000-135000 year"


def test_recruitee_does_not_declare_unknown_remote_job_us_eligible(monkeypatch):
    xml = """<jobs><job><reference>2</reference><title>SEO Specialist</title>
    <remote>true</remote><country>GB</country>
    <url>https://sample.recruitee.com/o/seo-specialist</url></job></jobs>"""
    monkeypatch.setattr(adapters, "request_xml", lambda _url: xml.encode())
    role = sources.recruitee_jobs("Sample", "sample", SEEN)[0]
    assert "GB" in role.location
    assert "US" not in role.location


RSS = """<rss version="2.0"><channel><title>Startup Jobs</title>
<item><title>Acme: Senior SEO Manager</title>
<link>https://startup.jobs/senior-seo-manager-acme-123</link>
<guid>https://startup.jobs/senior-seo-manager-acme-123</guid>
<description><![CDATA[<p>Technical SEO and content operations.</p>]]></description>
<pubDate>Thu, 22 Oct 2026 12:30:00 +0000</pubDate>
</item>
<item><title>Content Operations Manager</title>
<link>https://startup.jobs/content-operations-xyz-456</link>
<description><![CDATA[<p>Sitecore, publishing and QA.</p>]]></description>
</item>
</channel></rss>"""


def test_startup_rss_does_not_invent_employer_apply_link_or_us_location(monkeypatch):
    seen = []
    def fetch(url):
        seen.append(url)
        return RSS.encode()
    monkeypatch.setattr(adapters, "request_xml", fetch)
    jobs = sources.startupjobs_jobs(
        "Startup Jobs Remote",
        "https://startup.jobs/feeds/jobs?workplace=remote", SEEN)
    assert len(jobs) == 1
    assert jobs[0].source == "startupjobs"
    assert jobs[0].company == "Acme"
    assert jobs[0].published_at == "2026-10-22T12:30:00+00:00"
    assert jobs[0].publication_basis == "feed_timestamp"
    assert jobs[0].job_url == jobs[0].apply_url
    assert jobs[0].location == ""
    assert not _has_external_application(jobs[0])
    assert jobs[0].source in AGGREGATOR_SOURCES
    assert seen == ["https://startup.jobs/feeds/jobs?workplace=remote"]
    with pytest.raises(ValueError):
        sources.startupjobs_jobs("X", "https://example.org/jobs", SEEN)


def test_existing_employer_sourcing_policy_remains_intact():
    assert {"recruitee", "workable"} <= DIRECT_SOURCES
    assert "startupjobs" not in DIRECT_SOURCES
    assert {"recruitee", "workable", "startupjobs"} <= sources.SOURCE_FUNCS.keys()
    assert validate_config({"local_regions": ["NC"], "boards": list(EXPANSION_BOARDS),
                            "alert_threshold": 82, "dashboard_threshold": 52,
                            "max_alert_age_hours": 24, "dashboard_age_hours": 168,
                            "watch_interval_minutes": 15}) == []


def test_expansion_catalog_adds_only_missing_boards_and_preserves_preferences():
    original = {"boards": [{"company": "Hugging Face",
                            "source": "workable", "board": "huggingface",
                            "enabled": False}],
                "local_regions": ["raleigh"],
                "alert_threshold": 91}
    updated, added = add_sources(original)
    assert len(added) == len(EXPANSION_BOARDS) - 1
    assert updated["boards"][0]["enabled"] is False
    assert updated["local_regions"] == ["raleigh"]
    assert len(planned_sources(updated)) == 0
    twice, another = add_sources(updated)
    assert another == []
    assert twice == updated
    assert original["boards"] == [{"company": "Hugging Face", "source": "workable",
                                   "board": "huggingface", "enabled": False}]


def test_add_sources_cli_backs_up_config_and_does_not_touch_state(config, tmp_path):
    paths = RuntimePaths.from_home(tmp_path)
    paths.ensure()
    paths.config.write_text(json.dumps(config, indent=2), encoding="utf-8")
    paths.state.write_text('{"jobs":{"x":{"alerted":true}}}', encoding="utf-8")
    original_state = paths.state.read_text()
    assert _add_sources(paths, dry_run=True) == 0
    assert json.loads(paths.config.read_text()) == config
    assert _add_sources(paths) == 0
    updated = json.loads(paths.config.read_text())
    assert len(updated["boards"]) == len(config["boards"]) + len(EXPANSION_BOARDS)
    assert len(list(tmp_path.glob("config.backup-*.json"))) == 1
    assert paths.state.read_text() == original_state
    assert _add_sources(paths) == 0
    assert len(list(tmp_path.glob("config.backup-*.json"))) == 1


def test_startup_rss_recovers_employer_from_title_at_company(monkeypatch):
    rss = ("""<rss><channel><item><title>Website Manager at Example Co</title>"""
           """<link>https://startup.jobs/website-manager-example-123</link>"""
           """<description>Sitecore and SEO</description>"""
           """</item></channel></rss>""")
    monkeypatch.setattr(adapters, "request_xml", lambda _: rss.encode())
    jobs = sources.startupjobs_jobs("Startup Jobs", "https://startup.jobs/feeds/jobs", SEEN)
    assert len(jobs) == 1
    assert jobs[0].company == "Example Co"
    assert jobs[0].title == "Website Manager"


def test_workable_multilocation_us_and_foreign_preserved(monkeypatch):
    payload = {"jobs": [{"shortcode": "a12", "title": "Web Producer",
            "city": "London", "country": "United Kingdom", "telecommuting": True,
            "locations": [{"city": "Raleigh", "state": "NC", "country": "US"}],
            "url": "https://apply.workable.com/a/j/a12/",
            "published_on": "2026-10-22T15:00:00Z"}]}
    monkeypatch.setattr(adapters, "request_json", lambda _: payload)
    job = sources.workable_jobs("Example", "example", SEEN)[0]
    assert "United Kingdom" in job.location
    assert "Raleigh, NC, US" in job.location
