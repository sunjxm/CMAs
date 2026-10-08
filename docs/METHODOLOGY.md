# US Yield Curve Capital Market Assumptions

## Document Control

Version: 0.8, working methodology draft. Updated October 7, 2026 (US Eastern time).

Status: data acquisition, source processing, candidate anchors, par-node projections, benchmark/TIPS inputs and first-order research return paths for Short Term Bond and US Aggregate are implemented. Current composition review, credit loss/spread calculators, synthetic Treasury discount-factor/holding-return comparisons and a global hedge-carry calculator are also implemented; see HANDBOOK_IMPLEMENTATION.md. The selected primary research candidate is HLW median20. Equilibrium levels, convergence and return approximations are not committee-approved. Complete composition, credit assumptions, foreign inputs, index-level repricing and the other four completed return sleeves remain outstanding. See INVESTMENT_GRADE_RETURNS.md for the existing index return engine, which these research extensions have not silently replaced.

This document separates implemented calculations from proposed extensions. Numerical review snapshots are preserved in dated run summaries rather than treated as permanent policy assumptions. The accompanying development log records the evolution of the process.

## 1. Objective And Scope

The objective is a reproducible, resource-efficient process for projecting the US Treasury yield curve over a horizon exceeding 30 years. The principal reporting nodes are one month, two years, five years, ten years, and thirty years. One month approximates the requested 30-day node; an exact day-based instrument mapping will be needed at the pricing stage. Additional Treasury nodes are retained to support curve construction.

Historical calibration currently covers October 1, 1996 through September 30, 2026. These are explicit settings, not automatically rolling dates. At monthly frequency the window contains 360 possible calendar months. Source-specific coverage can be shorter.

Long-run equilibrium estimates, the path toward equilibrium, and portfolio returns are distinct model components. Estimating an equilibrium curve does not by itself establish expected returns.

## 2. Curve Definition

The baseline historical and candidate equilibrium curves use official Treasury par yields. Treasury documents the par-curve definition and its construction from market quotations. Its fitting methodology changed on December 6, 2021; the long historical window therefore spans a source-methodology change. No attempt is currently made to restate the earlier history. [Treasury methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology)

Bloomberg generic benchmark yields are stored separately. Successful retrieval does not establish that a generic index has the same definition as the official par series. They are not used to estimate the baseline par slopes while catalog verification is incomplete.

