# CMA Yield Curve Inputs

The first implementation is a data layer for a 30-plus-year US CMA model. It
does not yet select equilibrium yields, bootstrap discount factors, or calculate
bond returns. Those steps and their acceptance checks are in PLAN.md.

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
blpapi 3.26.8.1 and pandas 3.0.6. No packages were installed or upgraded.
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
LW current estimates, SPF inflation and ACM data using `official_sources.json`.
It records source URLs, checks file formats, and stores checksums. Parsing those
files into approved anchor estimates is the next step; raw downloads are not
automatically averaged or treated as historical release vintages.
Avoid guessing Bloomberg survey tickers or historic-release fields. OIS/futures
are optional phase-two inputs and are deliberately not prepopulated with
unverified identifiers. Extend the catalog after selecting actual contracts and
definitions; contract-roll rules require separate work.

## References

- [xbbg request interface](https://xbbg.org/python/quickstart)
- [Bloomberg API documentation](https://bloomberg.github.io/blpapi-docs/)
- [Treasury par curve methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology)
- [NY Fed real neutral rate data and real-time vintages](https://www.newyorkfed.org/research/policy/rstar)
- [NY Fed ACM zero-coupon term premiums](https://www.newyorkfed.org/research/data_indicators/term-premia-tabs)
- [NY Fed Survey of Market Expectations](https://www.newyorkfed.org/markets/market-intelligence/survey-of-market-expectations)
- [Philadelphia Fed inflation surveys](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/inflation-forecasts)
- [CBO long-term economic projections](https://www.cbo.gov/data/budget-economic-data)
