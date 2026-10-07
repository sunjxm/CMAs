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

## October 7 2026 Median20 Selection And Fixed Income Model Foundation

Status: primary research candidate selected by user; projection and input registration implemented for research. No committee approval or asset-return forecast is inferred.

Changed primary_candidate from hlw_latest to hlw_median20. Retained latest HLW and LW diagnostics, the 30-year mean Treasury spread statistic, and zero basis adjustments pending review. Earlier numerical snapshots and their manifests remain unchanged; a new anchor-review run records the updated selection.

Registered six requested bond benchmarks with nominal USD return conventions. Global ex-USD is USD hedged and EMBI is USD hard-currency sovereign debt. Only the supplied LBUSTRUU ticker is entered; the other five exact identifiers remain unresolved rather than replaced by proxies. Benchmark and analytics verification are manual controls.

Implemented monthly Treasury par-node projections over 40 years, using a provisional five-year base half-life and three/eight-year sensitivities. Horizon zero, half-gap behavior, node/date/type consistency and source checksums are tested or enforced. Implemented offline asset readiness, Bloomberg metadata/history entry points, explicit units and monthly observed total-return calculations that do not bridge gaps.

FIXED_INCOME_RETURNS.md records the sleeve-specific return design and LaTeX formulas. Expected-return forecasts, real/foreign curves, credit-loss calibration, hedge carry and discount-factor pricing remain unimplemented. New summaries and manifests preserve the execution trail. Review copies can be refreshed with the Word converter.

Validation: the complete suite passed 59 tests, including projection identities, invalid inputs, hash/settings guards, asset configuration and missing-month return controls. A live offline run generated 15,873 par-node observations across three half-life scenarios, and a new review marked all 11 median20 nodes primary. Bloomberg metadata returned LBUSTRUU as U.S. Aggregate in USD; full benchmark/analytics verification remains outstanding.

## October 7 2026 Benchmark Tickers And Confirmed Replacements

Status: user-confirmed benchmark selection, pending live metadata and analytics verification.

Registered LGC3TRUU, LBUSTRUU, LTI1TRUU, LF98TRUU, LG38TRUH and EMUSTRUU with the Index suffix. Public sponsor/fund-provider documentation corroborates their identities; evidence links and verification notes are recorded in bond_assets.json and FIXED_INCOME_RETURNS.md.

Identified two differences from the earlier requests. The user explicitly chose Bloomberg US Corporate High Yield LF98TRUU instead of ICE BB-B constrained HY, and Bloomberg EM USD Aggregate EMUSTRUU instead of JP Morgan EMBI Global Diversified. The configuration retains the superseded names. HY calibration must cover the broader rating universe, and EM calibration must include corporate as well as sovereign/government-related exposure. A separate EM aggregate model family prevents mislabeling the new benchmark as sovereign-only EMBI.

The live API attempt was unsuccessful: localhost:8194 was unreachable. No new metadata or history is claimed as downloaded. Verification flags remain false. Offline review and tests can run without Bloomberg; unresolved benchmark mismatches cannot be marked verified. A new readiness archive records the confirmed selections. Historical run archives are unchanged.

Validation: all 62 tests passed, including three new tests for mismatch reporting, verification safeguards and the separate EM aggregate model family. The confirmed selection readiness report is archived in data/20261007T043717_d78280e9. Its manifest records configuration/code hashes and hashes of the CSV and Markdown outputs.

## October 7 2026 Approved Benchmarks And Monthly Index Analytics

Status: benchmark definitions accepted by user; historical index inputs and reviewed nominal analytics implemented. Expected-return assumptions remain unapproved and no asset forecasts are generated.

Recorded benchmark approval against the successful six-index metadata archive and its hash. Downloaded monthly total-return levels over the configured 30-year window: five sleeves have 360 levels, TIPS has 333 beginning January 1999. Observed monthly returns require adjacent calendar months. History is archived in data/20261007T044858_c7a75489.

Added API field discovery, candidate history probes and offline normalization tasks. Archived 207 candidate definitions in data/20261007T044912_7451b33f and 14,017 numeric candidate observations in data/20261007T045111_990c638e. Nominal mappings use index YTW, option-adjusted rate duration, USD blended spread duration and the explicitly basis-point Treasury OAS field. Units and definition evidence are recorded in configuration. Reviewed normalized observations and gaps are in data/20261007T045416_440bc4a1.

