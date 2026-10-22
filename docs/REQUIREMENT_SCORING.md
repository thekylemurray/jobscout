# Phase 2: Requirement-aware scoring for personal JobScout CLI

Phase 2 refines **fit** without changing the public job feeds or Phase 1 verification.

## What changed

1. **Occupation before keywords.** Full-stack/software engineering jobs are excluded even if the title includes website, SEO or content. Unpaid internships are excluded.
2. **Role-scope caps.** Directors, senior directors, heads of function, executives, account-management-focused roles, design-focused roles and developer roles receive conservative upper fit bounds. Explicit personnel-management responsibilities also constrain scores when direct-report experience has not been demonstrated.
3. **Requirements not merely keywords.** JobScout extracts a conservative list of skills and duties, labels each Required, Responsibility, Preferred or Mentioned, then checks a **local** candidate-evidence file. The shared section parser now handles nested headings correctly, so Preferred Qualifications are not mistaken for Required Qualifications.
4. **Inspectable evidence.** The dashboard displays a Requirement evidence section. The output CSVs add requirement_coverage, required_gaps, scope_flags and requirement_evidence columns.
5. **Alert fit minimum.** Strong-fit notifications require at least 75/100 fit in addition to the original priority threshold, verified employer application, credible freshness and deduplication.

## Optional private skill evidence

Copy a file named candidate_evidence.json next to your local config.json. Its content might look like this:

    {
      "demonstrated": ["sitecore", "cms publishing", "seo", "web qa"],
      "transferable": ["adobe experience manager", "contentful"],
      "not_demonstrated": []
    }

Use exact lowercase category names from src/jobscout/requirements.py. File parsing and status conflicts are validated. The file is excluded from Git commits and is not embedded in JobScout's public source. You can use a provided personalized file in your private local folder instead of this generic example.

**Definitions:** Demonstrated = relevant experience supported by the candidate; Transferable = related experience that may apply; Not demonstrated = candidate positively identifies a gap; Unassessed = unknown, not equivalent to unqualified. Omitting the file leaves specific qualification judgments unassessed and adds zero profile-specific score adjustment.

Positive evidence can add up to 8 points for required categories. Only *explicitly declared* gaps in required categories subtract points, up to 24. Preferred categories do not cause gap penalties. Role-scope caps always apply after evidence adjustments.

## Regression cases

| Case | Prior issue | New expected result |
| --- | --- | --- |
| Senior Full Stack Engineer, Website Development | Website in title rescued software engineering | Exclude |
| Head of AEO & SEO | Could score 96 | Cap at 68, visible head-of-function warning |
| Sr. Director, Marketing Web Product | Could score 96 | Cap at 62 |
| Senior SEO Manager & Account Manager | Account management overshadowed by SEO terms | Cap at 72, ownership warning |
| Website Content Writer Internship (UNPAID) | In target results | Exclude |
| Senior Web Producer, Technical SEO Specialist | Genuine web/search roles | Keep high-fit eligibility |
| Preferred HubSpot versus required Sitecore | Nested qualification headings misclassified | Distinguish preferred from required |

Scores remain explainable heuristics, **not a probability of being hired or proof of eligibility**. The requirement catalog is intentionally incomplete; terms not explicitly supported will not be classified. An omitted skill means "unassessed", not "does not qualify".

## Use with your existing installation

Back up your current local config.json and data/state.json. Install the updated CLI code in a separate folder first; do not replace your personal search history. Copy your original config.json and data directory. Optionally copy your candidate_evidence.json to that folder too. Then run in PowerShell:

    jobscout scan --open

Follow with:

    jobscout watch

Review output/eligible_all.csv, output/rejected.csv and output/last_run.log. The same CSVs are regenerated every scan; local state and the job-history ledger are preserved.

The bundled Python test suite includes requirement classification, role caps, pipeline integration, CSV exports and alert gating on Python 3.11–3.13. A live scan with your personal configuration is still required to establish behavior on current employer postings.
