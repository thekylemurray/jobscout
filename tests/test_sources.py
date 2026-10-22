from jobscout import sources


def test_greenhouse_adapter_normalizes_public_board_payload(monkeypatch):
    payload = {
        "jobs": [
            {
                "id": 42,
                "title": "Senior Website Manager",
                "location": {"name": "Remote - United States"},
                "content": "<p>Own the <strong>website</strong> roadmap.</p>",
                "absolute_url": "https://example.com/jobs/42",
                "first_published": "2026-09-03T12:00:00Z",
                "updated_at": "2026-09-04T12:00:00Z",
            }
        ]
    }
    monkeypatch.setattr(sources, "request_json", lambda _url: payload)

    jobs = sources.greenhouse_jobs("Example", "example", "2026-09-07T00:00:00Z")

    assert len(jobs) == 1
    assert jobs[0].uid == "greenhouse:example:42"
    assert jobs[0].description == "Own the website roadmap."
    assert jobs[0].published_at == "2026-09-03T12:00:00Z"


def test_himalayas_adapter_preserves_numeric_publication_timestamp(monkeypatch):
    row = {
        "guid": "abc",
        "companyName": "Example",
        "title": "SEO Manager",
        "locationRestrictions": ["United States"],
        "employmentType": "Full Time",
        "description": "<p>Technical SEO and analytics</p>",
        "applicationLink": "https://example.com/apply",
        "pubDate": 1788436800,
        "currency": "USD",
        "minSalary": 100000,
        "maxSalary": 130000,
        "salaryPeriod": "annual",
    }
    monkeypatch.setattr(sources, "request_json", lambda _url: {"jobs": [row]})

    jobs = sources.himalayas_jobs(
        "Himalayas US Remote",
        "https://example.com/api/search",
        "2026-09-07T00:00:00Z",
    )

    assert len(jobs) == 1
    assert jobs[0].published_at == 1788436800
    assert jobs[0].publication_basis == "feed_updated_timestamp"
    assert jobs[0].compensation == "USD 100000-130000 annual"
