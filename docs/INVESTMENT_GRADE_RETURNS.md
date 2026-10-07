# Investment-Grade Bond Return Methodology

Version: 0.1. Date: October 7, 2026. Status: implemented research approximation, not approved expected-return CMAs.

## Scope And Decisions

The first return engine covers Short Term Bond (`LGC3TRUU Index`) and US Aggregate (`LBUSTRUU Index`). Both are nominal USD rebalanced-index sleeves. It consumes archived observations offline; it does not request new Bloomberg data.

The Treasury paths retain the selected `hlw_median20` neutral-rate candidate, 30-year mean historical Treasury slopes, and provisional 5-year convergence half-life. Rate half-life sensitivities of 3 and 8 years are retained. The name median20 refers to neutral-rate smoothing; it does not change the slope estimator or automatically select a credit-spread assumption.

This implementation adds deterministic return scenarios, not an approved probability-weighted or stochastic expected return. Credit losses and fees are not estimated. A zero-loss gross scenario must not be published as a final net CMA.

## Inputs And Rate Exposure

Endpoint month: September 2026. The input observations and starting official par curve end on September 30.

| Sleeve | Yield-To-Worst | Rate Duration | Spread Duration | Treasury OAS |
| --- | --- | --- | --- | --- |
| Short Term Bond | 4.981182% | 1.770269 years | 1.857456 years | 10.5504 bp |
| US Aggregate | 5.564121% | 5.699883 years | 5.632845 years | 31.3007 bp |

Yields are normalized to decimal rates and OAS to decimal spreads. Durations remain years. These field mappings were reviewed separately from the benchmark identity.

The provisional rate-exposure proxy weights are:

| Sleeve | 2Y Treasury | 5Y Treasury | 10Y Treasury |
| --- | --- | --- | --- |
| Short Term Bond | 100% | 0% | 0% |
| US Aggregate | 0% | 50% | 50% |

These are illustrative judgmental weights, not measured key-rate durations, not maturity weights and not fitted coefficients. They sum to one, so a parallel Treasury shift produces the total observed rate-duration response. Nonparallel curve moves remain approximations. Duration is never used as a maturity or an interpolation coordinate. The weights are editable in `return_settings.json`.

## Yield-Based Carry Proxy

Let $y_{m,t}$ be the projected Treasury par yield for node $m$, $w_{a,m}$ the sleeve's proxy exposure weight, $s_{a,t}$ its OAS, and $Y_{a,0}$ its observed initial yield-to-worst.

Define the initial yield-basis residual:

$$
q_a = Y_{a,0} - \sum_m w_{a,m}y_{m,0} - s_{a,0}.
$$

Hold this residual constant and update the sleeve's yield proxy:

$$
Y_{a,t} = \sum_m w_{a,m}y_{m,t} + s_{a,t} + q_a.
$$

This reproduces initial yield-to-worst exactly. The residual is an accounting calibration, not an estimated return premium; it can contain coupon, curve, sector, option and analytics-basis effects. Holding it fixed for decades is a simplification requiring review.

Monthly carry is approximated by $Y_{a,t}/12$. Yield-to-worst is not an exact coupon-income measure or a guaranteed return. No additional OAS carry is added because OAS is already included in the yield proxy. No separate roll-down contribution is assumed or added in this version; this limitation is explicit rather than filled with a fitted residual.

## Monthly Returns

For annual expected-loss input $\ell_a$ in decimals:

$$
R_{a,t+1} = \frac{Y_{a,t}}{12}
- D^r_a \sum_m w_{a,m}\left(y_{m,t+1}-y_{m,t}\right)
- D^s_a\left(s_{a,t+1}-s_{a,t}\right)
- \frac{\ell_a}{12}.
$$

Rate and spread durations are held at their observed endpoint values throughout the projection, consistent with a constant-exposure rebalanced-index approximation rather than an aging buy-and-hold bond. Credit losses enter exactly once. Rates and return contributions are decimals; durations are years.

The first-order model omits convexity, changes in duration, mortgage prepayment and volatility dynamics, detailed sector composition, index turnover, fees, transaction costs and taxes. The US Aggregate's securitized exposure makes these omissions especially relevant. Future cash-flow pricing or a sector model would replace this approximation rather than add overlapping carry or roll-down terms to it.

