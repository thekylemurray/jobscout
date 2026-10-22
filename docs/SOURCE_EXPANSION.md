# Source expansion — personal JobScout 2.2.0

This is for the **personal PowerShell/CLI edition**, not the separate Windows app being prepared for Doreen.

## New public, read-only adapters

| Source | Form | Account/board | Date semantics |
| --- | --- | --- | --- |
| Workable | Public employer widget JSON | account slug from `apply.workable.com/{slug}` | Employer's `published_on`, when provided |
| Recruitee | Public XML job feed | subdomain from `{slug}.recruitee.com` | XML `posted` (updated date kept separately) |
| Startup Jobs | Public RSS, 50 recent jobs / feed | URL at `startup.jobs/feeds/jobs` | RSS publication, provider feed timestamp |
| Himalayas (expanded) | Existing public filtered JSON search | your current Himalayas source | `pubDate` means last *update*, **not original job posting** |

Workable's private administrative SPI API is **not** used. Recruitee's JSON Careers Site API is moving to token requirements; this adapter uses the separate publicly documented XML feed, which exposes published offers. Startup Jobs requires no token for RSS and must be visibly credited as source, with links to its own job page. For Himalayas, **preserve `applicationLink` exactly** and display Himalayas source credit. These sites may change endpoints, limits, or terms.

References:
- https://workable.readme.io/reference/jobs-1
- https://docs.recruitee.com/docs/feed
- https://startup.jobs/api/
- https://himalayas.app/docs/remote-jobs-api

## Activate the nine curated source boards

The new adapters are installed in code, but **do not automatically modify your existing `config.json`**.

Open PowerShell in the actual JobScout project folder (containing `pyproject.toml`, `config.json` and `candidate_evidence.json`).

~~~powershell
.\.venv\Scripts\jobscout.exe --version
.\.venv\Scripts\jobscout.exe add-sources --dry-run
.\.venv\Scripts\jobscout.exe add-sources
.\.venv\Scripts\jobscout.exe doctor
.\.venv\Scripts\jobscout.exe scan --open
~~~

The `add-sources` command appends only missing (source, board) entries. It creates a timestamped `config.backup-*.json` **before** replacing the JSON file atomically. It leaves your current region, salary, watch settings, personal candidate evidence and `data/state.json` unchanged. If you previously disabled a source, it remains disabled. You can inspect and disable new employers in `config.json` afterward.

Initial monitored sample includes Workable accounts **Hugging Face, Huzzle and Dodge Construction Network**; Recruitee accounts **Zensai, Braavo, Better Collective and HIKE2**; and two Startup Jobs feeds (remote-all and remote-marketing). These are **not claims that specific matching jobs are currently open**. The purpose is to measure coverage from demonstrably existing career boards.

The first run against any newly added ATS creates a historical baseline, so the app should not alert on old roles just because it has never checked those employers before.

## Interpreting scan reports

Compare `output/eligible_all.csv`, `output/rejected.csv` and `output/last_run.log` to your last v2.1 scan. The new `EXPANSION_COVERAGE` log row contains:

- `raw_eligible`: eligible candidates found on Workable, Recruitee and Startup Jobs before cross-source deduplication.
- `dedup_primary`: records whose winning source is one of the new adapters.
- `overlap_with_existing`: retained postings also discovered via the new sources but whose winning source was a different adapter.

These are **source-discovery measurements**, not hiring success or true recall. A new adapter only creates meaningful value if it yields relevant unique postings that can be verified and applied to. The standard `APPLICATION_CHECKS` metrics continue to distinguish employer-confirmed applications from aggregator-only links.

Potential caveats: Workable's public widget may rate-limit; Recruitee feed markup can change; Startup Jobs RSS may omit employer/location (such entries are skipped or remain unverified); Himalayas API shared anonymous rate limits can affect broad searches. No broad crawling, credentials, login or auto-apply behavior is included.

## Next expansion options

After comparing a real scan, consider more targeted US employer accounts, Rippling and Personio, and an authenticated Startup Jobs JSON API if a free key is useful. Avoid expanding more broadly until we know the incremental source value.
