# JobScout CLI — Phase 1 trust checks (preview)

This applies to the **personal command-line JobScout** based on `main`, not the Windows profile application for Doreen. Existing `jobscout scan`, `jobscout watch`, `config.json`, and local `data/state.json` remain supported.

## Changes

1. **Employer application verification.** Following ranking/deduplication, up to 40 qualifying **employer** application URLs are checked, with at most four concurrent requests and an eight-second timeout each. Aggregator-only pages are not counted as verified employer applications and no longer consume HTTP checks. Greenhouse and SmartRecruiters use their public requisition-detail APIs first, falling back to HTML checks if the API response is inconclusive. A successful HTTP response is not sufficient for active status. Positive evidence requires a matching job title and application call-to-action (or a matching Workday public detail record). Explicit withdrawn-job notices and direct posting HTTP 404/410 are treated as closed. HTTP 403/429, timeouts, JavaScript-only pages, redirects to general career pages, and unconfirmed Workday API errors are **Unverified**, not falsely closed.
2. **Publication provenance.** The CSVs and dashboard report whether a date came from a direct employer ATS, remote-job feed, relative Workday estimate, or first observation. A job discovered for the first time is not automatically assumed to have been posted that hour. A listing that is updated or reposted cannot reset its earlier observed publication time.
3. **Persistent requisition identity.** A local `requisitions` record is added to `data/state.json`; it retains first-seen and publication evidence, notification history, and last application check. Known ATS IDs persist despite some title and URL changes. **Missing from a source feed does not mean closed.**
4. **Stricter notifications.** Newly announced jobs must have a sufficiently recent *employer publication timestamp*, a successful application check, a high enough priority score, and a recent first observation. Workday relative dates and aggregator timestamps remain available for review, but do not independently trigger high-confidence alerts.

These rules intentionally favor reducing dead links and misleading freshness claims over maximizing notifications. Workday jobs with only a relative `postedOn` value will not create automatic alerts.

## Running it

From the existing local JobScout installation, after merging/updating to this branch:

```powershell
jobscout scan --open
jobscout watch
```

The **maximum** number of verifiable application URLs checked per scan is 40; the actual number can be smaller if most matches are aggregator-only links. Set `"verification_max_per_scan": 60` in `config.json` to increase that number, or set it to `0` to disable the HTTP checks during an offline test. Higher settings increase scan time and requests.

Review `output/jobs.html`, `output/eligible_all.csv`, `output/rejected.csv`, and `output/last_run.log`. The CSVs include `source`, `availability`, `availability_note`, `availability_checked_at`, `publication_basis`, and `first_seen_at`. The scan log includes an `APPLICATION_CHECK_SCOPE` summary showing employer checks, employer-linked aggregator checks, and skipped aggregator-only links.

## What this does not prove

A positively checked job can close at any time and does not guarantee a working submission flow behind authentication. Listings served exclusively through JavaScript often remain unverified. Public employer APIs may change. The app performs public GET requests only and does not log in or submit applications.

Existing state is preserved, but backing up your personal `data/state.json` and `config.json` before upgrading is sensible. The history key avoids title-based collisions whenever a known ATS requisition ID is available.

## Validation

The offline regression suite covers targeted Greenhouse and SmartRecruiters API responses, priority selection of employer links, aggregator-only pages, explicit withdrawn pages (including the Amgen error text), HTTP failures, generic redirects, employer publication timestamps versus estimates, old requisitions that are updated, and suppression of repeat notifications. CI runs on Python 3.11, 3.12 and 3.13.

## First scan replay (not a second live scrape)

The previously supplied `eligible_all(5).csv` has 112 eligible results. Of those, 30 have direct-employer URLs (including 20 Greenhouse, 7 SmartRecruiters, and 3 other direct destinations); only 10 clear the default review-fit threshold of 52. The remaining 82 results link to Himalayas or Jobicy aggregators rather than verified employer application pages. The new policy would select those 10 direct postings for verification instead of making 30+ requests that are expected to hit aggregator HTTP 403 responses. Actual live availability can change and requires a new scan on the user's PC.
