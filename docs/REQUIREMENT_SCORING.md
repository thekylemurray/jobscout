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

## Version 2.1 — Assessment confidence and manual review

A fit score is **relevance**, not a qualification guarantee. JobScout 2.1 now reports a separate assessment-confidence level based on how much *required-skill evidence* it could evaluate:

- **High:** At least two recognized explicit Required categories, with at least 75% of them assessed as demonstrated, transferable, or explicitly not demonstrated.
- **Medium:** Some explicit required categories are recognized, or at least two candidate-criteria categories are found without formal requirements.
- **Low:** No explicit required categories, and too little candidate-criteria evidence to establish structured qualification coverage.

This is **confidence in the completeness of extracted qualification evidence**, not a probability of being hired. High confidence can accompany a definite gap; low confidence does not imply unqualified. Job descriptions that say **Who You Are**, **About You**, or **What You Bring** now populate Candidate criteria rather than inventing mandatory requirements.

**Manual qualification review** is flagged when any of these apply:
1. Fit is 80+ but no explicit mandatory skill categories were recognized;
2. Two or more explicitly required categories are still unassessed;
3. At least one explicitly required category is declared not demonstrated by the local profile;
4. Direct-report or personnel-management responsibilities are present without demonstrated personnel management;
5. Leadership scope requires verification.

Flagged jobs remain in the review dashboard and exported CSVs, even when they score highly. They are **never placed in Apply Now** or sent as automatic verified alerts until reviewed; the tool doesn't pretend to know the missing qualifications. Review does not automatically change a fit score.

New report fields: `assessment_confidence`, `qualification_review_required`, and `qualification_review_reasons`. Existing `requirement_coverage`, `required_gaps` and evidence fields continue unchanged.

### Repeatable offline benchmark

On the JobScout source checkout, run:

```powershell
.\.venv\Scripts\python.exe -m jobscout.benchmark
```

The `benchmarks/phase2_1_cases.json` dataset contains 32 **synthetic, human-labeled fixture scenarios**, not full real job descriptions. The tool reports precision among review-ready top-five jobs, recall of labeled good matches, and rejection/review safeguard rates. CI runs the benchmark alongside unit tests. The dataset can be copied privately and relabeled for later testing against actual human-reviewed postings without committing application history.

**Do not interpret precision@5 on synthetic fixtures as observed real-world recommendation accuracy.** A live run and review of postings from the user's search profile remains necessary. Real-world recall also requires manually labeling known relevant jobs that the tool found, plus a sample of excluded listings.
