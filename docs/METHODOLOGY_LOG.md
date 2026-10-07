# CMA Methodology Development Log

This log records implemented changes, proposed decisions, evidence, and unresolved choices. Numerical results belong to individual dated run summaries. Entries are additive; a later decision should supersede an earlier entry explicitly.

## 2026-10-06: Initial Data Layer

Status: implemented, not an approved forecasting methodology.

Implemented Bloomberg metadata/history retrieval, public Treasury par retrieval, raw official-source archiving, unit normalization, coverage reporting, and common-date curve selection. Generic Bloomberg yields remain separate from official par yields pending definition review. Official-source archives retain download manifests and checksums.

User-selected calibration window: 30 years, October 1996 through September 2026. Monthly observations use each series' last available date in a completed calendar month. Missing observations are not filled. Monthly Bloomberg requests use calendar periodicity.

Operational change: Treasury downloads now report annual progress and identify the year on failure. Download-all tasks share one Bloomberg client to avoid reconfiguring the xbbg engine between metadata and history requests.

## 2026-10-06: Official Input Processing And Candidate Anchors

Status: implemented for research and review. No anchors approved.

Added explicit source_parsers.py, estimate_anchors.py, and analysis.py modules, plus process-inputs and anchor-review entry-point tasks. Download-all remains an acquisition workflow; it does not silently estimate or approve equilibrium levels.

Finding: the previously archived Inflation.xlsx contains long-run CPI forecasts, not the PCE forecast needed for a PCE-based neutral-rate bridge. Added the official SPF median PCE10 workbook. Preserve CPI separately. HLW/LW use core PCE whereas PCE10 is headline PCE; expose a definition adjustment rather than assuming exact equivalence.

Transformation decisions:

- Preserve quarterly macro/survey observations at native frequency.
- Read the publisher's monthly ACM worksheet and check every maturity's yield decomposition.
- Retain every recognized HLW real-time quarterly vintage sheet, without inventing release dates.
- Require raw-file checksum agreement before parsing.
- Keep observation cutoffs distinct from verified information dates; all new review outputs remain point_in_time_eligible=false.

Candidate decisions:

- Compare latest HLW, a 20-quarter HLW median, and latest one-sided LW separately.
- Add latest SPF PCE10 to the selected real-neutral input using an explicitly approximate additive convention.
- Expose policy-to-3m and inflation-definition adjustments, initially zero and unapproved.
- Estimate par slopes relative to three-month Treasury yields, using equal-weight same-date paired monthly observations.
- Report 10-, 20-, and 30-year windows, mean/median and empirical spread quantiles; require 60 paired months for included primary nodes.
- Use the 30-year mean window and HLW latest only as provisional primary research settings.
- Keep ACM term premiums diagnostic; do not add them to par spreads.

Initial evidence: latest-HLW candidate 1-month yield approximately 3.1536%, 10-year yield approximately 4.4916%. Latest-LW alternatives approximately 3.7974% and 5.1354%. One-month spread coverage was 303 months; thirty-year same-date paired coverage was 312 months. These calculations show method sensitivity, not approved outputs or confidence intervals.

Validation: 37 automated tests passed, including an offline end-to-end output/hash test. Live parsing of six archived official files succeeded, including 34 HLW real-time vintages and all 30 ACM series. The first review run used the complete monthly Treasury archive and produced 33 candidate par nodes across three macro methods.

Dependency change: installed openpyxl and xlrd in my_env for XLSX/XLS reading; recorded them in the project's official optional dependency group.

Next decisions: assess policy/bill and headline/core adjustments; compare dated FOMC, market-expectations, and other neutral-rate evidence; approve or revise the anchor-selection rule; then implement and validate convergence. Discount-curve construction, expected returns, and historical forecast evaluation remain unimplemented.

## October 6 2026 LaTeX Equations And Word Review Copies

Status: implemented for documentation and review; no change to model approval status.

Methodology version 0.3 replaces plain-text formulas with LaTeX, defines symbols and units, and documents the equal-weight mean-spread estimator. Anchor and convergence calculations are unchanged.

The converter supports inline and display LaTeX through MathML to editable Word equations. Code blocks stay literal. Math dependencies are recorded in the documents extra. Markdown remains authoritative; dated run summaries and manifests are unchanged.

Validation: all 47 tests passed, including four new equation tests for fractions, powers, summations, inline/table math, escaped currency, code, and DOCX serialization. Both Word documents were rendered and visually reviewed.

## Future Entry Template

### Date And Change Title

Status: proposed, implemented for research, approved, or superseded.

Reason and evidence:

Definitions or calculations changed:

Affected source archives and numerical run summaries:

Tests and validation performed:

Unresolved assumptions and reviewer/approval record:
