from datetime import datetime, timezone
from jobscout.utils import parse_dt, canonical_company, has_meaningful_term

def test_parse_dt_iso_and_epoch():
    iso=parse_dt("2026-09-03T12:00:00Z")
    epoch=parse_dt(1788436800)
    assert iso and iso.tzinfo
    assert epoch and epoch.tzinfo
    assert epoch.year == 2026

def test_parse_dt_milliseconds():
    dt=parse_dt(1788436800000)
    assert dt and dt.year == 2026

def test_company_aliases():
    assert canonical_company("EndeavorB2B") == canonical_company("Endeavor Business Media")

def test_geo_context_suppresses_geospatial():
    assert not has_meaningful_term("GIS geospatial geographic mapping", "geo")
    assert has_meaningful_term("SEO AEO GEO generative search", "geo")


def test_nested_qualification_headings_remain_distinct():
    from jobscout.utils import extract_sections
    text = ("Required Qualifications: Sitecore experience and technical SEO. "
            "Responsibilities: CMS publishing, UAT. "
            "Preferred Qualifications: Drupal and HubSpot.")
    sections = extract_sections(text)
    assert "Sitecore" in sections["required"]
    assert "Drupal" not in sections["required"]
    assert "Dr​upal".replace("\u200b", "") in sections["preferred"]
    assert "UAT" in sections["responsibilities"]
