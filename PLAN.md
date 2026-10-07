# Implementation Plan

## Design Decisions

- Forecast annual par curves over 35 years from a complete dated starting curve.
- Use official Treasury par data for the baseline. Keep Bloomberg benchmark
  yields separate until their definitions have been established.
- Start with direct exponential convergence; add a near-term market/survey
  variant only after measuring its effect on portfolio returns.
- Maintain decimal rates internally. Preserve original rates and units.
- Treat the cash anchor, curve slope anchors, convergence speed and uncertainty
  scenarios as separately reviewed assumptions.
- Keep data retrieval, anchor estimation, projection, curve construction and
  return calculation in separate modules.

## Phase 1: Data Layer (Implemented)

Modules: catalog.py, bloomberg.py, data.py, treasury.py, official.py, anchors.py.

1. Confirm Bloomberg connectivity in my_env. Validate identifiers using NAME
   and PX_LAST, then check a small historical sample.
2. Fetch Treasury benchmark histories, effective fed funds, SOFR and optional
   real-yield diagnostics. Fetch the official Treasury par curve separately.
3. Save dated exports and coverage reports. Fail when required series are
   absent. Select starting curves on a common observation date.
4. Preserve source definitions, original units and retrieval dates. Manually
   verify financial definitions before approving catalog entries.
5. Archive official HLW/LW, SPF inflation and ACM source files with checksums.

Acceptance: working live Bloomberg sample, correct percent/decimal conversion,
no mixed dates or curve types, and meaningful data-quality tests. The official
Treasury endpoint is separately checked; a public-source access failure must
not silently switch to generic Bloomberg yields.

## Phase 2: Equilibrium Inputs And Anchor Estimation

Planned modules: source_parsers.py, estimate_anchors.py.

1. Parse downloaded HLW/LW, ACM and SPF files with explicit column/sheet mappings
   and tests. Add the policy-rate survey and CBO files once their relevant
   definitions are selected. Preserve raw files and source vintages.
   Enter FOMC longer-run estimates from a dated SEP release; automated parsing
   can follow once the initial release schema is confirmed.
2. Compare long-run policy-rate surveys, inflation plus real neutral rates,
   historical real cash, and CBO distant-year rate projections.
3. Map neutral policy to average cash and the Treasury bill instrument using
   explicit cycle and instrument-basis adjustments.
4. Estimate monthly equally weighted historical curve spreads over multiple
   complete cycles and alternative windows. Record sample coverage.
5. Produce base/low/high par anchors at 1m, 2y, 5y, 10y and 30y, plus supporting
   nodes. Report source disagreements and structural overrides explicitly.

Do not add ACM term premiums to cash-to-10y historical spreads: that generally
double counts compensation. ACM zero premiums require zero-yield comparisons.
Do not combine PCE-defined real rates with CPI inflation without an adjustment.

Acceptance: one documented set of anchors with plausible curve shape, source
dates and sensitivity to historical sample selection. No backtest uses data
revisions or publications unavailable at its forecast date.

## Phase 3: Projection Engine

Planned module: projection.py.

Baseline for maturity m at forecast horizon h:

    projected_yield(m, h) = anchor(m)
        + [initial_yield(m) - anchor(m)] * 2 ** [-h / half_life(m)]

Test half-lives of 3, 5 and 8 years as candidate settings, not calibrated facts.
Require h=0 to reproduce the starting curve and long horizons to approach the
anchors. A convergence half-life is different from its forecast handoff year.

Alternative: use selected OIS/futures and survey short-rate forecasts for the
first 2-3 years, then converge. Review premium, Treasury/OIS basis and futures
convexity adjustments. A short-rate forward is not a future 10y bond yield.
Avoid discontinuities at the handoff. Label maturity and forecast horizon as
separate dimensions in every output.

Acceptance: reproducible 35-year projections, monotone gap decay in the
baseline, no accidental curve-type mixing, and sensitivity tables. Smooth
curve-factor projections are a later upgrade if node paths become awkward.

## Phase 4: Discount Curve Construction

Planned module: discount_curve.py.

Bootstrap each projected par curve onto coupon dates, then derive zero and
forward curves from the same discount factors. Use a proven fixed-income
library, such as QuantLib, after reviewing the selected version and conventions.
Five policy nodes do not uniquely specify every coupon-date discount factor;
interpolation and boundary assumptions must be explicit. Retain supporting
short-end/belly nodes for calibration.

Acceptance: reproduce input par rates within tolerance, positive discount
factors, internally consistent zero/forward rates, and stable interpolation.
Do not impose an increasing yield curve or positive rates as a universal rule.

## Phase 5: Return Engine And Validation

Planned modules: returns.py, backtest.py.

1. Reprice fixed-coupon representative bonds as they age. Preserve coupons,
   use dirty prices, include reinvestment and define rebalancing rules.
2. Separate constant-maturity portfolios from buy-and-hold bonds. Do not add
   roll-down again if cash-flow repricing already captures it.
3. Add credit spreads and losses, real cash flows/TIPS indexation and floating
   reset projections. Callable bonds/MBS require separate scenario models.
4. Compare direct convergence, near-term market inputs, unchanged curves and
   simple historical benchmarks using 1-, 3-, 5- and 10-year outcomes.
5. Compare 5-, 10- and 30-year expected portfolio returns and adverse paths.
   Retain the extra near-term layer only if it improves decisions or validation.

Acceptance: price checks against Bloomberg examples, reconciled total returns,
and a committee report showing anchor and convergence sensitivity. There are
too few independent 30-year outcomes to optimize the model on that horizon.
