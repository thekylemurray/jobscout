"""Small, read-only live smoke check for the new public sources.

No user config, résumé, tokens or history needed. Only checks a few seed
accounts; it does not claim those accounts have personally relevant openings.
"""
from __future__ import annotations

from .sources_expansion import workable_jobs, recruitee_jobs, startupjobs_jobs
from .utils import iso_now


def main() -> int:
    checks = [
        ("workable", workable_jobs, "Hugging Face", "huggingface"),
        ("recruitee", recruitee_jobs, "Braavo", "getbraavo"),
        ("startupjobs", startupjobs_jobs, "Startup Jobs",
         "https://startup.jobs/feeds/jobs?workplace=remote"),
    ]
    failures: list[str] = []
    for name, func, company, board in checks:
        try:
            jobs = func(company, board, iso_now())
            published = sum(j.published_at is not None for j in jobs)
            linked = sum(bool(j.job_url and j.apply_url) for j in jobs)
            print(f"OK {name}: {len(jobs)} normalized jobs / "
                  f"{published} dated / {linked} linked")
        except Exception as exc:
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            failures.append(name)
    if failures:
        print("Source smoke requires review: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
