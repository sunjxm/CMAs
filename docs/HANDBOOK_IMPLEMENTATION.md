# Handbook-Informed Fixed-Income Extensions

Date: October 7, 2026. Status: research implementation, not approved CMAs.

## Summary And Scope

The JPM methodology review led to three extensions: composition-aware credit inputs, a coupon/aging/normalization holding-return comparison, and a USD hedge-carry calculator. These extend the research framework without silently replacing the existing index return assumptions.

| Extension | Implemented | Still Outstanding |
| --- | --- | --- |
| Credit losses | Current weighted member acquisition, rating coverage review, matched PD/recovery calculator | Complete issuer-type/rating coverage, approved recovery inputs, historical endpoint composition |
| Spread anchors | Segment-weighted historical spread calculator, explicit duration-ratio sensitivity, CSV import | Segment spread histories and target weights; no composition-aware anchor is fabricated |
| Carry and roll-down | QuantLib par-to-discount bootstrap and annual rolling Treasury holding returns | Mapping to actual credit-index sector/key-rate exposures and mortgage options |
| Global USD hedging | Monthly weighted local-return plus cash-differential approximation, CSV import | Complete currency weights, foreign bond returns and foreign cash anchors |

The existing `bond-returns` outputs remain unchanged. The other four sleeves have not been promoted to completed expected-return forecasts. The selected HLW median20 Treasury anchor remains in place. The handbook's distinction between cycle-neutral cash and economic r-star still requires an explicit assumption review; it is not resolved by these extensions. Half-life convergence remains different from finite-time normalization.

## Current Composition Acquisition

`cma_curve/composition_inputs.py` requests Bloomberg `INDX_MWEIGHT` and then bounded batches of constituent reference fields. It archives raw weights, field definitions, identifiers, S&P issue ratings, industry sectors and issue currency. A weighted list is accepted for research only when its nonnegative weights sum to one within rounding tolerance and identifiers are unique. No missing list is reconstructed by equally weighting an unweighted member list.

The successful weighted lists contain:

| Sleeve | Weighted Members | Weight Coverage |
| --- | --- | --- |
| Short Term Bond | 2,141 | Approximately 100% |
| High Yield | 1,949 | Approximately 100% |
| EM USD Aggregate | 2,161 | Approximately 100% |

Across these lists, 6,201 unique member identifiers were queried in batches of 200. US Aggregate and Global ex-USD returned no usable weighted list. Separate exploratory membership requests returned 2,500 members each; these cannot establish completeness and were not used to invent weights.

**These are October 7 current-vintage snapshots, not September 30 weights.** They must not be inserted into the September forecast as though they were historical endpoint observations. Bloomberg's identifier resolver returned CUSIPs for member identifiers, including internal aliases; returned identifiers and missing fields are retained. Full issuer classification has not been verified. Coarse industry-sector classification is not equivalent to index sector classification.

## Corporate Default And Recovery Review

The reproducible illustrative calibration uses S&P's March 27, 2025 study, Table 4, page 9: weighted annual global corporate default frequencies over 1981-2024. This is a pinned historical vintage, not a claim that it is the latest study. The source frequencies and their units are recorded in each credit-review manifest.

Issue ratings are aggregated to broad S&P categories. Unsupported, unrated and defaulted labels are not silently assigned a zero default probability. Government-category exposures are kept separate; the corporate default table is not applied to EM sovereign debt. Other government-related issuers can still be misclassified by coarse industry data, so all current loss contributions remain proxies.

For explicitly supplied, fully covered segments, annual expected loss is approximated as:

$$
\ell_a = \sum_j w_{a,j}\,PD_j\,(1-RR_j).
$$

All inputs are decimals. Segment weights must cover the whole portfolio and sum to one, including any government/securitized exposures with their separately specified assumptions. The calculator does not automatically renormalize a corporate-only subset to 100%.

The current review uses 20%, 40% and 60% recovery sensitivities, not estimated or approved recovery rates. At 40% assumed recovery:

| Sleeve | Covered Corporate Weight | Unresolved Corporate Weight | Other/Unresolved Weight | Covered Annual Loss Contribution |
| --- | --- | --- | --- | --- |
| Short Term Bond | 22.24% | 0.33% | 77.42% | 1.16 bp |
| High Yield | 94.78% | 5.22% | Approximately 0% | 185.99 bp |
| EM USD Aggregate | 27.00% | 19.56% | 53.44% | 8.00 bp |

