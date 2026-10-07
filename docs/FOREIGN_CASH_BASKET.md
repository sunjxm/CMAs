# Foreign Cash Basket And USD Hedge Carry

Date: October 7, 2026. Status: implemented research engine; foreign assumptions not yet calibrated.

## Scope

The resource-efficient model estimates a foreign cash basket and an additive USD hedge-carry overlay. It does not require foreign bond-yield histories or constituent-level bond analytics. It does not forecast foreign bond price changes, losses or duration exposure, and it does not replace the Global ex-USD total-return model.

The user requested EUR, CNY, JPY, GBP, CAD, AUD and CHF as individual components. Remaining currencies are combined into Other. Currency denomination weights are used, not country-of-issuer or GDP weights.

## Source Weights And Explicit Approximation

Weights come from the September 30, 2026 workbook review, `data/20261007T055252_78d41204`, with user-confirmed observation date. The raw displayed currency weights total 99.99%.

| Bucket | Model Weight |
| --- | --- |
| EUR | 41.26% |
| CNY | 20.02% |
| JPY | 13.99% |
| GBP | 7.19% |
| CAD | 5.05% |
| AUD | 2.82% |
| CHF | 0.98% |
| Other | 8.69% |

Named currencies retain their raw weights and total 91.31%. Other combines the remaining displayed weights (8.68%), including Unclassified (0.15%), plus the 0.01 percentage point rounding residual. This is a documented modeling allocation, not a recovered exact Bloomberg weight. The workbook importer remains unchanged and continues to preserve raw residuals. The residual allocation occurs only in this basket model. No named currency is renormalized.

The Other cash assumption must represent the residual currency mix, not automatically the US cash rate. A practical initial calibration can combine available smaller-currency cash proxies and explicit assumptions for missing exposures. The source/rationale field must identify that approximation. Fixed September weights are a baseline held through the projection and reviewed annually, not a 40-year composition forecast.

## US Link And Foreign Anchors

The engine consumes the existing selected `hlw_median20` projection for `BC_1MONTH`, preserving its starting rate, anchor, 40-year monthly grid and 3/5/8-year half-life cases. In the current archive, starting US cash is approximately 4.02%, its long-run anchor approximately 3.1881%, and the underlying inflation assumption is 2.20%. These values are read from verified archives, not repeated as editable settings.

The one-month Treasury node is a cash-return proxy, not the federal funds policy rate or an exact FX-forward funding rate. Foreign starting rates should use comparable short-term money-market proxies where available. If an overnight or policy rate is used, document the convention/basis difference.

For currency or bucket c:

$$
a_c=a_{USD}+(\pi_c-\pi_{USD})+\delta_c.
$$

Here a is an annual nominal cash anchor, pi is the long-run inflation assumption, and delta is an explicit real-cash/convention adjustment. Foreign inflation definitions should be comparable to the US input, or differences should be documented and reflected in adjustments. Anchors are intended as cycle-average nominal cash assumptions. Neutral policy estimates alone are not automatically cycle-average cash returns.

The editable template proposes zero real-cash adjustments for simplicity. These are provisional judgments, not estimates or established cross-country equalities. Foreign inflation anchors and current cash rates remain blank until supplied, so no production numbers are invented.

## Convergence And Hedge Overlay

Each bucket uses the same half-life as the corresponding US scenario:

$$
r_c(t)=a_c+[r_c(0)-a_c]2^{-t/h}.
$$

The weighted foreign cash rate and annualized USD hedge carry are:

$$
r_F(t)=\sum_c w_cr_c(t),\qquad
H_t=r_{USD}(t)-r_F(t)+b-k.
$$

Here b is a signed additive hedge-return basis adjustment and k is a nonnegative implementation-cost deduction. Both default to zero as explicitly provisional settings. The first-order monthly overlay is:

$$
R_{t+1}^{hedge,overlay}\approx H_t/12.
$$

Beginning-period rates are used: horizon-zero September cash funds the October return month. Ending-period cash is not substituted. Hedge carry may be positive or negative. Add the overlay to an appropriate local-bond monthly return before compounding. Do not compound hedge carry alone as a standalone bond investment, or add it to a return series that already includes USD hedging.