## Scenarios And Sensitivities

| Case | Spread Path | Annual Loss Input |
| --- | --- | --- |
| gross_constant_spread | Initial OAS held constant | 0 bp; gross diagnostic |
| gross_median20_spread | OAS converges to its trailing 20-year median | 0 bp; gross diagnostic |
| loss_10bps_sensitivity | Initial OAS held constant | Illustrative 10 bp |
| loss_25bps_sensitivity | Initial OAS held constant | Illustrative 25 bp |

The 10/25bp inputs are sensitivity amounts applied to the whole sleeve, not estimates of index default losses or losses per credit-sector dollar. They are neither committee-approved nor substitutes for rating/sector weights and recovery assumptions.

For the historical-median spread sensitivity:

$$
s_{a,t} = \bar{s}_a + \left(s_{a,0}-\bar{s}_a\right)2^{-h_t/H_s},
$$

where $H_s=5$ years provisionally. The trailing 20-year window is October 2006 through September 2026, with 240 observed monthly OAS values for each sleeve. Median OAS is 17.9872bp for Short Term Bond and 48.0996bp for US Aggregate. This is a separate optional spread sensitivity, not an adopted equilibrium choice. The spread half-life is independent of the Treasury rate half-life.

Each return case is crossed with the 3/5/8-year Treasury half-life scenarios. There are 24 sleeve/scenario/case paths in total, each containing 480 monthly returns over 40 years.

## Compounding And Attribution

Annual returns compound twelve monthly returns. Annualized cumulative returns for horizon $H$ years are:

$$
g_{a,H} = \left[\prod_{t=1}^{12H}\left(1+R_{a,t}\right)\right]^{1/H}-1.
$$

These are geometric annualized returns for deterministic paths, not expected geometric returns under uncertainty. No volatility drag adjustment is introduced without a stochastic model or a separately documented convention.

Monthly return components sum exactly to monthly return. Annual output includes both arithmetic component sums and compounded contributions. For component $k$, let $c_{k,t}$ be its monthly contribution and $W_{t-1}$ wealth accumulated since the start of that year:

$$
A_{k,\mathrm{year}} = \sum_{t\in\mathrm{year}}W_{t-1}c_{k,t},
\qquad W_0=1,
\qquad W_t=W_{t-1}(1+R_t).
$$

Compounded contributions sum exactly to the annual return. This is chronological wealth-weighted attribution, not stand-alone compounding of each component. Arithmetic columns ending `_sum` must not be mistaken for additive attribution of the compounded return; additive columns end `_compounded_contribution`.

## Numerical Research Snapshot

Base Treasury half-life, constant spreads and zero credit losses:

| Sleeve | 1Y Annualized | 10Y Annualized | 30Y Annualized | 40Y Annualized |
| --- | --- | --- | --- | --- |
| Short Term Bond | 5.3276% | 4.6541% | 4.1350% | 4.0380% |
| US Aggregate | 6.3594% | 5.6810% | 5.1581% | 5.0603% |

Initial projected yield declines produce a positive rate-price contribution. This is one reason near-term return can exceed initial yield. The resulting path remains before assumed losses and fees and subject to all model approximations.

At 30 years, the median-spread sensitivity gives 4.1892% and 5.2597%, respectively. Under constant spreads, the 10bp annual-loss sensitivity gives 4.0313% and 5.0534%; the 25bp sensitivity gives 3.8759% and 4.8966%. These numerical alternatives illustrate sensitivity, not a recommendation to adopt a particular loss or spread assumption.

## Historical Diagnostics

Use beginning-month observed yield and durations, together with subsequently realized Treasury and OAS changes. Do not use end-period duration or yield to calculate beginning-period carry. No historical residual is fitted back into the forecasts.

Treasury node observations are selected on the last common daily curve date in each month. Different nodes are not independently filled from different dates. Analytics are observed within seven days of month-end; actual index returns are matched by calendar month. Both beginning- and end-month inputs and adjacent months are required. Missing months are excluded, not bridged. Differences in source close times remain a diagnostic limitation.

| Sleeve | Comparable Months | Monthly RMSE | Mean Observed Minus Model | Correlation |
| --- | --- | --- | --- | --- |
| Short Term Bond | 288 | 7.1180 bp | 1.6480 bp | 0.9864 |
| US Aggregate | 288 | 27.1867 bp | 1.5497 bp | 0.9809 |

