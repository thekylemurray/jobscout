# Changelog

## 2.2.0 — Personal CLI source expansion preview

- Added no-token public Workable, Recruitee XML and Startup Jobs RSS adapters.
- Added curated expansion boards with safe idempotent `jobscout add-sources` and automatic timestamped config backup.
- Expanded focused Himalayas queries and corrected `pubDate` provenance to last-updated, not initial publication.
- Added source-attribution and deduplication counters to the scan log.
- Preserved Phase 2.1 scoring, personal profiles, history and alert-verification safeguards.



## 2.1.0 — Personal CLI requirement-confidence refinement

- Added candidate-oriented qualification sections without declaring them hard requirements.
- Introduced explicit evidence-confidence levels and mandatory qualification-review warnings, independent of fit scores.
- Kept unassessed experience distinct from verified skills gaps; unresolved high-scoring matches are routed to manual review instead of automatic Apply Now alerts.
- Expanded CSV and HTML reporting with confidence and qualification-review reasons.
- Added an offline synthetic 32-role benchmark with precision@5, recall and review/exclusion checks.
- Extended automated test coverage to Python 3.14 to match personal Windows installations.
- Continued compatibility with existing config.json, candidate_evidence.json, scan/watch, and state history.



## 1.0.0 — Portfolio release

- Converted the prototype into an installable `src/` Python package with a cross-platform CLI.
- Split source ingestion, normalization, scoring, orchestration, and runtime paths into focused modules.
- Added pytest regression coverage and Ruff linting.
- Added GitHub Actions CI across Python 3.11–3.13.
- Added an offline demo dashboard.
- Added Unix timestamp parsing for aggregator publication dates.
- Added company-alias normalization for stronger duplicate detection.
- Removed candidate-specific names and hard-coded local-region messaging from the engine.
- Added architecture, scoring, source, privacy, and contribution documentation.

## 0.8.1

Precision-tuning prototype: explicit SEO title handling, web-title precedence, and contextual adjacent-specialization penalties.
