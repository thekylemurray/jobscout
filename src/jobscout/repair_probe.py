"""Low-volume proof that repaired Amplitude/Postman public ATS endpoints respond."""
from __future__ import annotations

from .http import request_json, request_json_post


def main() -> int:
    failures = []
    ashby = "https://api.ashbyhq.com/posting-api/job-board/amplitude?includeCompensation=true"
    try:
        obj = request_json(ashby)
        roles = obj.get("jobs", [])
        if not isinstance(roles, list) or not roles:
            raise ValueError("Amplitude Ashby returned no recognized jobs")
        print(f"OK Amplitude Ashby: {len(roles)} job records")
    except Exception as exc:
        failures.append("Amplitude")
        print(f"FAIL Amplitude Ashby: {type(exc).__name__}: {exc}")
    base = "https://postman.wd108.myworkdayjobs.com"
    api = f"{base}/wday/cxs/postman/careers/jobs"
    try:
        obj = request_json_post(
            api,
            {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
            referer=f"{base}/en-US/careers",
        )
        roles = obj.get("jobPostings", [])
        if not isinstance(roles, list) or not roles:
            raise ValueError("Postman Workday returned no recognized postings")
        print(f"OK Postman Workday: {len(roles)} first-page job records")
    except Exception as exc:
        failures.append("Postman")
        print(f"FAIL Postman Workday: {type(exc).__name__}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