TIPS real-yield and real-duration inputs, global ex-USD spread/hedge inputs and convexity scaling remain unresolved. Generic index yields are not silently treated as real TIPS yields, and missing global fields are not zero-filled. Benchmark approval is not approval of credit losses, spread anchors, return approximations or equilibrium levels.

Validation: 67 tests pass, including new field parsing, error preservation, unchanged configuration during discovery, candidate raw-unit controls, percent/basis-point/duration normalization and source checksum rejection. Successful live field searches and history downloads were inspected. All new archives contain summaries and hashes; earlier archives remain unchanged.

## October 7, 2026 - TIPS Real Yield Investigation And Provisional Proxy

Status: implemented for research. User authorized an approximation if a suitable direct real-yield input could not be established.

Investigated Bloomberg real-yield/real-duration definitions and live index applicability. Nine direct analytics candidates returned no usable observations for LTI1TRUU; index average maturity did return data. No exact real-yield or real-duration mapping was approved. Search and probe evidence is retained in data/20261007T050208_tips_research and data/20261007T050254_tips_probe.

Added cma_curve/tips_inputs.py and main.py --task tips-inputs. The separate proxy archive uses USGGT05Y/PX_LAST as fixed 5-year real yield and INDEX_OAD_TSY as provisional duration, with index average maturity diagnostic only. September 30 values are 2.6985%, 3.5494 years and 4.7557 years respectively. Normalized observations, coverage and hashes are in data/20261007T050432_5c17a6c3. No backfill, arbitrary inflation subtraction or exact-analytics readiness override was performed.

The detailed investigation, LaTeX return specification, limitations and reproduction commands are in docs/TIPS_INPUTS.md. This downloads inputs only: real-yield equilibrium, CPI assumptions, sensitivity review and the expected-return engine remain separate work. All 71 tests pass.

## October 7, 2026 - First Investment-Grade Return Engine

Status: implemented for research, not approved CMAs. Covers LGC3TRUU and LBUSTRUU only.

Added cma_curve/bond_returns.py, return_settings.json and main.py --task bond-returns. The offline engine consumes the selected median20 Treasury projection and archived reviewed analytics. It uses explicit illustrative rate-node weights (2Y for short-term; equal 5Y/10Y for Aggregate), fixed endpoint durations, yield/12 carry proxy and fixed initial yield-basis residual. No separate roll-down, convexity, mortgage dynamics or fitted historical residual is added.

Base paths hold OAS constant and are before expected credit losses and fees. Separate trailing-20-year median OAS convergence and 10/25bp annual-loss sensitivities remain provisional. Each is crossed with existing 3/5/8-year Treasury half-lives. Exact monthly components, annual compounding, additive wealth-weighted annual attribution and 1/5/10/20/30/40-year annualized returns are archived in data/20261007T051346_bond-returns_9d6cd64a.

Gross constant-spread 30-year annualized paths are 4.1350% for Short Term Bond and 5.1581% for US Aggregate. These are deterministic research scenarios, not final expected returns. Historical explanatory diagnostics cover 288 compatible months (October 2002-September 2026), with monthly RMSE 7.1180bp and 27.1867bp. Realized shocks are used; no forecasting skill or point-in-time validation is claimed. Aggregate's 2008 model return exceeds observed return by approximately 1.98 percentage points.

Validation: 87 tests pass, including 16 new return-engine tests and an end-to-end archive fixture. Live archived-input execution succeeds. Source hashes, current settings/mappings, gap/staleness controls and annual attribution are checked. Initial native NumPy loading failure from launching outside activated conda was resolved by using the environment's Library/bin; no global environment modifications were made.

Detailed LaTeX formulas, choices, diagnostic results and outstanding approvals are in docs/INVESTMENT_GRADE_RETURNS.md. The other four sleeves remain unimplemented; input availability is not silently promoted to return-model approval.

## Future Entry Template

### Date And Change Title

Status: proposed, implemented for research, approved, or superseded.

Reason and evidence:

Definitions or calculations changed:

Affected source archives and numerical run summaries:

Tests and validation performed:

Unresolved assumptions and reviewer/approval record:
