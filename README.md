# CMA Yield Curve Inputs

This project retrieves inputs and generates research-draft equilibrium yield
candidates for a 30-plus-year US CMA model. It does not yet approve anchors,
project curve paths, bootstrap discount factors, or calculate bond returns.
The evolving methodology is in docs/METHODOLOGY.md, with a development trail in
docs/METHODOLOGY_LOG.md. Remaining phases are described in PLAN.md.

## Run In Your Existing Environment

Start with `main.py`. Running it directly (including the editor's Run button)
checks Bloomberg connectivity. The settings at the top select the task, dates
and groups. Use `--task all` to run connectivity, metadata, Bloomberg history,
Treasury par data and official anchor downloads in sequence. A failed step stops
the run; completed exports are retained. Defaults select October 1, 1996 through
September 30, 2026: 30 complete years of monthly history. FREQUENCY is monthly.
Monthly data use the last available observation in each completed month, not
monthly averages. Partial ending months are excluded; use `--frequency daily`
for a current starting curve or short daily sample.

```powershell
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' 'C:\Users\Jeff\Python\CMAs\main.py'
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' 'C:\Users\Jeff\Python\CMAs\main.py' --task all
```

You can also import `run` from `main` and call `run(task='history', start=...,
end=...)`. Paths to configuration and the default data directory are resolved
relative to the module, so running from another folder works.

Your Bloomberg-enabled environment was found at
`C:\Users\Jeff\miniconda3\envs\my_env\python.exe`, with xbbg 1.5.0,
blpapi 3.26.8.1 and pandas 3.0.6. The official processing stage additionally
uses openpyxl and xlrd. Install extras on another machine with
`python -m pip install -e ".[bloomberg,official]"` after activating its environment.
Run from this directory, or use the full script path. An editable installation
is optional; the examples below work without one.

```powershell
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' fetch_data.py check
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' fetch_data.py metadata
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' fetch_data.py history --start 1996-10-01 --end 2026-09-30
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' fetch_data.py history --groups real_rates --start 1996-10-01 --end 2026-09-30
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' fetch_data.py treasury-par --start 1996-10-01 --end 2026-09-30
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' fetch_data.py official-inputs
& 'C:\Users\Jeff\miniconda3\envs\my_env\python.exe' -m unittest discover -s tests -v
```

The port check verifies reachability, not authorization or entitlements. Use
metadata and a small historical request next. For a remote API, supply `--host`
and `--port`; non-Desktop authentication needs your team's xbbg session setup.
The adapter accepts an already configured xbbg backend for that case:
`BloombergClient(backend=blp)`.

Each export creates a new folder under `data/`, with observations, a coverage
report, and a manifest recording retrieval time, request dates and definitions.
Reference requests save their own response in `bloomberg_reference.csv`.
BDP is a current reference request; use BDH for a curve at a historical date.
Snapshots downloaded today are not automatically point-in-time historical
vintages. No missing observations are forward-filled.

## Inputs And Definitions

| Group | Included | Intended use |
|---|---|---|
| treasury | Generic US government yields at 1m, 3m, 6m, 1y, 2y, 3y, 5y, 7y, 10y, 20y, 30y | Market comparison and historical slope diagnostics |
| cash | Effective fed funds; optional SOFR | Policy/bill basis and cash diagnostics |
| real_rates | Optional generic TIPS yields at 10y and 30y | Real-rate cross-checks, not pure neutral rates |
| treasury-par | Official Treasury par curve, annual XML feed | Preferred baseline for par-node projections |

One month is an approximation to your 30-day node. The Bloomberg USGG series
are labeled `benchmark_yield`, not `par`: a successful price request does not
establish CMT/par methodology. Catalog `verified` remains false until someone
reviews the Terminal security/field definitions and units. Do not relabel these
series as par just to pass a check. The Treasury module labels the official
series as par and stores percentages as both original values and decimal rates.
`PX_LAST=4.2` with `units=percent` becomes `rate_decimal=0.042`.

The corrected 1-year Bloomberg identifier is `USGG12M Index`. The candidate
`USGG1YR Index` failed validation and was replaced. The candidate 5-year TIPS
identifier failed and is excluded until a suitable series is verified.

To add a data item, add its ticker, field, units and definition to `catalog.json`.
For generic rate indices, PX_LAST is the rate; for individual bonds PX_LAST is
usually a price. Select an appropriate yield field instead. Missing required
series cause a failure; missing optional series appear in coverage. Historical
coverage varies by instrument. SOFR does not have decades of observations.
The public Treasury par feed starts in 1990; requests starting earlier use its
available coverage with a warning. Other series, especially one-month bills and
TIPS, also have shorter histories. Coverage reports retain the actual first and
last dates. Use the 3-month bill for longer cash-history diagnostics where
appropriate; do not fill the absent one-month history with it silently.

Monthly exports include a `month` label and retain the date returned by the
source. Bloomberg monthly requests use calendar periodicity; Treasury daily
observations are sampled locally. Missing months are not carried forward.

## Use From Python

```python
from cma_curve.treasury import fetch_treasury_par
from cma_curve import curve_asof
from cma_curve.anchors import slope_diagnostics, load_anchor_inputs

history, urls = fetch_treasury_par('2026-09-28', '2026-10-06')
curve = curve_asof(
    history, '2026-10-06',
    ['BC_1MONTH', 'BC_2YEAR', 'BC_5YEAR', 'BC_10YEAR', 'BC_30YEAR'],
    require_type='par',
)
# This selects the latest common observed date, subject to a staleness limit.
# It does not combine five nodes from five different dates.
diagnostics = slope_diagnostics(
    history, 'BC_1MONTH', ['BC_2YEAR', 'BC_5YEAR', 'BC_10YEAR', 'BC_30YEAR'],
    '2026-09-28', '2026-10-06',
)
# Use multi-cycle histories and alternate windows for actual slope estimates.
# The short example above is a connection/integration check only.
```

## External Anchor Inputs

`anchor_inputs.csv` is an empty input template, not a set of invented estimates.
Populate it from official releases or your team's reviewed data. Each row needs
the key, value, units, observation date/forecast period, publication date,
vintage date, source and precise definition. `load_anchor_inputs()` excludes
values published or revised after the requested as-of date. It preserves
multiple sources and estimates rather than silently averaging them.

Priority inputs are FOMC longer-run nominal fed funds, survey longer-run nominal
fed funds, long-run inflation, HLW/LW real neutral rates, and ACM term premiums.
`official-inputs` downloads and archives HLW current and real-time workbooks,
LW current estimates, SPF CPI and PCE inflation, and ACM data using `official_sources.json`.
It records source URLs, checks file formats, and stores checksums. Parsing those
files into research-draft candidates is now implemented; raw downloads are not
automatically averaged or treated as historical release vintages.
Avoid guessing Bloomberg survey tickers or historic-release fields. OIS/futures
are optional phase-two inputs and are deliberately not prepopulated with
unverified identifiers. Extend the catalog after selecting actual contracts and
definitions; contract-roll rules require separate work.

## Process Inputs And Review Anchors

After downloading official sources and monthly Treasury par history:

```powershell
python main.py --task process-inputs
python main.py --task anchor-review
```

Both run offline and create new dated folders under data/. Anchor review includes
source parsing, so running process-inputs first is optional. The default discovers
the most recently retrieved official and Treasury bundles by manifest type.
An older five-source archive lacks PCE10: rerun official-inputs to obtain it.
A failed or incomplete latest bundle fails visibly rather than silently choosing
an older snapshot. For a reproducible formal run, pin the inputs:

```powershell
python main.py --task anchor-review --official-archive data\20261007T031202_official_f559f005 --treasury-bundle data\20261007T030129_567ade64
```

`anchor_settings.json` holds provisional source, smoothing, adjustment, and
historical spread choices. `--settings` accepts another settings file. Neither
run task is included in --task all, which continues to download inputs only.
These analysis tasks require monthly calibration; they do not use Bloomberg.

Each run saves official_observations.csv, source_inventory.csv, run_summary.md,
and a manifest with hashes. Anchor review also saves candidate_anchors.csv,
macro_components.csv, slope_diagnostics.csv, acm_diagnostics.csv, and
starting_par_curve.csv. Original raw archives and earlier run reports are retained.

Quarterly inputs are not expanded into monthly pseudo-observations. Release
dates remain unmapped and all generated candidates are research drafts, not
historically available inputs or approved assumptions. Review the methodology
and comparison tables before adopting the numbers. Source histories and
data/ exports remain local and are not needed to version-control the code.

## Fixed Income Model Foundation

The selected primary research anchor is now `hlw_median20`; Treasury curve slopes
still use 30-year means. Six benchmark sleeves are registered in bond_assets.json
for nominal USD returns, including USD-hedged global ex-USD and Bloomberg EM USD Aggregate.
See docs/FIXED_INCOME_RETURNS.md for definitions and outstanding assumptions.

```powershell
python main.py --task anchor-review
python main.py --task curve-projection
python main.py --task asset-review
python main.py --task asset-metadata
python main.py --task asset-analytics
python main.py --task asset-analytics-probe
python main.py --task asset-analytics-normalize
```

Projection settings are in projection_settings.json: 40 years at monthly steps,
a provisional five-year base half-life and three/eight-year sensitivities. Outputs
are par-node projections, not discount factors or asset-return forecasts. Changing
anchor settings requires a new anchor-review before projection. Use --review-bundle
to pin an archived review for reproducibility.

All six user-supplied Bloomberg benchmark tickers are configured. The user approved
LF98TRUU broad US Corporate High Yield and EMUSTRUU EM USD Aggregate instead of
the earlier ICE BB-B constrained and JP Morgan EMBI requests. Confirm metadata,
rating/maturity filters, total-return convention and hedging before setting each
benchmark's verified flag. Configure analytics field mappings and verify units in
Bloomberg FLDS. After review, download selected sleeves with:

```powershell
python main.py --task asset-history --assets us_aggregate
```

The six benchmark definitions are now user-approved, with successful metadata
evidence and downloaded monthly histories. Reviewed nominal analytics mappings
are recorded separately. Field discovery archives definitions; the probe archives
raw candidate values; offline normalization consumes only verified mappings and
preserves gaps. TIPS real analytics, global spread/hedge inputs and convexity scaling
remain unresolved. These tasks do not generate expected-return forecasts.

Unverified benchmarks are rejected. Historical monthly returns do not bridge
missing months. Metadata is a current snapshot, not data at --end. All new tasks
archive summaries and hashes in data/. The existing --task all remains download-only.

## Word Review Copies

`convert_md_to_docx.py` turns Markdown into editable Word documents with a clean
report style. It preserves source Markdown, headings, emphasis, external links,
lists, tables, literal code blocks, and native editable Word equations. Wide tables automatically select
landscape pages. It requires neither Word nor a Bloomberg connection to convert.
Images and internal anchor links are not supported and fail visibly rather than
silently disappearing. Raw HTML is treated as literal text, not executed.

```powershell
python -m pip install -e ".[documents]"
python convert_md_to_docx.py
```

With no file arguments, the script selects docs/*.md and the latest anchor-review
run_summary.md. Word copies go into docs/word/. To refresh existing copies:

```powershell
python convert_md_to_docx.py --overwrite
```

Select files, a folder, or quoted patterns; --all also includes project-root
Markdown files such as README.md and PLAN.md:

```powershell
python convert_md_to_docx.py docs\METHODOLOGY.md --output docs\word --overwrite
python convert_md_to_docx.py "docs\*.md" --output docs\word --overwrite
python convert_md_to_docx.py --all --overwrite
```

Use --orientation portrait or landscape to override automatic page selection.
Close a Word copy before overwriting it. Review edits made in Word do not flow
back into Markdown automatically; incorporate agreed changes into the Markdown
source, then regenerate. Convert duplicate filenames into separate output folders.

Write inline LaTeX as `$r^{*}$` and display equations between `$$` delimiters on
separate lines. Do not put formulas inside code fences or backticks: those remain
literal code. Escape currency dollar signs as `\$` to avoid treating prices as
math. For example:

```markdown
$$
y_m(h) = a_m + \left[y_m(0) - a_m\right] 2^{-\frac{h}{H_m}}
$$
```

The converter uses LaTeX-to-MathML-to-Office-Math conversion, so equations are
editable in Word rather than images. It supports common mathematical notation,
not complete LaTeX documents or custom macros. Conversion errors stop visibly;
visually review complex expressions after exporting. Install the updated
documents extra above on each machine before using equation conversion.

## TIPS Proxy Inputs

```powershell
python main.py --task tips-inputs
```

Downloads monthly 5-year TIPS benchmark yield, index duration proxy and average maturity into a separate hashed archive under `data`. These are explicitly provisional inputs, not verified index real analytics or expected returns. See `docs/TIPS_INPUTS.md` for the investigation and limitations. Missing observations are not filled.

## Investment-Grade Return Research

```powershell
python main.py --task bond-returns
```

Run in activated `my_env`. Uses archived curves and reviewed index analytics offline to generate 40-year monthly paths for Short Term Bond and US Aggregate, annual attribution, long-horizon annualized returns and historical explanatory diagnostics. Source bundles can be pinned with `--curve-bundle`, `--analytics-bundle` and `--history-bundle`; assumptions are in `return_settings.json` or `--return-settings`.

These are draft deterministic scenarios. The gross baseline has no credit losses or fees; spread/loss cases are sensitivities. See `docs/INVESTMENT_GRADE_RETURNS.md`. Other sleeves are not generated, and `--task all` remains download-only.

## Handbook-Informed Extensions

```powershell
python main.py --task composition-inputs
python main.py --task credit-review
python main.py --task holding-returns
python main.py --task global-hedge-review
```

`composition-inputs` downloads current weighted constituents and metadata where Bloomberg supplies complete weights; it does not fetch historical month-end composition. `credit-review` retains unresolved exposure and exports segment-input templates. `holding-returns` bootstraps synthetic Treasury discount curves with QuantLib and compares coupon/aging/normalization returns; it does not replace credit-index forecasts. `global-hedge-review` produces no forecast until complete foreign return, cash and currency inputs are supplied.

Install the optional pricing library on another machine with `pip install -e ".[pricing]"`. CSV inputs can be supplied with `--loss-segments`, `--spread-segments` and `--global-hedge-inputs`. See `docs/HANDBOOK_IMPLEMENTATION.md` for schemas, reproduction and outstanding data. All outputs remain research-only.

## Bloomberg Breakdown Workbook

```powershell
python main.py --task workbook-inputs
```

Reads `BBG_bond_data.xlsx` at the project root without modifying it. Archives sector/rating marginals, currency weights and currency analytics with source cells, missing-value coverage and hashes. It does not infer the observation date from `--end`, rescale rounded weights, turn missing local yields into zero or change forecast assumptions. Optional `--workbook`, `--workbook-asof` and `--workbook-rating-method` specify a different file and confirmed provenance. Requires the `official` extra's openpyxl dependency.

See `docs/WORKBOOK_INPUT_REVIEW.md` for findings, the cash-rate review template and the resource-efficient global carry/hedge proposal. A snapshot is not a historical series, and separate sector/rating tables are not a joint credit distribution.

## Foreign Cash Basket And USD Hedge Carry

```powershell
python main.py --task foreign-cash
```

Links the existing US one-month cash projection to seven named currencies (EUR, CNY, JPY, GBP, CAD, AUD, CHF) plus Other. The first run creates `inputs/foreign_cash_assumptions.csv` with blank cash/inflation inputs and explicit provisional zero real-cash adjustments; existing files are never overwritten. Fill reviewed inputs and rerun to produce monthly cash paths and an additive USD hedge overlay, not a global bond total-return forecast.

Configuration is in `foreign_cash_settings.json`. Inputs and archives can be pinned with `--foreign-cash-inputs`, `--foreign-cash-settings`, `--workbook-bundle` and `--curve-bundle`. The Other bucket explicitly absorbs remaining currency weights and the displayed rounding residual. See `docs/FOREIGN_CASH_BASKET.md` for LaTeX formulas, units, conventions, calibration and audit trail.

## References

- [xbbg request interface](https://xbbg.org/python/quickstart)
- [Bloomberg API documentation](https://bloomberg.github.io/blpapi-docs/)
- [Treasury par curve methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology)
- [NY Fed real neutral rate data and real-time vintages](https://www.newyorkfed.org/research/policy/rstar)
- [NY Fed ACM zero-coupon term premiums](https://www.newyorkfed.org/research/data_indicators/term-premia-tabs)
- [NY Fed Survey of Market Expectations](https://www.newyorkfed.org/markets/market-intelligence/survey-of-market-expectations)
- [Philadelphia Fed inflation surveys](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/inflation-forecasts)
- [CBO long-term economic projections](https://www.cbo.gov/data/budget-economic-data)