ACM estimates belong to a model-based zero-coupon decomposition. They are not substituted for par yields or interpreted as directly observed risk premiums. [NY Fed term-premium data](https://www.newyorkfed.org/research/data_indicators/term-premia-tabs)

For later cash-flow pricing, projected par curves must be converted into consistent discount factors, zero yields, and forward rates. Coupon frequency, day count, settlement conventions, interpolation, and boundary assumptions will be specified before implementing this step. Five reporting nodes alone do not uniquely define a discount curve.

## 3. Data Sources

| Input | Source | Native frequency | Implemented use |
| --- | --- | --- | --- |
| Nominal par yields, 1m through 30y | US Treasury annual XML feed | Daily | Monthly historical spreads; complete starting par curve |
| Generic nominal Treasury yields | Bloomberg USGG indices | Requested monthly | Separately stored market diagnostics |
| Effective fed funds and SOFR | Bloomberg | Requested monthly | Archived policy/cash diagnostics; not yet calibrated into the policy-to-bill adjustment |
| US real neutral rate, HLW | NY Fed current workbook | Quarterly | Latest neutral-rate candidate and 20-quarter median alternative |
| US real neutral rate, LW | NY Fed current workbook | Quarterly | Separate latest-value neutral-rate candidate |
| HLW real-time histories | NY Fed vintage worksheets | Quarterly by labeled vintage | Preserved for future vintage analysis; not used in the primary candidate |
| Median 10-year headline PCE forecast | Philadelphia Fed SPF PCE10 | Quarterly | Long-run inflation candidate |
| Median 10-year CPI forecast | Philadelphia Fed SPF Inflation.xlsx | Quarterly | Separate CPI diagnostic, not a PCE substitute |
| ACM fitted zero yields, risk-neutral yields, and premiums, 1y through 10y | NY Fed ACM workbook | Monthly and daily sheets | Monthly decomposition checks and 10y premium diagnostics |

NY Fed defines r-star as a real short-term rate associated with stable inflation and normal economic conditions. US HLW/LW estimation uses core PCE inflation. Current-vintage one-sided estimates can still contain revised economic data and re-estimated parameters. The one-sided label does not establish historical release availability. [R-star overview](https://www.newyorkfed.org/research/policy/rstar), [HLW model and US data definitions, Appendix A2](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr1063.pdf)

SPF PCE10 is a median forecast of annual-average headline PCE inflation over the survey year and following nine years. It is a ten-year survey proxy, not a literal infinite-horizon inflation estimate. It begins in 2007; no earlier PCE history is manufactured. Inflation.xlsx contains CPI, not PCE, long-run forecasts. [PCE10 definition and files](https://www.philadelphiafed.org/surveys-and-data/pce10), [SPF documentation](https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/spf-documentation.pdf)

## 4. Archiving And Transformation

Every download is written to a new timestamped directory. Official-source manifests preserve the retrieval timestamp, configured and resolved URLs, file sizes, and SHA-256 checksums. Original workbooks are not overwritten by parsing.

Source processing uses explicit sheet and column mappings:

- HLW: locate the US column under Natural Rate (r*) in the current sheet and each recognized quarterly vintage sheet. Growth and foreign-country columns are not interchangeable with US r-star.
- LW: use the one-sided rstar column in the data sheet. The two-sided column is excluded from the candidate workflow.
- SPF CPI: INFCPI10YR on the INFLATION sheet.
- SPF PCE: PCE10 on the Median_Level sheet.
- ACM: DATE and ACMY01-10, ACMTP01-10, and ACMRNY01-10 on ACM Monthly. The publisher's URL has a CSV extension but the downloaded content is an XLS workbook; file signatures determine the archived format.

Before parsing, raw-file hashes must match the download manifest. Unrecognized layouts, duplicate source/vintage/period observations, invalid dates, and nonfinite numeric values cause failures. Empty/missing source observations are omitted without filling.

Rates preserve their original percentage-point values. Decimal rates equal original values divided by 100. Basis-point adjustments are divided by 10,000. Candidate tables include both decimal and percentage representations. Normalized official exports retain the sources' full histories; the calibration window and observation cutoff are applied when estimating candidates and diagnostics.

### 4.1 Frequency

Treasury daily data are sampled using the last available observation for each node in each completed calendar month. Actual observation dates are retained. Bloomberg monthly requests use calendar periodicity. This is month-end sampling, not averaging all daily yields within each month.

ACM uses the publisher's monthly worksheet. Quarterly r-star and survey series retain quarterly observations. They are not repeated three times to create pseudo-monthly samples. HLW/LW original quarter-start dates are preserved in source_date; a quarter-end date labels the economic period. SPF dates similarly label the survey quarter. These dates are not publication dates.

### 4.2 Availability And Vintage Controls

The analysis end date is an observation-period cutoff and historical calibration endpoint. It is not a verified forecast information date.

Current source snapshots and HLW real-time sheets currently lack mapped release dates. Their publication_date and vintage_date fields remain blank, availability_status identifies the gap, and point_in_time_eligible is false. A quarterly vintage label is retained but is not converted into a guessed publication date.

This allows current-vintage research and comparison, but not an unbiased historical forecast evaluation. Release calendars and vintage availability must be mapped before backtesting. The separately implemented dated-anchor importer can filter genuinely documented publication and revision dates; processed research observations are not silently inserted into that approved-input interface.

## 5. Candidate Cash And Policy Anchors

The implementation generates three macro candidates rather than automatically averaging models:

1. Latest available HLW US r-star: a monitoring sensitivity.
2. Median of the most recent 20 consecutive HLW quarterly estimates: the selected primary research candidate.
3. Latest available one-sided LW US r-star: a model-selection sensitivity.

Each uses the latest PCE10 median forecast whose survey-period label does not exceed the observation cutoff. Inputs older than the configured maximum of 12 months are rejected. The 20-quarter median requires all 20 consecutive quarters and gives equal weight to each quarter.

For candidate $j$:

$$
i_j^{*} = r_j^{*} + \pi_{\mathrm{PCE}}^{*} + \Delta_{\pi}
$$

$$
a_{j,3\mathrm{m}} = i_j^{*} + \Delta_{\mathrm{bill}}
$$

Here $i_j^{*}$ is the nominal neutral policy candidate, $r_j^{*}$ is the real neutral-rate candidate, $\pi_{\mathrm{PCE}}^{*}$ is the long-run headline PCE inflation proxy, and $\Delta_{\pi}$ is the inflation-definition adjustment. The reference three-month Treasury anchor is $a_{j,3\mathrm{m}}$; $\Delta_{\mathrm{bill}}$ is the policy-to-three-month basis adjustment. All rates and adjustments in these equations use decimal units.

The addition of real and inflation rates is an approximate nominal-rate convention, not an exact Fisher compounding calculation. Since the models use core PCE while SPF uses headline PCE, an explicit additive inflation-definition adjustment is exposed. Its sign represents the net correction required by the chosen definitions.

The policy-to-bill adjustment must account for the difference between a neutral overnight policy rate and the long-run yield of a three-month Treasury instrument. It may also need to reflect average-cycle effects relative to neutral policy. Both adjustments currently default to zero. Zero is a provisional modeling assumption, not an estimated relationship or an approved committee decision.

Neither the overnight policy candidate nor the three-month Treasury candidate is labeled as the final 30-day cash anchor. The one-month par node is obtained separately from the historical one-month versus three-month spread.

## 6. Historical Par Spreads And Curve Anchors

The three-month Treasury par node is the historical reference because it has longer coverage than the one-month node. For maturity $m$ and month $t$:

$$
s_{m,t} = y_{m,t}^{\mathrm{par}} - y_{3\mathrm{m},t}^{\mathrm{par}}
$$

$$
a_{j,m} = a_{j,3\mathrm{m}} + \widehat{s}_m
$$

Here $s_{m,t}$ is the paired historical par spread, $y_{m,t}^{\mathrm{par}}$ is the observed par yield, $a_{j,m}$ is the candidate par anchor, and $\widehat{s}_m$ is the selected historical spread statistic. The primary mean-spread estimator is:

$$
\widehat{s}_m = \frac{1}{N_m} \sum_{t \in \mathcal{T}_m} s_{m,t}
$$

The set $\mathcal{T}_m$ contains eligible paired months in the selected window and $N_m$ is its observation count. The same units apply to yields, spreads, and anchors.

Each spread requires both nodes on the same actual observation date. A shared calendar month alone does not authorize pairing quotes from different dates. Available paired months receive equal weights. At most one observation per node per month is permitted.

The primary research setting uses the mean paired spread over the requested 30-year window. Diagnostics also report 10- and 20-year windows, medians, and 10th/90th percentiles. These percentiles describe historical observations, not uncertainty intervals for equilibrium means. At least 60 paired months are required for every node included in the primary candidate.

All available standard Treasury nodes are retained. No monotonicity constraint is imposed on yield levels. Sample windows, missing history, and economic regimes can affect the estimated curve shape; shape and coverage require explicit review.

The one-month node uses its observed spread to three-month yields rather than silently backfilling one-month history with three-month rates. Thirty-year gaps are also not interpolated or replaced with Bloomberg benchmark quotes. Different maturities can consequently have different effective samples.

Historical par spreads include more than a pure term premium: they also reflect expected future short-rate differences, liquidity, and instrument effects over the selected sample. They are empirical curve-shape anchors, not structural term-premium estimates. A multi-cycle mean is a practical starting point whose stability must be checked.

## 7. ACM Diagnostic Controls

For maturities one through ten years, fitted yield must equal risk-neutral yield plus term premium within 0.000001 percentage points on complete rows. The workflow records monthly 10-year premium means, medians, latest values, and sample coverage over 10-, 20-, and 30-year windows.

ACM premiums are not added to the historical par spreads, which would introduce overlapping compensation. Nor are they extrapolated mechanically from ten to thirty years. A separate zero-curve anchor methodology would require consistent zero-yield and compounding definitions.

## 8. Initial Research Snapshot

The first processing run used the six-source official archive retrieved on October 7, 2026 UTC and the monthly Treasury bundle covering October 1996 through September 2026. The run was performed on October 6 US Eastern time. These retrieval dates do not establish that all source revisions were available on September 30.

The latest HLW r-star was approximately 1.0086% for 2026Q2, LW was approximately 1.6524% for 2026Q2, and SPF headline PCE10 was 2.2000% for 2026Q3. Under zero adjustments and the 30-year mean-spread setting:

| Node | HLW latest candidate | LW latest candidate | Paired months |
| --- | --- | --- | --- |
| 1 month | 3.1536% | 3.7974% | 303 |
| 2 years | 3.5349% | 4.1787% | 360 |
| 5 years | 3.9963% | 4.6401% | 360 |
| 10 years | 4.4916% | 5.1354% | 360 |
| 30 years | 4.8419% | 5.4857% | 312 |

These are reproducible candidate outputs, not approved CMA levels. The roughly 64-basis-point difference between model choices is economically material and is not a statistical confidence interval.

The historical 10-year par spread to three-month yields averaged approximately 128.30 basis points. The same 30-year window produced a mean ACM 10-year zero-coupon premium of approximately 72.58 basis points. The concepts differ; their difference is not added as a pricing adjustment.

## 9. Convergence Design

The implemented research baseline projects each maturity toward its selected equilibrium candidate:

$$
y_m(t) = a_m + \left[y_m(0) - a_m\right] d_H(t)
$$

$$
d_H(t)=\begin{cases}
2^{-t/H}, & 0\le t\le25,\\
2^{-25/H}(30-t)/5, &25<t<30,\\
0, &t\ge30.
\end{cases}
$$

Here $a_m$ is the selected equilibrium candidate, $y_m(0)$ is the starting par yield, and $H > 0$ is the convergence half-life. Forecast horizon $t$ and half-life $H$ are both measured in years. The engine outputs monthly par-node paths over 40 years, reaching the anchor exactly at year 30 and remaining there thereafter.

Maturity m is distinct from forecast horizon t. Horizon zero must reproduce the common-date starting curve. Half-lives of three, five, and ten years are user-selected sensitivity settings, not empirically validated constants. The exponential phase ends at year 25. The remaining gap then closes linearly by year 30. Levels are continuous at the handoff, but their slopes generally change.

An optional near-term OIS/futures/survey path can be assessed after the baseline is implemented. Market forwards are not automatically unbiased forecasts and a forward short rate is not a future ten-year bond yield. Premium, convexity, instrument-basis, and handoff assumptions would need separate treatment. The additional layer should be retained only when it improves forecast validation or materially informs portfolio decisions.

The provisional base uses a five-year half-life at all maturities, with three- and ten-year sensitivity paths. This is a configuration choice, not a fitted estimate. The projection preserves the common-date starting nodes and verifies source checksums and anchor settings. This task does not bootstrap discount curves or calculate portfolio returns. Surface comparisons use piecewise-linear maturity interpolation solely for visualization, with exact modeled nodes retained. The primary HLW median20 selection changes the neutral-rate input only; historical spreads continue to use their 30-year mean.

The surface comparison has five starting-curve rows (current September 30, 2026 first) and three half-life columns. Historical observed curves from December 2006, December 2009, July 2020 and June 2023 use the same current-vintage anchors. These are alternative initialization scenarios, not historical forecasts or a point-in-time backtest. Details and charts are in docs/YIELD_CURVE_SURFACES.md. Old curve and return archives are preserved; downstream return forecasts have not been regenerated with this change.

## 10. Pricing And Return Design: Planned

Projected curves will be converted to discount factors using a reviewed fixed-income library and explicit conventions. Verification will include reproduction of input par rates, positive discount factors, and internally consistent zero and forward rates.

Fixed-income returns will be calculated by aging and repricing actual representative cash flows, including coupon income and reinvestment. Constant-maturity rebalanced portfolios and buy-and-hold bonds require different definitions. Roll-down must not be added twice when repricing already captures it. Credit spreads, defaults, TIPS indexation, and callable or mortgage exposures require additional models.

Six rebalanced benchmark sleeves are now registered for nominal USD returns: short-term government/credit, US Aggregate, TIPS 1-10Y, Bloomberg US Corporate High Yield, Global Aggregate ex USD hedged to USD, and Bloomberg Emerging Market USD Aggregate. On October 7, the user confirmed the Bloomberg HY and EM benchmarks instead of the earlier ICE BB-B constrained and JP Morgan EMBI requests. Broader HY rating coverage and EM corporate exposure must be reflected in the return model. A monthly carry-and-risk approximation is proposed as the first resource-efficient index-level implementation, with explicit validation before use and cash-flow repricing as a later refinement. Benchmark identifiers, analytics, credit losses, real/foreign curves and hedge carry must be verified first. FIXED_INCOME_RETURNS.md documents the separate models and outstanding inputs. Asset registration and historical downloads do not constitute expected-return forecasts.

## 11. Validation And Approval

The initial implemented phase passed 37 automated tests plus a live archive integration run. Covered controls include workbook mapping, units, decomposition, hash failures, missing observations, monthly pairing, cutoff filtering, stale inputs, smoothing coverage, candidate arithmetic, audit-output hashes, curve-type separation, and shared Bloomberg sessions. Passing tests validate implemented behavior; they do not establish forecasting accuracy or committee approval.

Before adoption, reviewers must approve:

- The neutral-rate source, smoothing rule, and comparison with dated FOMC/survey estimates.
- The long-run inflation proxy and headline/core definition adjustment.
- The policy-to-Treasury basis and whether a neutral level needs a cycle-average adjustment.
- The historical spread window, mean/median choice, and treatment of structural changes and node gaps.
- Low/base/high economic scenarios, distinguishing judgments from confidence intervals.
- Convergence half-lives, any near-term market overlay, and the pricing/portfolio conventions.
- Publication-date and vintage mapping before backtests, plus the proposed forecast evaluation benchmarks.

No approval state is inferred from a successful data-processing run. The review pipeline is deliberately restricted to research-draft outputs.

## 12. Reproducibility And Documentation Trail

The version-controlled docs/METHODOLOGY.md contains the evolving process. docs/METHODOLOGY_LOG.md records development decisions and their status. Each processing or review run creates an independent run_summary.md and a manifest in its dated data directory. Prior reports are not overwritten.

Run manifests record the raw archive, Treasury input bundle where used, settings, parser version, source hashes, processing-code hashes, and generated-file hashes. Numerical candidates, macro components, spread diagnostics, ACM diagnostics, source inventories, and the starting curve are saved separately for inspection.

When settings or source mappings change, rerun the analysis and add a dated log entry explaining the reason, validation performed, and approval status. Preserve the raw input bundles. Commit code, settings, and methodology text to version control; keep vendor downloads outside Git unless organizational licensing and data-handling rules explicitly permit distribution. Git hashes and manifests alone cannot restore raw files that were not retained.

On another machine, install the project with its official-source and Bloomberg extras as applicable. Download fresh data for a new analysis, or securely transfer the exact permitted archives to reproduce an earlier result. Default latest-bundle discovery is convenient for routine research; pin explicit archive paths for formal reproducibility.
