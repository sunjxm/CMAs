# Validation Record

Validated on October 6, 2026 (America/New_York). Export folder timestamps use UTC.

## Environment

- Existing conda environment: my_env.
- xbbg 1.5.0, blpapi 3.26.8.1, pandas 3.0.6.
- No environment changes or package installations.
- Bloomberg local API reachable on localhost:8194 outside this chat's network
  sandbox. Live reference and historical requests succeeded.

## Live Samples

- Bloomberg history, September 28 through October 6: 103 observations across
  15 series, saved in `data/20261007T023045_7a2d7607/`.
- Official Treasury par feed, same interval: 77 observations across 11 nodes,
  saved in `data/20261007T022847_526ac849/`.
- Five-node par snapshot selected on the common date October 6: one month,
  2y, 5y, 10y and 30y. Selection excludes future rows and separate-date fills.
- Effective fed funds and SOFR latest observations in the sample: October 5.
  This publication lag is retained in the coverage report.
- HLW current and real-time estimates, LW current estimates, SPF inflation,
  and ACM downloaded successfully with format checks and checksums, saved in
  `data/20261007T023236_official_c6e78ccf/`.

## Corrections Found By Live Requests

- USGG1YR Index failed: catalog corrected to USGG12M Index.
- USGGT5Y Index failed: omitted pending a verified 5-year real-yield definition.
- The NY Fed ACM URL ends in .csv but returns an XLS workbook. The downloader
  now expects the actual file format and saves it as acm.xls.

Earlier diagnostic exports are retained as an audit trail. Their manifests may
contain failed candidate requests; use the successful export folders above.

## Tests

12 unittest tests passed. Coverage includes Bloomberg output normalization,
percent/basis-point/decimal conversion including negative rates, missing required
data, common-date selection, staleness, wrong/unverified curve types, overnight
input separation, release/vintage filtering, Treasury XML parsing, paired slope
observations, and partial official-download failures with preserved manifests.

## Limits

Live requests validate identifiers, returned labels and sample availability.
They do not fully certify Bloomberg security/field methodologies. Catalog
verified flags remain false until Terminal definitions are reviewed. Bloomberg
generic yields are deliberately not labeled Treasury par yields.

The official anchor files are archived but not yet parsed into equilibrium
estimates. The empty anchor_inputs.csv is a reviewed-input template. Download
time is not a historical publication date. Automated source parsing, forecasts,
discount-curve construction, return calculations and backtests remain planned.
