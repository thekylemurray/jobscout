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
