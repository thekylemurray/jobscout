# Source adapters

JobScout currently contains adapters for:

| Source | Type | Notes |
|---|---|---|
| Greenhouse | Direct ATS | Public board JSON |
| Ashby | Direct ATS | Public job-board API |
| Lever | Direct ATS | Public postings API |
| SmartRecruiters | Direct ATS | Company postings API |
| Workday | Direct ATS | CXS/search endpoints |
| iCIMS | Direct ATS | Search/detail pages |
| Stripe Careers | Direct employer | Careers search/detail pages |
| Remote OK | Aggregator | Public API |
| Jobicy | Aggregator | Public remote-jobs API |
| Himalayas | Aggregator | Public search API |
| We Work Remotely | Aggregator | RSS |
| Workable | Direct employer ATS | Public jobs widget JSON (`published_on`) |
| Recruitee | Direct employer ATS | Published-offer XML feed, no careers token |
| Startup Jobs | Aggregator | Public RSS with source attribution |

Adapters are intentionally isolated from scoring. A source is responsible only for retrieval and normalization into the `Job` model.

> Public endpoints can change without notice. Source failures are isolated, retried where appropriate, and summarized in `output/last_run.log`. Always respect the terms and rate limits of sites you configure.

See [source expansion instructions](SOURCE_EXPANSION.md) for setup, rate limits, and provider date semantics.