The engine reports horizon-average annualized hedge carry in basis points, not a CAGR. Optional foreign-basket anchor shifts of -50/0/+50bp are crossed with the existing rate half-life scenarios. They change the foreign anchor, not the starting cash rate; they are illustrative sensitivities, not confidence intervals. Higher foreign cash anchors reduce USD hedge carry.

## Inputs And Commands

Code: `cma_curve/foreign_cash.py`. Settings: `foreign_cash_settings.json`. Editable assumptions: `inputs/foreign_cash_assumptions.csv`.

```powershell
python main.py --task foreign-cash
```

On the first run, the engine creates the assumptions CSV only if absent. Existing input files are never overwritten. Each of the eight rows requires:

- `bucket`: one of the seven named currencies or Other.
- `current_cash_decimal`: annual cash rate as a decimal (0.025 means 2.5%).
- `current_cash_asof`: September 30, 2026 for the current workbook/curve.
- `inflation_anchor_decimal`: long-run inflation as a decimal.
- `real_cash_adjustment_bps`: signed adjustment in basis points, initially zero.
- `source`: source references and assumption rationale for cash and inflation/real-cash anchors.
- `note`: optional convention or proxy details.

Different input or source archives can be pinned explicitly:

```powershell
python main.py --task foreign-cash --foreign-cash-inputs inputs/foreign_cash_assumptions.csv --foreign-cash-settings foreign_cash_settings.json --workbook-bundle data/20261007T055252_78d41204 --curve-bundle data/20261007T042413_curve-projection_f55f3b45
```

The engine verifies source hashes, matching observation dates, unique complete bucket coverage, finite numeric inputs and contiguous monthly US paths. It inherits the inflation input from the selected anchor review, rather than hardcoding a foreign/US inflation spread. Latest-source discovery is convenient, but pin archives for a formal reproducible run. Unknown or mismatched workbook dates are rejected.

## Outputs And Verification

First live run: `data/20261007T130543_7d38a78e`, status `missing_inputs_no_projection`. It generated the eight-row editable input CSV and archived bucket coverage, currency mapping, templates, a LaTeX run summary and hashes. No hedge forecast was generated because current cash and inflation anchors are missing. No bond-return settings changed.

Once inputs are complete, a run also produces per-bucket paths in `observations.csv`, aggregate `cash_and_hedge_paths.csv`, beginning-period `monthly_hedge_overlay.csv`, and `horizon_average_hedge_carry.csv`. Source/config/input/output hashes and the unchanged research status are retained.

All 113 project tests pass, including eight new tests for separate AUD/CHF weights, residual allocation, bad weights, missing inputs, duplicate buckets, observation-date mismatch, anchor arithmetic, hedge sign, basis/cost conventions, sensitivities, half-life, negative cash rates, monthly grid, source hashes, first-month timing and preserving editable inputs. A fully supplied synthetic fixture exercises the numerical pipeline; those fixture assumptions are not market data and were not inserted into live inputs.

## Outstanding Calibration

Obtain reviewed September 30 short-term cash rates for the seven currencies and an Other proxy. Select documented foreign inflation and real-cash adjustments, and review basis/cost sensitivities. This is a small input table, not a requirement to estimate seven separate neutral-rate systems or collect 30 years of local bond yields.

The current implementation does not fetch or silently choose Bloomberg foreign cash identifiers. Identifier/field verification and calibration are the next data step. Adding these assumptions does not by itself complete foreign bond-rate normalization or the Global ex-USD total-return forecast.

## Sources

- User-supplied September 30 Bloomberg workbook and its hashed input-review archive.
- Existing selected US cash projection and anchor-review archives.
- [JPM LTCMA Methodology Handbook, page 31](https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/portfolio-insights/ltcma/noindex/ltcma-methodology-handbook.pdf): projected cash differentials as a long-run hedge-cost proxy.
- [BIS: Covered interest parity lost](https://www.bis.org/publications/qr-201609/covered-interest-parity-lost-understanding-cross-currency-basis): cash differentials do not fully capture persistent cross-currency basis.
