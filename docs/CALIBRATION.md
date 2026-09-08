# Calibration notes

JobScout was built iteratively from observed ranking failures rather than from a fixed keyword list. Each meaningful false positive or false negative becomes a regression case.

## 1. Substring matching was not good enough

An early implementation treated raw substrings as signals. That caused two memorable failure modes:

- `geo` matched geographic / geospatial language.
- `cro` appeared inside unrelated words or referred to a Chief Revenue Officer rather than conversion-rate optimization.

The current matcher uses token/phrase boundaries plus local context. Ambiguous acronyms only count when surrounding language supports the intended meaning.

## 2. Generic business language creates fake relevance

Words such as `stakeholder`, `governance`, `analytics`, `roadmap`, and `automation` occur in almost every professional function. A finance or engineering role can accumulate a convincing-looking score if those signals are evaluated independently.

JobScout now classifies the title and role family before description scoring. Generic titles need a coherent cluster of web/content/search evidence; known out-of-lane title families are vetoed early.

## 3. Requirement location matters

A technology listed under **Required Qualifications** should carry more evidence than one buried in a generic company paragraph. The parser therefore approximates four sections and applies different weights:

- Required qualifications: 1.00
- Responsibilities: 0.85
- Preferred qualifications: 0.60
- General text: 0.50

The parser is intentionally conservative because many ATS feeds flatten the original HTML structure.

## 4. Adjacent specialties need context, not blanket penalties

A search role may mention ecommerce customers without being an ecommerce role. A website role may collaborate with demand generation without owning demand generation.

Adjacent specialties are therefore classified as:

- **core** — title evidence, repeated ownership, or explicit ownership language;
- **supporting** — appears in required/responsibility text without strong ownership;
- **incidental** — preferred/general mention only.

Only core and supporting signals reduce fit.

## 5. Fit and application priority are different questions

A role can be an excellent fit and still be a low-priority application because it is stale, poorly sourced, geographically incompatible, or below compensation targets.

Separating the two scores keeps the semantic question — *could I do this job?* — independent from the tactical question — *should I apply to this one first?*

## 6. Source normalization is part of ranking quality

The same role may appear on an employer ATS and multiple aggregators. JobScout canonicalizes company names, compares normalized title tokens, and prefers direct-employer records while preserving alternate-source provenance.

A later production run exposed another normalization issue: one aggregator emitted Unix publication timestamps while most ATS feeds emitted ISO-8601. Freshness was moved behind a source-agnostic parser that accepts ISO strings, Unix seconds, and Unix milliseconds.

## Regression philosophy

Scoring changes should answer a concrete observed failure. The preferred workflow is:

1. capture the false positive or false negative as a synthetic fixture;
2. write the assertion that expresses the desired behavior;
3. make the smallest scoring change that satisfies it;
4. run the full suite to protect earlier cases.

This keeps a hand-built ranking system from turning into an untestable pile of exceptions.