Comparable period: October 2002 through September 2026, determined by joint analytics availability rather than filling the requested 30-year window.

Stress-year diagnostic results:

| Sleeve | Year | Observed Return | Modeled Return |
| --- | --- | --- | --- |
| Short Term Bond | 2008 | 4.9728% | 5.1289% |
| Short Term Bond | 2022 | -3.6867% | -3.8770% |
| US Aggregate | 2008 | 5.2399% | 7.2202% |
| US Aggregate | 2022 | -13.0103% | -13.4580% |

These are explanatory diagnostics using realized shocks, not tests of yield forecasting skill, out-of-sample validation or point-in-time backtests. US Aggregate's 2008 discrepancy is a clear caution against treating aggregate first-order exposure as a complete option/sector model. Bias and residuals may reflect roll-down, convexity, trading/rebalancing, timing, options or proxy error; they must not be relabeled as credit losses or alpha without evidence. Calendar-year returns are calculated only when all twelve diagnostic months exist.

## Reproduction And Audit

Run inside the activated `my_env` environment:

```powershell
python main.py --task bond-returns
```

The command uses the latest eligible archived curve projection, normalized analytics and benchmark history under `data`. It uses the archive's observation cutoff; changing `--start` or `--end` does not recut those sources. Refresh upstream inputs and projections to change the forecast endpoint.

Formal reproduction can pin sources:

```powershell
python main.py --task bond-returns --curve-bundle data/20261007T042413_curve-projection_f55f3b45 --analytics-bundle data/20261007T045416_440bc4a1 --history-bundle data/20261007T044858_c7a75489
```

`--return-settings` specifies an alternative research settings file. The implementation refuses nonmonthly frequency. It validates source-file hashes, curve settings, benchmark identity, reviewed analytics mappings, units, duplicate months, complete projection grids and observation freshness. Different analytics coverage remains visible. Existing readiness flags and the other four sleeves are not silently changed.

Code: `cma_curve/bond_returns.py`. Assumptions: `return_settings.json`. Tests: `tests/test_bond_returns.py`.

The inspected run is `data/20261007T051346_bond-returns_9d6cd64a`, containing:

- `monthly_return_paths.csv`: monthly returns, wealth, inputs and four return components.
- `annual_return_paths.csv`: annual compounded returns and component attribution.
- `annualized_returns.csv`: 1/5/10/20/30/40-year annualized returns for every scenario.
- `starting_inputs.csv`: endpoint yields/durations/OAS, spread-window coverage and proxy weights.
- `historical_diagnostics.csv`: observed/model monthly returns and residuals.
- `historical_diagnostic_metrics.csv`: comparable coverage, bias, RMSE and correlation.
- `historical_diagnostic_years.csv`: complete calendar-year comparisons and annual error diagnostics.
- `run_summary.md` and `manifest.json`: narrative, settings, source identities and output hashes.

Validation: 87 project tests pass, including 16 return-engine tests covering signs, units, no double spread carry, losses applied once, compounding, exact annual attribution, missing/stale inputs, gap exclusion, lagged analytics, duplicate months, source checksums, an end-to-end archive fixture and changed-settings rejection.

The first automation run outside an activated conda environment encountered a native NumPy correlation-library loading failure. Running with the environment's `Library/bin` on PATH resolved it. No dependency replacements or global environment edits were made; run the user commands in the existing activated `my_env` terminal.

## Remaining Review Decisions

Approve or replace rate-node proxy weights, the fixed yield-basis residual and constant-duration convention. Decide whether explicit roll-down, compatible convexity or sector/key-rate exposures are needed before publishing US Aggregate. Establish portfolio-level credit-loss and fee assumptions. Choose spread anchors and convergence behavior rather than treating the sensitivity case as approved. Only then promote these research paths to official expected-return assumptions.

## Source

[Bloomberg Fixed Income Index Methodology, January 2026, duration, convexity and key-rate duration sections](https://data.bloomberglp.com/professional/sites/10/Bloomberg-Index-Publications-Fixed-Income-Index-Methodology.pdf). Bloomberg defines OAD against par-curve shifts and describes key-rate exposures for nonparallel movements; this implementation's fixed node weights are explicitly simpler proxies.