**These are contributions from the covered subset, not full-index expected losses.** The full-portfolio loss field is deliberately unavailable for every sleeve. Missing ratings and noncorporate credit populations require separate assumptions. S&P's corporate study is issuer-weighted; applying those frequencies to issue ratings and market-value weights introduces population and weighting differences. The simple PD-times-LGD formula also omits par-to-market-value conversion, price recovery conventions, migration, index exits and distressed exchanges. These limitations preclude adopting the numbers as official return deductions.

## Composition-Aware Spread Anchors

`spread_anchor_by_segment` computes a target-weighted anchor from supplied segment history. The default leaves each historical spread unchanged:

$$
\bar{s}_a = \sum_j w_{a,j}^{\mathrm{target}}\bar{s}_j.
$$

For review, a separate explicit duration-ratio sensitivity is:

$$
\bar{s}_a^{(p)} = \sum_j w_{a,j}^{\mathrm{target}}\bar{s}_j
\left(\frac{D_j^{\mathrm{target}}}{\bar{D}_j}\right)^p,
\qquad p\in\{0,1\}.
$$

The handbook motivates duration adjustment but does not fully specify its quantitative rule. Therefore, the power-one ratio is **our illustrative sensitivity**, not a claimed reproduction of JPM's implementation. It must not be adopted solely because the handbook mentions duration adjustments. Both alternatives are exported when a complete spread-segment CSV is supplied. No segment history or target composition has yet been fabricated or auto-approved.

## Coupon, Aging And Normalization Repricing

`cma_curve/holding_returns.py` uses QuantLib 1.43, installed in `my_env` and registered as the project's optional `pricing` dependency. It bootstraps positive discount factors from the projected par quotes and does not discount cash flows by treating par yields as zero rates.

Conventions are explicit research choices: simple-rate deposit helpers for tenors below one year; semiannual fixed-rate par bonds at longer tenors; Actual/365 Fixed; zero settlement lag; unadjusted dates; log-linear discount interpolation; no extrapolation. They do not reproduce every Treasury quote/day-count convention.

For each of the existing 3/5/8-year rate half-life scenarios and each year of the 40-year projection, the module buys a new synthetic 2-, 5- or 10-year par Treasury bond. It collects the year's coupons and sells the aged bond after one year. Coupon cash is not reinvested within that year; proceeds are reinvested into a new constant-tenor bond for the next year.

$$
R = \frac{C+P_1-P_0}{P_0}.
$$

The return is decomposed without overlap:

$$
R = \underbrace{C/P_0}_{\mathrm{coupon}}
+ \underbrace{(P_1^{\mathrm{frozen}}-P_0)/P_0}_{\mathrm{aging\ under\ unchanged\ curve}}
+ \underbrace{(P_1-P_1^{\mathrm{frozen}})/P_0}_{\mathrm{normalization}}.
$$

The frozen curve retains the original constant-maturity par quotes at the sale date. Its aging price effect includes roll-down and can include coupon/accrual schedule effects; it is not labeled pure roll-down in every case. Sale-date coupons are counted as received cash, not again in sale value. The initial synthetic bond must reprice to par. QuantLib's global evaluation date is restored after each calculation, including errors.

There are 360 annual holding-return observations: three tenors times three rate scenarios times 40 years. Coupon, aging and normalization contributions sum to each holding return. Annualized cumulative returns are calculated from those holding returns.

**Do not add yield/12, a separate duration shock or another roll-down allowance to these holding returns.** Those would overlap with the repriced cash flows. The Treasury comparison is not an exact replica of Short Term Bond or US Aggregate and does not yet replace their first-order benchmark paths. Credit spreads, sector weights, key-rate exposures and mortgage options need separate incorporation.

## Global ex-USD Hedge Approximation

`cma_curve/global_hedge.py` consumes monthly currency weights and local bond return paths, plus beginning-period annualized USD and foreign cash rates. The approximation is:

$$
R_t^{USD,h} \approx \sum_c w_{c,t}
\left[R_{c,t}^{\mathrm{local}} + (r_t^{USD}-r_t^c)/12\right].
$$

