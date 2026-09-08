# Changelog

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
