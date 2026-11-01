# JobScout v1.6 release candidate — calibration notes

This build addresses four categories of failure observed in Haley's October 31 / November 1 scans. It changes the opt-in portable desktop matcher, not the legacy personal CLI scorer.

## 1. Direct people management

Reject explicit experience or duties managing direct reports, supervising staff, or hiring/coaching/developing a team, including wording such as “5+ years of direct people-management experience.” Ordinary cross-functional project leadership is not a people-management veto. Potential future supervision is a **review note**, not proof of current direct reports. Ambiguous descriptions still need human confirmation.

## 2. Washington salary bands and on-target earnings

A multi-geography U.S. base salary envelope can wrongly combine a San Francisco maximum with Seattle and “other U.S.” ranges. For a candidate in Washington State, the new check rejects only when **every explicitly Washington-compatible band found is below the configured base floor**, regional coverage is sufficiently explicit, and unknown competing bands do not make a veto unsafe. A separate explicit U.S. on-target earnings (OTE) ceiling below the base floor is also disqualifying because base cannot exceed the quoted total on-target pay. OTE is **not** displayed as verified base compensation.

**Important limitation:** The parser recognizes common public salary formats, not all company-specific geographical tiers or bonus/equity disclosures. The candidate's city within Washington is unknown. A high Seattle range therefore triggers review, not confirmation that the candidate qualifies for that range. Ambiguous compensation stays unverified.

## 3. Mandatory domain specialties

Explicit mandatory ethics/compliance, public-sector procurement, and channel/distributor operations experience now enter the auditable capability assessment. The portable profile uses four evidence states: demonstrated, transferable, unassessed, not_demonstrated. Missing résumé evidence is **unassessed**, not an assertion of lacking the skill. Mandatory specialties not confirmed have fit-score caps (74 for unassessed, 84 for transferable, 62 for not_demonstrated) so generic operations keywords cannot produce a 96-point match on a specialist position. Preferred qualifications do not trigger these caps.

## 4. Adjacent-role visibility

Up to **25** of the most recently published/discovered adjacent matches remain in a dedicated **Adjacent — manual review** dashboard section, even when older than the primary dashboard's configured freshness window. A separate `adjacent_review.csv` export carries all adjacent eligible opportunities. They never generate automatic match alerts. All existing hard filters still apply.

## Verification and handoff boundaries

Regression fixtures cover salary tiers/OTE, direct-report duties vs. non-supervisory leadership, domain prerequisites vs. preferred skills, and aged adjacent results. CI includes Python tests and a Windows package/GUI smoke test.

**Not established by tests:** actual live market coverage, perfect matching accuracy, availability at the time of application, eligibility for Washington State remote work, or confirmed acceptable base compensation for roles with ambiguous bands. Review a fresh live scan before giving this to a new user as a final handoff. Personal profiles and résumés are not committed to the public repo.

Existing user profiles persist under `%LOCALAPPDATA%\JobScout\profiles`. Importing the v1.6 JSON creates a new profile; replacing the executable alone does not replace saved profile preferences. 
