# JobScout 1.5 — portable requirement review

This release adds **opt-in** requirement-aware scoring for portable Windows profiles. The original CLI scorer and existing profiles continue to work without these keys.

## Mandatory specialist prerequisites

The optional `profile.capability_evidence` object maps a deliberately small set of specialty identifiers to one of four statuses:

- `demonstrated`: candidate provided affirmative evidence (no deduction)
- `transferable`: adjacent experience, but exact required specialty needs checking (−5)
- `unassessed`: no affirmative or negative information (−9; **not** a declaration of ineligibility)
- `not_demonstrated`: candidate explicitly reported not demonstrating it (−15)

Only language found in explicit requirement sections or mandatory statements counts. Preferred skills and general responsibilities do not incur a penalty. Combined deductions are capped at 24 points. The risk list and score breakdown both expose the relevant requirement and evidence status. Patterns are limited to HubSpot administration, paid media, training-data annotation, field-sales/revenue operations, partner ecosystems, and platform administration. They do **not** establish exhaustive qualification checking.

## Adjacent discovery

The optional `profile.adjacent_title_terms` list whitelists adjacent titles. A match gets `review_only=true`, `match_path=adjacent review`, an eight-point fit deduction and a maximum fit score of 74. Such jobs are displayed under **Adjacent — manual review** (and included in CSV exports), but **never trigger automatic match alerts**. Hard exclusions for salary, location, employment type, direct reports, employer and required certification still apply.

## SmartRecruiters

Public posting URLs are used instead of API detail references in the application link. The portable scanner retrieves full details for configured target and adjacent titles. The availability check requires the exact posting ID in the public active-postings list, a matching public detail ID/title, and a matching employer-facing SmartRecruiters URL. Missing/mismatching information, timeouts and HTTP errors yield **Unverified**, not a fabricated claim that a job closed. A verified listing means the job was listed at the check time; applying successfully is **not tested**.

## Boundaries

Scores remain deterministic review aids, not hiring probabilities or guarantees of qualifications, salary, Washington eligibility, or an offer. The role-specific career profile is stored separately from the executable. If the executable is replaced, import an updated JSON profile to receive profile-setting changes. Existing local profiles are retained.

## Development

The changes are exercised by the portable-requirements and SmartRecruiters regression fixtures, in addition to the existing CI tests and Windows smoke tests.
