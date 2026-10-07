# Fixed Income Capital Market Return Assumptions

Prepared October 7, 2026. Status: implementation specification and input registration; asset expected-return calculations are not yet implemented or approved.

## Decisions And Scope

The selected primary research anchor is the median of the latest 20 consecutive quarterly US HLW real-neutral-rate estimates, `hlw_median20`. Latest HLW and latest LW remain diagnostics. The historical curve-shape statistic remains the 30-year mean paired Treasury spread; choosing a median neutral rate does not change the slope estimator to a median.

All six sleeves will report nominal USD returns for rebalanced benchmark portfolios, not buy-and-hold single bonds. Global Aggregate ex USD is hedged to USD. EM debt now uses Bloomberg Emerging Market USD Aggregate, not the originally requested JP Morgan EMBI Global Diversified or local-currency GBI-EM. Expected gross index returns will be reported separately from implementation fees and costs.

## Registered Benchmarks

| Sleeve | Requested benchmark | Model requirements |
| --- | --- | --- |
| Short Term Bond | Bloomberg US Aggregate Government & Credit 1-3Y | US nominal curve, government/credit composition, carry, rate/spread exposure, credit losses |
| US Aggregate | Bloomberg US Aggregate, LBUSTRUU | Treasury, corporate and securitized exposures; effective duration and convexity; mortgage prepayment and option effects |
| Inflation Linked | Bloomberg TIPS 1-10Y | Real yield curve, real duration, CPI-U inflation, indexation conventions and floors |
| High Yield | Bloomberg US Corporate High Yield, LF98TRUU | US nominal curve, broad HY spread history, spread duration, default/recovery and rating migration assumptions |
| Global Bond ex US | Bloomberg Global Aggregate ex USD Hedged | Currency/sector weights, foreign yield curves and spreads, USD hedge carry and rebalancing |
| EM Debt | Bloomberg Emerging Market USD Aggregate, EMUSTRUU | US nominal curve, sovereign/government-related/corporate exposures and spreads, rate/spread exposure and credit losses |

All six supplied tickers are now registered with the Bloomberg Index suffix. On October 7, 2026, the user explicitly approved replacing the original ICE BB-B constrained high-yield benchmark with LF98TRUU, and the original JP Morgan EMBI Global Diversified benchmark with EMUSTRUU. These are benchmark changes, not interchangeable aliases. The configuration preserves the earlier requests and evidence links. No ETF, local-currency EM index, or unhedged global variant is substituted.

| Sleeve | Supplied Bloomberg security | Documentation review |
| --- | --- | --- |
| Short Term Bond | LGC3TRUU Index | Sponsor methodology identifies 1-3 Yr Gov/Credit USD unhedged total return |
| US Aggregate | LBUSTRUU Index | Sponsor listing and prior API metadata identify US Aggregate in USD |
| Inflation Linked | LTI1TRUU Index | Fund-provider benchmark documentation identifies TIPS 1-10Y; sponsor/API check pending |
| High Yield | LF98TRUU Index | Bloomberg US Corporate High Yield; user-approved replacement, not BB-B constrained |
| Global ex-USD Hedged | LG38TRUH Index | Sponsor methodology identifies Global Aggregate ex-USD total return USD hedged |
| EM Debt | EMUSTRUU Index | Bloomberg Emerging Market USD Aggregate; user-approved replacement, not EMBI |

