# JobScout v1.6.1: operational alignment and qualification uncertainty

## Why this patch exists

Version 1.6 introduced useful mandatory-domain checks but deducted for unassessed skills **and** imposed additional score ceilings (e.g., 74). This obscured important differences between strong transferable operational experience and uncertain specialized requirements.

## Three distinct fields

- **Operational alignment (0–96):** The original, explainable title-plus-operations-skills score, with no mandatory-specialty deductions. It is **not** a job-offer probability or proof of qualification.
- **Qualification adjustment (0 to −24):** One bounded, explicit deduction for mandatory specialist requirements using candidate evidence (`demonstrated`, `transferable`, `unassessed`, `not_demonstrated`). An unassessed status indicates that supplied evidence is insufficient, not that the person lacks the qualification. Preferred skills are not penalized.
- **Adjusted fit (0–100):** Operational alignment plus the qualification adjustment; adjacent-review titles receive a separate −8 modifier. There are **no additional qualification/adjacent score caps**.

**Priority** starts from adjusted fit exactly once and then uses normal posting-age, source, location, and salary signals. It does not apply a second specialist deduction. The dashboard displays all three components, the adjusted fit and priority scores. The complete eligible, dashboard and adjacent-review CSV exports contain `operational_alignment_score` and `qualification_adjustment` alongside `fit_score` and `priority_score`.

Example: 96 operational alignment and an unassessed ethics/compliance requirement (−9) produce **87 adjusted fit**. Older publication dates can then lower priority independently.

## What did not change

- Permanent full-time, U.S./Washington remote, salary, people-management, travel, employer exclusions and other eligibility checks remain as in 1.6.
- Adjacent roles continue in an independent manual-review view/export, regardless of the normal freshness window; they cannot generate automatic alerts.
- SmartRecruiters availability verification and sources are unchanged.
- The existing local candidate profile JSON remains valid; v1.6.1 does not require editing sensitive candidate preferences.

## Validation boundaries

Automated tests verify accounting, dashboard/export fields, non-penalization of preferred skills, hard-veto preservation, and the absence of duplicated deductions. They do not establish real-world precision, verified Washington eligibility, compensation, or company application availability. Run a new live scan and inspect candidate results before distribution.