All rates and returns are decimals. Currency weights must sum to one each month. A higher USD cash rate gives positive USD hedge carry for a foreign asset, and vice versa. The model rejects duplicate currency-month pairs, missing months, inconsistent USD cash rates and incomplete weight totals. Omitted currencies are not rescaled away.

This is the handbook's resource-efficient cash-differential proxy, not an exact replication of FX-forward or benchmark hedge P/L. It omits cross-currency basis, actual forward quotes, hedge slippage, residual FX exposure and fees. Hedging removes most currency exposure, not foreign interest-rate exposure. No unhedged currency appreciation forecast is added on top of the hedged-return approximation.

Without complete inputs, the task writes a readiness summary and empty input template and generates **no global return path**. Global yield and duration alone are insufficient.

## Commands And Input Templates

Run in activated `my_env`:

```powershell
python main.py --task composition-inputs
python main.py --task credit-review
python main.py --task holding-returns
python main.py --task global-hedge-review
```

Only `composition-inputs` needs the Bloomberg connection. The remaining tasks consume archived or supplied inputs. `--task all` remains download-only. Current composition retrieval does not become historical merely by passing `--end`.

For another machine, install the pricing dependency:

```powershell
pip install -e ".[pricing]"
```

After completing the generated templates with reviewed inputs:

```powershell
python main.py --task credit-review --loss-segments inputs/loss_segments.csv --spread-segments inputs/spread_segments.csv
python main.py --task global-hedge-review --global-hedge-inputs inputs/global_hedge_inputs.csv
```

Loss-segment columns: `asset_key`, `segment`, `weight_decimal`, `annual_pd_decimal`, `recovery_decimal`, `source`, `reference_date`.

Spread-segment columns: `asset_key`, `segment`, `weight_decimal`, `historical_spread_decimal`, `historical_duration`, `target_duration`, `source`, `reference_date`.

Global hedge columns: `date`, `currency`, `weight_decimal`, `local_return_decimal`, `usd_cash_decimal`, `foreign_cash_decimal`. Cash rates must be beginning-period rates; local returns must cover the indicated monthly period. Actual benchmark currency weights and foreign return assumptions must be provided, not guessed.

Generated loss/spread estimates remain supplied-input research results and do not automatically change return_settings.json or bond_assets.json. Sources can be pinned with `--constituent-bundle` for credit review and `--curve-bundle` for the holding-return comparison. CSV inputs and archive outputs are hashed.

## Evidence And Verification

- `data/20261007T052459_composition-research`: candidate composition field definitions.
- `data/20261007T052559_composition-probe`: successful current member/weight availability probe; preceding invalid-format probe is retained separately as a failed exploratory request.
- `data/20261007T053541_d6360df5`: successful production composition task, all usable weighted lists and raw constituent metadata.
- `data/20261007T053717_3722789d`: inspected credit review and loss/spread templates.
- `data/20261007T053239_holding-returns_74929205`: inspected QuantLib Treasury comparison and attribution.
- `data/20261007T053717_c7933b3d`: global hedge readiness report and input template; no forecast.

All 100 project tests pass, including 13 extension tests for rating mapping, unresolved exposure, complete-weight loss/spread calculations, CSV loss import, hedge sign/units/weights/gaps, no-input readiness, flat-curve holding return, upward-curve aging, rate shocks, par/zero distinction and global evaluation-date restoration. The production composition task and all three review tasks ran successfully.

## Next Required Inputs

For the September 30 forecast, obtain endpoint sector/rating weights for LBUSTRUU and complete currency weights plus local yield/duration breakdowns for LG38TRUH. Resolve HY's missing S&P rating exposures or approve a documented alternative rating treatment. Separate sovereign, government-related and corporate exposures in EM. Obtain matched segment spread histories and PD/recovery populations, and approve recovery and loss conventions before altering official returns.

## Sources

- [JPM Methodology Handbook, pp. 10-13 and 31](https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/portfolio-insights/ltcma/noindex/ltcma-methodology-handbook.pdf).
- [S&P 2024 Annual Global Corporate Default and Rating Transition Study, Table 4, p. 9](https://maalot.co.il/Publications/FTS20250331162126.pdf).
- [QuantLib](https://www.quantlib.org/).
- Bloomberg field definitions, current member lists and reference responses preserved in the evidence archives.
