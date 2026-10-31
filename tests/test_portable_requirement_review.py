"""Synthetic regression cases informed by Haley's October scan, no private PII."""
from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone

import pytest

from jobscout.app import render_html
from jobscout.config import default_config, validate_config
from jobscout.models import Job
from jobscout.portable_requirements import assess_required_capabilities
from jobscout.profiles import blank_profile
from jobscout.review import check_availability, review_status
from jobscout.scoring import score_job


def profile_config():
    c = default_config()
    p = blank_profile()
    p.update(name="Synthetic remote senior IC",
             title_terms=["program manager"], adjacent_title_terms=[
                 "sales operations manager", "senior manager gtm operations",
                 "ai product strategy operations senior manager"],
             core_skills=["operating cadence", "workflow automation"],
             career_lanes=[], allow_remote=True, allow_contract=False,
             remote_only=True, home_state="Washington", require_full_time=True,
             exclude_people_management=True, max_travel_percent=9.99,
             capability_evidence={
                 "data_annotation": "unassessed",
                 "hubspot_admin": "unassessed",
                 "paid_media": "unassessed",
                 "field_sales_revops": "transferable",
             })
    c.update(profile=p, local_regions=[], salary_floor=150000, salary_target=165000,
             dashboard_threshold=52, boards=[])
    assert not validate_config(c)
    return c


def posting(**kwargs):
    data=dict(uid="example", company="Example", source="manual",
              title="Senior Program Manager", location="Remote - United States",
              workplace="Remote", employment_type="Full Time",
              description="Build an operating cadence and automate workflows.",
              job_url="https://example.com/123", apply_url="https://example.com/123",
              published_at=None, first_seen_at="2026-10-31T00:00:00Z",
              compensation="USD 165000-200000 annual base")
    data.update(kwargs)
    return Job(**data)


def test_required_specialty_reduces_score_and_shows_evidence():
    cfg=profile_config()
    base=score_job(posting(),cfg)
    flagged=score_job(posting(description=(
        "Required qualifications: At least five years of data annotation operations. "
        "Build an operating cadence and automate workflows. "
        "Responsibilities: Coordinate stakeholder programs.")),cfg)
    assert flagged.eligible
    assert flagged.fit_score < base.fit_score
    assert any("required specialty data_annotation (unassessed)" in n for n in flagged.requirement_notes)
    assert any("-9" in n for n in flagged.score_breakdown)


def test_preferred_and_generic_responsibilities_not_required():
    cfg=profile_config()
    preferred=score_job(posting(description=(
        "Responsibilities: Lead data annotation operations. "
        "Preferred qualifications: Five years of data annotation operations. "
        "Build an operating cadence and automate workflows.")),cfg)
    assert preferred.eligible
    assert preferred.requirement_notes == []


def test_demonstrated_and_transferable_not_misrepresented():
    p=profile_config()['profile']
    desc="Required Qualifications: Experience in sales forecasting and field sales teams."
    notes, penalty, lines=assess_required_capabilities(desc,p)
    assert penalty == -5
    assert any("transferable" in n for n in notes)
    p['capability_evidence']['field_sales_revops']="demonstrated"
    assert assess_required_capabilities(desc,p)[1] == 0


def test_adjacent_role_only_review_no_alert_class():
    cfg=profile_config()
    j=score_job(posting(title="Sales Operations Manager",description="Build dashboards."),cfg)
    assert j.eligible and j.review_only and j.match_path == "adjacent review"
    assert j.fit_score <= 74
    assert review_status(j) == "Adjacent — manual review"
    html=render_html([j],portable=True)
    assert "Adjacent — manual review" in html


def test_hard_veto_overrules_adjacent():
    cfg=profile_config()
    assert not score_job(posting(title="Sales Operations Manager",workplace="Hybrid"),cfg).eligible
    assert not score_job(posting(title="Sales Operations Manager",compensation="USD 100000-120000 annual base"),cfg).eligible
    assert not score_job(posting(title="Sales Operations Manager",description="Managing 4 direct reports."),cfg).eligible


def test_profile_schema_rejects_unknown_evidence_keys():
    c=profile_config()
    c["profile"]["capability_evidence"]["invented"] = "unassessed"
    assert any("capability_evidence" in err for err in validate_config(c))


class _Response:
    def __init__(self,payload):
        self.payload=json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self,n=-1):
        return self.payload


def sr_posting():
    return posting(
        source="smartrecruiters", uid="smartrecruiters:ServiceNow:744000158098969",
        title="Sr Business Operations Mgr",
        job_url="https://jobs.smartrecruiters.com/ServiceNow/744000158098969",
        apply_url="https://jobs.smartrecruiters.com/ServiceNow/744000158098969")


def test_smartrecruiters_public_active_listing_verified(monkeypatch):
    from jobscout import review
    urls=[]
    def fetch(req,timeout=8):
        urls.append(req.full_url)
        if "?" in req.full_url:
            return _Response({"content":[{"id":"744000158098969","name":"Sr Business Operations Mgr"}]})
        return _Response({"id":"744000158098969","name":"Sr Business Operations Mgr",
                          "applyUrl":"https://jobs.smartrecruiters.com/ServiceNow/744000158098969-operations"})
    monkeypatch.setattr(review.urllib.request,"urlopen",fetch)
    j=check_availability(sr_posting())
    assert j.availability == "Available"
    assert "application submission not tested" in j.availability_note
    assert j.apply_url.endswith("-operations")
    assert len(urls)==2 and "destination=PUBLIC" in urls[0]


def test_smartrecruiters_filtered_absence_never_closes(monkeypatch):
    from jobscout import review
    monkeypatch.setattr(review.urllib.request,"urlopen",lambda req,timeout=8:_Response({"content":[]}))
    j=check_availability(sr_posting())
    assert j.availability=="Unverified" and "incomplete" in j.availability_note


def test_smartrecruiters_detail_404_does_not_falsely_close(monkeypatch):
    from jobscout import review
    def fetch(req,timeout=8):
        if "?" in req.full_url:
            return _Response({"content":[{"id":"744000158098969"}]})
        raise urllib.error.HTTPError(req.full_url,404,"Not Found",None,None)
    monkeypatch.setattr(review.urllib.request,"urlopen",fetch)
    j=check_availability(sr_posting())
    assert j.availability=="Unverified"


def test_smartrecruiters_unrelated_link_not_recommended(monkeypatch):
    from jobscout import review
    def fetch(req,timeout=8):
        if "?" in req.full_url:
            return _Response({"content":[{"id":"744000158098969"}]})
        return _Response({"id":"744000158098969","name":"Sr Business Operations Mgr",
                          "applyUrl":"https://jobs.smartrecruiters.com/ServiceNow/WRONG"})
    monkeypatch.setattr(review.urllib.request,"urlopen",fetch)
    j=check_availability(sr_posting())
    assert j.availability=="Unverified"