Evidence: [Short-term sponsor methodology](https://assets.bbhub.io/professional/sites/27/01030_20240327.pdf), [US Aggregate and HY sponsor listing](https://www.bloomberg.com/markets/rates-bonds/bloomberg-fixed-income-indices), [TIPS benchmark documentation](https://www.flexshares.com/us/en/individual/funds/tipb), [Global ex-USD sponsor methodology](https://assets.bbhub.io/professional/sites/27/3121_20240410.pdf), [EM sponsor consultation](https://data.bloomberglp.com/professional/sites/27/2024-10-11-Update-on-Consultation-on-Bloomberg-Fixed-Income-Indices.pdf).

The initial live Bloomberg attempt failed because the API at localhost:8194 was unreachable. The subsequent successful six-index metadata archive, public documentation and explicit user approval now support benchmark verification. Benchmark flags are true, while analytics and expected-return assumptions have separate review controls. Ex-USD is a denomination exclusion, not a blanket exclusion of US issuers.

## October 7 Input Implementation And Evidence

The approved benchmark definitions reference data/20261007T044515_53edb1b4/bloomberg_reference.csv and its SHA-256 hash. A successful monthly download is archived in data/20261007T044858_c7a75489, with observations, coverage, adjacent-month total returns and a methodology summary. Five sleeves have 360 monthly levels from October 1996 through September 2026, yielding 359 monthly returns. TIPS has 333 levels from January 1999 through September 2026, yielding 332 returns. No earlier TIPS levels are manufactured. Some histories may include provider backfills; the download does not establish point-in-time index availability.

Field discovery through Bloomberg's API field-definition service is archived in data/20261007T044912_7451b33f. It returned 207 candidate definitions across six searches. The raw candidate history probe is archived in data/20261007T045111_990c638e and contains 14,017 numeric observations across eight fields and six indices. Returned numbers alone do not establish economic applicability or approve a field.

Reviewed nominal mappings now use INDEX_YIELD_TO_WORST in percentage points, INDEX_OAD_TSY in years, INDEX_BLENDED_SPREAD_DUR in years for USD indices, and INDEX_OAS_TSY_BP in basis points. Nominal carry is not automatically set equal to yield-to-worst. The HY yield metric remains labeled yield_to_worst, and EM's spread metric explicitly uses Treasury OAS rather than an EMBI benchmark spread. Generic INDEX_OAS_TSY is in percentage units and is not assigned a basis-point scale; the explicitly basis-point field is selected instead.

Normalized observations and a gap report are archived in data/20261007T045416_440bc4a1. Percent yields are divided by 100, basis-point spreads by 10,000 and durations retained in years. The normalization verifies the raw observation hash and matching benchmark tickers. It consumes only reviewed mappings; unavailable or unverified metrics remain absent. Analytics histories are often shorter than total-return histories, so calibration must use metric-specific coverage and compatible observation dates.

Unresolved inputs remain explicit:

- TIPS generic INDEX_YIELD_TO_WORST and INDEX_YIELD_TO_MATURITY are not approved as real yields. A real-yield definition and real-duration exposure need separate review.
- LG38TRUH returned yield and rate-duration history, but no INDEX_BLENDED_SPREAD_DUR, INDEX_OAS_TSY or INDEX_OAS_TSY_BP history. Underlying foreign-bond yield is not USD-hedged carry, and its duration is not US Treasury duration. Foreign curves, spreads and hedge carry remain separate missing model components.
- INDEX_OAC_TSY values were archived, but their scaling is not yet approved for a second-order return formula. Convexity remains unconfigured.
- Credit-loss rates, spread anchors, migration, carry/roll-down calibration, CPI/PCE assumptions and portfolio exposure weights remain to be specified before expected-return forecasts.

All 67 automated tests pass. The input layer is implemented; expected-return forecasts are not yet generated. Latest source snapshots are not a point-in-time backtest.

## October 7 Investment-Grade Return Implementation

Short Term Bond and US Aggregate now have an offline first-order research return engine. Run `python main.py --task bond-returns`; editable draft assumptions are in `return_settings.json`. Full formulas, attribution, reproduction, diagnostics and limitations are in [INVESTMENT_GRADE_RETURNS.md](INVESTMENT_GRADE_RETURNS.md). The inspected archive is data/20261007T051346_bond-returns_9d6cd64a.

Baseline paths use fixed endpoint durations, explicit judgmental Treasury-node weights and yield-based carry, with constant OAS and zero losses. They are gross scenario approximations, not approved expected-return CMAs. Optional historical-median spread convergence and annual-loss sensitivities remain separate. No roll-down, convexity, mortgage-option dynamics or fitted residual correction is included.

There are 24 sleeve/scenario/case paths over 40 years, with monthly attribution, annual compounding and annualized cumulative returns. Historical diagnostics compare observed returns with realized-shock approximations over 288 compatible months; they are not forecasting backtests. All 87 tests pass. Other sleeves and the remaining approval decisions stay outstanding. The earlier implementation entries above are historical snapshots, superseded where noted by this entry and docs/TIPS_INPUTS.md.

## Implemented Shared Curve Projection

The pipeline now projects each official Treasury par node monthly over 40 years:

$$
y_m(h) = a_m + \left[y_m(0)-a_m\right]2^{-h/H_m}
$$

Here maturity $m$ differs from forecast horizon $h$. Rates use decimals; horizons and half-lives use years. The provisional base half-life is five years, with three- and eight-year sensitivity paths. These settings are judgments, not estimated parameters. They do not assert that different maturities truly converge at the same speed.

Horizon zero reproduces the common-date starting curve. At one half-life the initial gap halves. The anchor is approached asymptotically, not reached at a preset terminal year. Source checksums and settings must match the anchor-review archive; changing the selected candidate requires a fresh review run before projection.

This step projects par nodes only. It does not bootstrap discount factors, interpolate a full curve, price securities, apply a market overlay, or predict index returns. Real and foreign curves remain separate missing components, not transformations silently inferred from the US par curve.

## Return Model Design

For a resource-efficient first implementation, use monthly index analytics and an explicitly approximate carry-and-risk model. Validate that approximation against observed benchmark total returns before use. A diagnostic decomposition for a nominal credit sleeve is:

$$
R_{a,t+1} \approx c_{a,t}\Delta t + \rho_{a,t} - D_{a,t}^{r}\Delta y_{a,t} - D_{a,t}^{s}\Delta s_{a,t} - \ell_{a,t}\Delta t
$$

Here $c$ is modeled annual carry, $\rho$ is the period's roll-down contribution, $D^r$ is rate duration, $D^s$ is spread duration, $\Delta y$ is the relevant curve shock, $\Delta s$ is the credit-spread shock, and $\ell$ is an annual expected credit-loss rate. For monthly steps $\Delta t=1/12$. Yield-to-worst is an input, not automatically equal to carry or expected return. Default losses must be represented exactly once, whether in survival/cash-flow modeling or a separate expected-loss adjustment.

For nonparallel curve moves, prefer key-rate durations and separate curve-node shocks. A single duration is a documented simplification, not a maturity mapping: duration is not maturity. Convexity requires compatible analytics and shock conventions; US Aggregate and callable credit may need option-adjusted models and scenario-dependent exposure. If cash flows are explicitly aged and repriced, roll-down is already captured and must not be added again.

The US Aggregate should ultimately be modeled by Treasury, credit, and securitized sectors or an equivalent validated decomposition. A one-bond proxy cannot faithfully capture its mortgage option risk. An aggregate approximation may be used for diagnostics if the error and limitations are documented. [Bloomberg methodology](https://data.bloomberglp.com/professional/sites/10/Bloomberg-Index-Publications-Fixed-Income-Index-Methodology.pdf)

TIPS nominal returns need real returns and realized/assumed CPI inflation. A high-level consistency identity is:

$$
1+R_{\mathrm{TIPS}}^{\mathrm{nom}} = \left(1+R_{\mathrm{TIPS}}^{\mathrm{real}}\right)\left(1+\pi_{\mathrm{CPI}}\right)
$$

This identity is a modeling abstraction, not a replacement for indexation lag, instrument-level floors and index rules. TIPS principal is linked to CPI-U; the policy anchor uses PCE, so substituting PCE without an explicit CPI/PCE assumption is not acceptable. [TreasuryDirect TIPS definition](https://www.treasurydirect.gov/marketable-securities/tips/)

For global USD-hedged bonds, project foreign bond returns and FX-forward hedge profit/loss consistently. Hedge carry depends on currency-specific short-rate differentials, forward pricing and basis; hedging does not convert foreign duration exposure into US duration. The exact hedged benchmark's index rules determine hedge ratios, timing and residual FX effects. Currency weights, foreign curves and hedge assumptions must be populated before forecasting this sleeve.

HY and EM USD Aggregate need separate spread anchors and expected credit-loss assumptions. Observed spreads contain risk and liquidity compensation as well as expected losses; they are not all excess return. LF98TRUU requires assumptions for the broader HY rating mix rather than BB-B-only losses. EMUSTRUU requires sovereign, government-related and corporate exposures rather than a sovereign-only EMBI proxy. It remains USD-denominated, not an EM local-currency currency-return model. Actual sector and rating weights must be downloaded and verified before calibration. Earlier ICE/JP Morgan selections are retained in the development log as superseded requests.

## Data Acquisition And Review

`bond_assets.json` registers benchmark identifiers, currency exposure, model families and analytics mappings. First confirm each benchmark's name, maturity/rating filter, total-return field and currency/hedging conventions using metadata plus Bloomberg index documentation. Set the benchmark's `verified` flag only after review. Metadata retrieval alone never flips that flag.

Each analytics mapping needs the Bloomberg field, units and a separate `verified` flag. Required metric names appear in the offline readiness report. Example mapping structure, with a deliberately nonfunctional placeholder field:

```json
"analytics": {
  "rate_duration": {"field": "REPLACE_WITH_VERIFIED_FIELD", "units": "years", "verified": false}
}
```

Field mnemonics and the index provider's definitions must be checked in Bloomberg FLDS before use. OAS uses basis points; yields use percentage points; durations use years; convexity units must match the pricing convention. Never substitute modified duration for effective duration, nominal yield for real yield, or spread-to-benchmark for OAS without a documented model change.

Monthly total-return index levels are downloaded for the existing 30-year calibration window where available. Historical monthly returns require adjacent calendar months. Missing months are not bridged or filled; histories are not extended before index coverage. Shorter availability, backfilled history and methodology changes need explicit review. Current metadata is not a historical observation at the calibration endpoint. Index histories are for validation and risk diagnostics, not historical-average-return anchors.

Annual return paths, 10/20/30/40-year annualized cumulative returns, and an attribution table are the planned outputs. For a deterministic path, annualized cumulative return is:

$$
g_H = \left[\prod_{t=1}^{12H}\left(1+R_t\right)\right]^{1/H}-1
$$

This is not automatically an expected geometric return under uncertainty. Arithmetic versus geometric expectations and volatility adjustments require separate decisions. Fees, trading costs and taxes must be explicit, not embedded in an unexplained residual.

## Run Order

```powershell
python main.py --task anchor-review
python main.py --task curve-projection
python main.py --task asset-review
python main.py --task asset-metadata
python main.py --task asset-history
python main.py --task asset-analytics
python main.py --task asset-analytics-probe
python main.py --task asset-analytics-normalize
```

After all identifiers and fields are reviewed:

```powershell
python main.py --task asset-history --assets us_aggregate
```

The history step intentionally refuses unverified benchmarks. `--task all` retains its existing download-only behavior and does not silently run projections or asset forecasts. Results and Markdown summaries are archived under `data/` in new folders. The reusable Word converter includes this methodology file automatically; refresh review copies after edits. Formal reproduction should pin the exact anchor-review bundle with `--review-bundle` and retain all source archives.
