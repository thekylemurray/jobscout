# Scoring model

JobScout deliberately separates **fit** from **priority**.

## Fit

Fit estimates whether a role belongs in the configured career lane and whether the posting's evidence aligns with that lane. Signals are weighted by where they appear:

| Job-description section | Relative weight |
|---|---:|
| Required qualifications | 1.00 |
| Responsibilities | 0.85 |
| Preferred qualifications | 0.60 |
| General text | 0.50 |

Title evidence is evaluated before description evidence. Hard-veto title families prevent unrelated jobs from accumulating points through generic terms such as “stakeholder,” “governance,” or “analytics.”

`GEO` and `CRO` are context-aware to avoid geospatial and Chief Revenue Officer false positives. Adjacent specialties such as paid media, ecommerce, and demand generation are classified as **core**, **supporting**, or **incidental** before penalties are applied.

The bundled profile caps fit at 96 to avoid false certainty.

## Priority

Priority starts from fit and then adjusts for:

- publication freshness,
- direct-employer vs aggregator source,
- geography,
- compensation,
- contract preference.

This means a strong but stale role can remain a high fit while receiving a lower application priority.

## Why rules instead of embeddings?

For this project, deterministic evidence made debugging and calibration more useful than opaque similarity scores. The architecture leaves room for a later semantic-ranking layer, but the rule engine provides an auditable baseline and a regression-testable explanation for every result.

## Phase 2: occupation, mandatory skills and alert safety

The title occupation is checked before web/SEO keywords. Explicit software-engineering titles (including full-stack engineer roles mentioning website development) and internships are not recommended in the senior web-operations career lane.

Fit now applies bounded occupation-scope caps to directors, senior directors, heads of function, account-management-heavy positions and design/developer titles. Responsibilities explicitly involving direct reports are flagged and capped if personal evidence is not demonstrated. A cap is a career-lane judgment, not a declaration that the candidate is unqualified.

The optional, locally ignored candidate_evidence.json file supports positive, transferable and explicitly not-demonstrated required skills, with at most +8 and -24 points respectively. Missing evidence is **Unassessed** and does not create a negative score. Preferred skills do not produce mandatory-gap penalties. Requirement extraction is a conservative catalog, not exhaustive semantic understanding.

The shared heading parser now prefers longer non-overlapping heading phrases, so Preferred Qualifications is not confused with a generic Qualifications section.

Finally, the automated alert gate requires a minimum **fit score of 75**, independent of priority/freshness/verified application, unless locally overridden with min_alert_fit_score. For full examples and installation, see REQUIREMENT_SCORING.md.
