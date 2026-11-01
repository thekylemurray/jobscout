# JobScout v1.6.2 — Haley handoff release

This is a small **presentation and onboarding** patch on top of v1.6.1. The candidate's dealbreakers, salary parser, ATS connectivity, mandatory-qualification adjustments, and ranking formula are **unchanged**.

## Results dashboard

The portable Windows dashboard separates:

1. **Primary matches — recent:** primary jobs within the configured publication-age window that meet the display score threshold.
2. **Older primary matches — still listed:** older primary matches meeting that same threshold **only when the scanner last confirmed the specific posting was available**. The label does not guarantee that application submission will still work. Users are instructed to verify.
3. **Older primary matches — availability unverified:** explicit fallback when nothing more current is shown and old primary roles have not been confirmed available; does not claim they are current.
4. **Adjacent — manual review:** selected neighboring titles in a separate review-only section, irrespective of their age, never automatic application alerts.

At most 25 old still-listed primary entries and 25 adjacent entries are displayed, each ranked using the same previous scores. The complete `eligible_all.csv` and `adjacent_review.csv` remain available without silently dropping candidates. No eligibility, fit score, priority, or notification rules were changed.

The user's latest supplied v1.6.1 sample included **14 eligible opportunities: 6 recent primary, 5 older available primary, 3 adjacent**. Under this new presentation selection, the same static sample should display all 14 rather than 9. This is a replay-based expectation, not proof of a subsequent live-market scan.

## Windows handoff validation

- CI tests cover current/older/adjacent grouping, unverified old postings, original CSV completeness, unchanged ranking, the manual evaluator, and nonportable legacy dashboard.
- `packaging/smoke_clean_install.py` launches the real Tk app under a brand-new synthetic user-data directory on Windows, imports a synthetic JSON profile, saves it, restarts the app, and verifies profile persistence. It does **not** require or store a real candidate's personal data.
- The existing Windows Actions build performs full pytest, native-window smoke, clean import/restart smoke, PyInstaller packaging, and packaged executable launch smoke.
- A full scan from the actual Haley profile and a user-driven Windows SmartScreen/UI review are still distinct from automated testing. No code-signing certificate is included.

## Candidate-specific package

The ready-to-share ZIP is produced separately from GitHub Actions output so no personal candidate profile is committed to the source repo. It includes the Windows `JobScout.exe`, the portable `Haley_JobScout_Profile.json`, onboarding guidance, and release notes. Haley's résumé is **not bundled**. Profiles persist in Windows local application data, and job applications are not submitted automatically.

## Important limits

This software is a search and triage aid, not a hiring probability, guaranteed complete market search, verified compensation offer, Washington employment guarantee, application-acceptance guarantee, or substitute for reviewing employer requirements. A role shown as 'Available' means an employer posting was confirmed at last check, not that applying will succeed.
