# Bloomberg Breakdown Workbook Review

Date: October 7, 2026. Status: imported for research; no official return assumptions changed.

## Source And Provenance

The user supplied `BBG_bond_data.xlsx` at the project root. The read-only importer preserves its sector, rating, currency, duration and yield observations, with exact sheet/cell provenance. Source and generated outputs are SHA-256 hashed. It does not overwrite, evaluate formulas in, or fill the workbook.

The workbook itself does not state an as-of date or rating methodology. The user confirmed September 30, 2026 and Bloomberg composite ratings. These are recorded as user-supplied provenance in the final archive. The snapshot therefore aligns by observation date with the September starting curve. Bloomberg composite ratings are not automatically identical to S&P agency ratings. File creation time and the program's `--end` default are never substituted for an observation date. A confirmed date does not automatically approve the other definitions.

## Findings

| Breakdown | Displayed Weight Total | Important Limitation |
| --- | --- | --- |
| US Aggregate sector | 99.97% | 0.03 percentage point displayed residual; no joint sector/rating table |
| US Aggregate rating | 100.00% | NR 46.62% plus Unclassified 25.43%, or 72.05% without a usable rating |
| Global ex-USD currency | 99.99% | 0.01 percentage point residual and 0.15% Unclassified |
| Global currency duration | 99.84% covered | Duration type unverified; Unclassified has no duration |
| Global currency local yield | 0.00% covered | All positive-weight currencies lack yields |

The only numeric local yields, 4.56% for ITL and 4.18% for DEM, occur on zero-weight legacy currencies. They are retained as source observations but supply no portfolio yield coverage. The currency and analytics sheets use different row orders, so the import joins currency labels rather than positions.

The weight residuals lie inside the theoretical rounding bound for two-decimal percentage-point weights. That is a consistency check, not proof of complete or correctly classified exposure. Raw weights remain unchanged. No automatic normalization removes residuals or the Unclassified exposure.

## Credit Implications

Separate sector and rating breakdowns cannot identify the rating distribution of the corporate subset. Applying global corporate default frequencies to every rated index weight would implicitly treat government and securitized exposures as corporations. Assuming that all unrated positions are Treasuries would also be unjustified.

The workbook improves composition review but does not by itself produce an approved US Aggregate expected loss. Obtain a corporate-only rating breakdown or sector-by-rating weights, review the mapping from Bloomberg composite ratings to the chosen default-study population, and retain separately reviewed government/securitized loss assumptions. The existing complete-segment calculator can then apply:

$$
\ell_a=\sum_j w_{a,j}PD_j(1-RR_j).
$$

No PD, recovery or zero-loss assumption is generated from the new marginal tables. HY and EM coverage gaps identified in the earlier review are unaffected.

## Global Bond Recommendation

Missing currency-specific bond yields do not prevent a resource-efficient hedge-carry approximation. Use the already reviewed aggregate index yield as an underlying-bond carry starting point, subject to confirming the yield convention. Obtain currency cash rates or matched forward-implied hedge costs, not 30 years of bond yields for every currency.

Our proposed annualized carry approximation is:

$$
y_t^{USD,h,carry}\approx y_t^{aggregate,local}
+r_t^{USD}-\sum_c w_{c,t}r_t^c.
$$

The corresponding monthly first-order return decomposition is:

$$
R_t^{USD,h}\approx R_t^{local,aggregate}
+\frac{r_t^{USD}-\sum_c w_{c,t}r_t^c}{12}.
$$

Use beginning-period annual decimal cash rates and monthly decimal local returns. The formulas are our resource-efficient approximation, informed by the handbook's cash/forward differential discussion, not an exact Bloomberg hedged-index replication. Basis, hedge timing, forward conventions, slippage and residual FX remain outside this calculation. Do not add the overlay to a return series or yield estimate that already includes the same hedging effect.

This still requires reconciled complete currency weights, treatment of the Unclassified exposure, foreign cash inputs and local bond return assumptions. USD hedging does not remove foreign interest-rate exposure. Foreign rate normalization cannot be replaced with US Treasury normalization solely because the reporting currency is USD.

For the foreign rate path, review current cash anchors plus foreign term/credit premiums, or use shorter overlapping foreign government-rate histories. Report available coverage rather than filling a nonexistent 30-year local-yield history. Long-run anchor and half-life choices remain separate approvals. The five largest currencies (EUR, CNY, JPY, GBP and CAD) cover 87.51%, but the remaining 12.48% displayed weight is not dropped or rescaled away.

## Implementation And Reproduction

`cma_curve/workbook_inputs.py` and the offline CLI task import this exact four-sheet layout. Explicit headers determine percent-point and year units. Unknown strings, duplicate categories, invalid numeric weights, negative duration and ambiguous percent-formatted storage are rejected. Missing values and unavailable formula caches remain missing. Signed yields are allowed.

```powershell
python main.py --task workbook-inputs --workbook-asof 2026-09-30 --workbook-rating-method "Bloomberg composite ratings"
```

The default workbook is `BBG_bond_data.xlsx` beside `main.py`. For another export, use `--workbook path/to/export.xlsx` and its confirmed provenance. These are provenance inputs, not inferred metadata or approval flags. Running without the provenance arguments intentionally records an unknown date/method rather than assuming every future export has the same date.

Final archive with confirmed provenance: `data/20261007T055252_78d41204`. The earlier undated import, `data/20261007T055053_cf5d0c48`, remains preserved for audit but is superseded for this source review.

Outputs include `observations.csv`, `coverage.csv`, `sector_weights.csv`, `rating_weights.csv`, joined `currency_inputs.csv`, `currency_cash_review_template.csv`, `run_summary.md` and `manifest.json`. The cash template is a review worksheet in CSV form, not a directly runnable monthly return input. It includes unresolved positive-weight exposure and leaves all unsupplied cash rates blank. No forecast or settings file is changed.

All 105 project tests pass. Five new tests cover units, missing values, cell provenance, label joins, duplicate/header/number rejection, recorded rounding without rescaling, missing formula caches, source preservation and output hashes. The actual workbook import succeeded and generated output hashes were verified.

## Sources

- User-supplied workbook: the four named sheets, with row/cell provenance retained in the archive.
- [JPM LTCMA Methodology Handbook, page 31](https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/portfolio-insights/ltcma/noindex/ltcma-methodology-handbook.pdf): local-return conversion and monthly FX forward hedging.
- [Bloomberg Fixed Income Index Methodology, currency hedging section](https://data.bloomberglp.com/professional/sites/10/Bloomberg-Index-Publications-Fixed-Income-Index-Methodology.pdf): actual index hedge mechanics differ from a cash-rate-only proxy.
