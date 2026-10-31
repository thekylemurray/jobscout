"""The ATS detail 'ref' is never a user-facing application link."""
from jobscout import sources


def test_smartrecruiters_api_reference_not_exported_as_apply_url(monkeypatch):
    def api(url):
        if url.endswith("/postings/744000158098969"):
            return {
                "id": "744000158098969", "name": "Sr Business Operations Mgr",
                "ref": "https://api.smartrecruiters.com/v1/companies/ServiceNow/postings/744000158098969",
                "location": {"country": "US", "remote": True},
                "typeOfEmployment": {"label": "Full time"},
            }
        return {"totalFound": 1, "content": [{
            "id": "744000158098969", "name": "Sr Business Operations Mgr",
            "location": {"country": "US", "remote": True},
        }]}
    monkeypatch.setattr(sources, "request_json", api)
    jobs = sources.smartrecruiters_jobs("ServiceNow", "ServiceNow", "2026-10-31")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.apply_url == "https://jobs.smartrecruiters.com/ServiceNow/744000158098969"
    assert j.job_url == j.apply_url
    assert "api.smartrecruiters.com" not in j.apply_url
