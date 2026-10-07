# TIPS Real Yield Input Investigation

Date: October 7, 2026. Status: provisional approximation authorized by the user; not a final expected-return assumption.

## Decision

Use Bloomberg's generic 5-year TIPS yield, `USGGT05Y Index / PX_LAST`, as a fixed-tenor proxy for the real yield of the Bloomberg TIPS 1-10Y sleeve (`LTI1TRUU Index`). Use `INDEX_OAD_TSY` as an explicitly provisional duration proxy. Do not mark either proxy as an independently verified index real analytic.

The September 30, 2026 index average maturity is 4.7557 years. This supports a simple 5-year benchmark proxy but does not establish exact equivalence to the index's market-value-weighted real yield. Average maturity and duration are distinct quantities.

## Investigation And Evidence

Bloomberg's January 2026 methodology distinguishes real yield and real duration. Its glossary describes real duration as sensitivity of real prices to real yields, but this does not identify the API field for this particular index.

Live API field searches covered real yield, real duration, index inflation and index ISMA. Field information and reference/historical requests then tested the following candidates on `LTI1TRUU Index`:

- `YLD_WITHOUT_INFLATION_MID` and `YLD_WITHOUT_INFLATION_BID`: documented inflation-linked bond calculations; no index observations returned.
- `INFLATION_ADJ_DUR_MID`: documented inflation-adjusted bond duration; no index observations returned.
- `INDEX_ISMA_YIELD` and `INDEX_ISMA_DURATION`: no observations returned.
- `INDEX_YTM_FLAT` and `INDEX_YTM_CURVE`: loan/floating-rate-oriented documentation; no observations returned.
- `INDEX_REAL_YIELD` and `INDEX_REAL_DURATION`: no usable field definition or observations returned; these guessed identifiers were rejected, not adopted.
- `WEIGHTED_AVERAGE_MATURITY_YEARS`: documented index market-value-weighted average maturity; current and historical values returned.

No suitable directly documented index real-yield field was established under this connection. This is not proof that Bloomberg offers no such field through another identifier, product or entitlement. Generic index YTW/YTM remain unverified as real yields. The available generic TIPS index YTW of approximately 5.1393% at September month-end is not used as real carry, nor is an arbitrary inflation assumption subtracted from it.

The live benchmark metadata identified `USGGT05Y Index` as `US Generic Govt TII 5 Yr` and `USGGT10Y Index` as `US Generic Govt TII 10 Yr`. The 5-year input is a generic benchmark bond yield, not a fitted par or zero-coupon rate.

## Observations

| Input | September 30, 2026 | Monthly Observations | First Date |
| --- | --- | --- | --- |
| 5-year real yield proxy | 2.6985% | 351 | July 31, 1997 |
| Index OAD duration proxy | 3.5494 years | 333 | January 29, 1999 |
| Index average maturity | 4.7557 years | 333 | January 29, 1999 |

Requested window: October 1, 1996 through September 30, 2026. Shorter available histories are retained without backfilling. Values above are historical endpoint observations, not October 7 reference quotes.

## Return Specification

Rates are stored as decimals after conversion from Bloomberg percent units. Durations and maturities are stored in years.

$$
y_t^{R,\mathrm{proxy}} = 0.01\,\mathrm{PX\_LAST}_t(\mathrm{USGGT05Y})
$$

A future first-order nominal USD return approximation is:

$$
R_t^N \approx y_t^{R,\mathrm{proxy}}\Delta t
+ \pi_t^{\mathrm{CPI}}\Delta t
- D_t^{R,\mathrm{proxy}}\Delta y_t^{R,\mathrm{proxy}}.
$$

Here inflation and yield are annualized decimal rates, $\Delta t$ is the period in years, and the yield change is a decimal change over that period. This equation specifies the intended approximation; the new module downloads inputs only and does not yet compute forecasts. CPI inflation is a separate input and must not be silently replaced by PCE inflation. Yield convergence also requires a separately specified real-yield anchor; this investigation does not set one.

## Limitations And Controls

- A single 5-year benchmark does not capture the index's full 1-10Y composition or nonparallel real-curve moves.
- `INDEX_OAD_TSY` is not independently verified here as real-yield duration. Its use remains an approximation, with sensitivity analysis required before final return approval.
- Neither yield nor duration is inferred from the other. Maturity is diagnostic only.
- No inflation is added to the real-yield input itself. Inflation enters nominal returns separately, preventing double counting.
- The first-order return specification omits roll-down, convexity, turnover/rebalancing, inflation-indexation lag, seasonality and the TIPS deflation floor.
- Missing data are not filled. Duplicates, nonfinite values, nonpositive maturity/duration and endpoints older than seven days are rejected. Negative real yields are valid.
- Current-vintage downloads are not point-in-time eligible research datasets.
- Exact-analytics readiness flags in `bond_assets.json` remain unchanged. Proxy inputs have a separate archive and explicit proxy flags; they must not silently pass an exact-analytics readiness check.

## Reproduction

Run the monthly proxy downloader in the Bloomberg-enabled environment:

```powershell
python main.py --task tips-inputs
```

Implementation: `cma_curve/tips_inputs.py`. Default window remains 30 years. `--start`, `--end` and `--output` can override it. The downloader saves `observations.csv`, `coverage.csv`, a hashed `manifest.json` and `run_summary.md` beneath the project's `data` directory.

Evidence archives:

- `data/20261007T050208_tips_research`: raw field search responses and candidate definitions.
- `data/20261007T050254_tips_probe`: explicit field definitions, current reference results and available history.
- `data/20261007T050432_5c17a6c3`: normalized monthly proxy inputs and coverage.

Validation: 71 project tests pass, including four proxy-specific tests for unit conversion, negative real yields, no missing-month filling, duplicate rejection, missing inputs and stale endpoints. Live proxy histories and September month-end values were inspected.

## Sources

- [Bloomberg Fixed Income Index Methodology, January 2026, Appendix 7](https://data.bloomberglp.com/professional/sites/10/Bloomberg-Index-Publications-Fixed-Income-Index-Methodology.pdf).
- Bloomberg API field definitions and responses retained in the evidence archives above.
- [Federal Reserve TIPS Yield Curve and Inflation Compensation](https://www.federalreserve.gov/data/tips-yield-curve-and-inflation-compensation.htm): a potential later replacement using an estimated real curve; not used by this fixed-tenor implementation.
