# Finite-Time Yield Curve Convergence And Surface Scenarios

Date: October 7, 2026. Status: implemented research projection, not approved expected returns.

## User Decisions

Replace the previous pure exponential 3/5/8-year scenarios with 3/5/10-year half-lives. Follow exponential convergence through year 25, then close the remaining gap linearly to the exact anchor at year 30. Retain a 40-year production projection with constant anchors after year 30. Plot years 0-30 as maturity-by-projection-horizon surfaces, with the September 30, 2026 starting curve first and historical initializations below.

The selected `hlw_median20` anchor method and historical mean Treasury slopes are unchanged. Foreign-cash calibration remains paused; no new cash assumptions or bond-return forecasts are generated in this step.

## Projection Formula

For maturity m, anchor a_m, observed starting yield y_m(0), horizon t and half-life H:

$$
y_m(t)=a_m+[y_m(0)-a_m]d_H(t).
$$

$$
d_H(t)=\begin{cases}
2^{-t/H}, &0\le t\le25,\\
2^{-25/H}\dfrac{30-t}{5}, &25<t<30,\\
0, &t\ge30.
\end{cases}
$$

All yields are decimal annual rates internally, with percentages in plots. Horizon and half-life are in years. At horizon zero, the projection reproduces every starting node. Through year 25, the gap halves every H years. After year 25, the remaining gap closes at a constant annual rate; it is not an exponential restarted at year 25. At year 30 and thereafter, each node equals its anchor exactly.

This construction is continuous in level at year 25. Its slope generally changes at the handoff and becomes zero at year 30. These kinks are intentional consequences of the requested piecewise rule, not an estimated economic transition. No smoothing or overshoot is added.

| Half-Life | Starting Gap Remaining At Year 25 |
| --- | --- |
| 3 years | 0.310% |
| 5 years | 3.125% |
| 10 years | 17.678% |

These percentages describe the fraction of the initial yield-minus-anchor gap, not yields or percentage-point yield changes. The linear tail matters most in the ten-year scenario.

## Historical Initializations

Each historical row uses an exact observed common date in the archived official Treasury monthly history. No missing maturity is carried forward from another date. The five display nodes are one month, 2, 5, 10 and 30 years. The one-month node represents the short cash point in this framework.

| Starting Date | Scenario | 1M Yield | 2Y Yield | 10Y Yield | 30Y Yield | 10Y Minus 2Y |
| --- | --- | --- | --- | --- | --- | --- |
| September 30, 2026 | Current curve | 4.02% | 4.88% | 5.29% | 5.64% | +41 bp |
| December 29, 2006 | Mild inversion | 4.75% | 4.82% | 4.71% | 4.81% | -11 bp |
| December 31, 2009 | Steep curve | 0.04% | 1.14% | 3.85% | 4.63% | +271 bp |
| July 31, 2020 | Low-yield curve | 0.09% | 0.11% | 0.55% | 1.20% | +44 bp |
| June 30, 2023 | Deep inversion | 5.24% | 4.87% | 3.81% | 3.85% | -106 bp |

All five rows converge toward the SAME current-vintage selected anchors. Historical curves are observed starting inputs, but the resulting projected scenarios are counterfactual initialization comparisons, not historical forecasts, out-of-sample validation or a point-in-time macro backtest. Historical anchor estimation is outside this step.

## Plot Design

The full comparison is a five-row by three-column surface matrix. Rows follow the table above. Columns show 3-, 5- and 10-year half-lives from left to right. X is maturity in years, Y is projection years 0-30, and Z/color is par yield in percent. All panels have identical axes, yield limits, camera angles and color scales.

Black lines mark observed starting curves, white dashed lines mark year 25, and red lines mark the year-30 anchors. Monthly projected values are archived; quarterly samples are used for display to reduce rendering cost. Piecewise-linear maturity interpolation preserves all five modeled nodes and is a display-only convention, not a pricing curve, zero-rate bootstrap or forward-rate model.

The separate interactive HTML has three half-life panels and a dropdown for starting scenario. Rotation, zoom and hover data are supplied by an embedded Plotly bundle; no internet connection or development server is needed. The PNG matrix remains the complete n-by-three overview. On October 7, mesh lines were added directly to the interactive surfaces along maturity and projection-year directions at two-year intervals. Mesh On/Off controls toggle all three surfaces without changing the selected scenario. The scenario selector updates only coordinates, preserving the mesh setting.

![Current starting-curve surfaces](../data/20261007T200421_curve-surfaces_d1a05074/current_curve_surfaces.png)

[Full five-by-three matrix](../data/20261007T200421_curve-surfaces_d1a05074/yield_curve_surface_grid.png).

[Interactive projection comparison and historical surface](../data/20261008T012212_curve-surfaces_2e42b0e5/interactive_curve_surfaces.html).

The interactive yield-axis range now fits the selected starting scenario, with one common range across its three half-life panels. A margin equal to the greater of 5% of the scenario yield span or 0.1 percentage point is added on each side, and limits are rounded outward to 0.1 percentage point. The current scenario spans approximately 3.0%-5.8%, removing the empty area below the previous zero-based axis. Dropdown changes update all three yield axes together without changing mesh visibility.

The interactive color scale also adapts to the selected scenario, using its actual minimum and maximum projected yields across all three half-lives. Current-curve color limits are approximately 3.1881%-5.64%. A constant-valued surface uses the padded axis limits as a nonzero color-range fallback. All three panels share the same color limits, and the colorbar updates with the scenario selector. Colors and vertical geometry are comparable across half-lives within a selected scenario, but no longer directly across different dropdown scenarios. Static matrix axes and color scales remain globally fixed for cross-scenario comparisons.

## Historical Surface Below The Projections

The HTML now contains a separate full-width historical surface below the three projection panels. It uses 360 months of archived Treasury data from October 1996 through September 2026, including all eleven available source maturities. X is maturity, Y is historical calendar year, and Z/color is observed or interpolated par yield percent. Hover reports the exact observation date and whether a value is observed or interpolated. Historical color/yield limits are independent of the projection selector, and changing a forecast starting scenario does not change history.

For missing interior maturity m between two valid quotes at maturities m_i and m_j on the SAME date t:

$$
y(m,t)=y(m_i,t)+\frac{m-m_i}{m_j-m_i}\left[y(m_j,t)-y(m_i,t)\right].
$$

The display grid includes every original maturity plus a denser maturity mesh. All observed values are preserved exactly in computation. Interpolation is linear in maturity and confined to available same-date endpoints; it is not a pricing bootstrap, time interpolation or a missing-history estimate. Missing months are retained as blank rows. Values shorter or longer than the available maturity range stay missing, and Plotly gap-connection is disabled.

For each month, the latest actual observation date is used. The one archived 30-year quote dated February 15, 2002 is excluded from the February 28 curve rather than carried forward and mixed with later quotes. That quote is preserved in the source archive and in an exclusion CSV. Missing one-month observations before their series begins and missing long-end observations remain visible as endpoint gaps.

The final historical grid has 39,240 cells: 3,855 observed, 33,696 same-date maturity interpolations (including the dense display mesh), and 1,689 unavailable. Outputs include `historical_surface_grid.csv` with bracket maturities/status, `historical_surface_coverage.csv`, `historical_excluded_quotes.csv` and `historical_yield_surface.png`. The combined HTML embeds Plotly once and keeps forecast and history controls separate.

![Historical Treasury surface](../data/20261008T012212_curve-surfaces_2e42b0e5/historical_yield_surface.png)

## Reproduction

Run in activated `my_env`:

```powershell
python main.py --task curve-projection
python main.py --task curve-surfaces
```

Projection configuration is in `projection_settings.json`. Scenario dates and labels are in `curve_surface_settings.json`, supplied optionally with `--surface-settings`. Add another archived common-date month-end curve to that file to extend the matrix. Exact dates are required; for a non-month-end date, a compatible historical archive must first be supplied using `--treasury-bundle`. The task does not silently choose a nearby date.

Curve and review sources can be pinned with `--curve-bundle` and `--review-bundle` on their respective tasks. Official monthly Treasury history defaults to the source recorded in the anchor-review manifest. Source hashes and dates are retained; altered source files are rejected where pinned checksums are available.

For another machine:

```powershell
pip install -e ".[plots]"
```

## Output Archives And Verification

- `data/20261007T200125_curve-projection_c3c43bf2`: updated full-node, 40-year monthly par projections for 3/5/10-year half-lives. All projected nodes equal anchors exactly from year 30 onward.
- `data/20261007T200421_curve-surfaces_d1a05074`: original reviewed plot archive, with 27,075 modeled node observations (5 initializations x 3 half-lives x 361 months x 5 nodes), actual starting curves, diagnostics, grid/current PNGs, interactive HTML, summary and hashes.
- `data/20261008T010009_curve-surfaces_5b97054f`: mesh update archive, adding two-year mesh lines and Mesh On/Off controls. The UTC folder timestamp is October 8; the user-facing change date is October 7 US Eastern. Numerical projections and static-plot design are unchanged.
- `data/20261008T010334_curve-surfaces_4ab065c6`: yield-axis update archive with scenario-specific padded limits shared across half-life panels. Numerical projections, mesh behavior, global color scale and static matrix are unchanged in that archived version.
- `data/20261008T011121_curve-surfaces_c4408ab4`: adaptive-color archive with scenario-specific actual-extrema color limits shared across the three panels, alongside the adaptive yield axes.
- `data/20261008T012212_curve-surfaces_2e42b0e5`: current combined HTML deliverable, appending the historical surface and adding its interpolation/coverage audit files. Forecast projections and existing controls are unchanged.

Prior archives are preserved. Intermediate plot archives were followed by layout corrections to the single-row plot title and short-maturity tick labels; the final archive above is the review deliverable. Existing bond-return and holding-return archives have not been regenerated, so they still reflect their recorded earlier scenarios.

All 129 project tests pass. The convergence tests cover exact terminal/post-terminal anchors, handoff continuity, initial half-life behavior, monotone gap closure, invalid handoffs, pure-exponential compatibility, exact-date/missing-node historical selection, node-preserving display interpolation and shared cash convergence. Interactive-export tests check mesh spacing and visibility on every panel, toggle payloads, scenario updates preserving mesh settings, and identical initial/updated yield limits on all three panels. Range tests cover padding, nonzero minima, flat curves, negative yields and invalid data. Seven historical-surface tests cover observed-node preservation, same-date interpolation, unfilled months/endpoints, earlier-date quote exclusion, invalid definitions/duplicates, hover/gap configuration and combined HTML panel ordering with one embedded Plotly bundle. The paused foreign-cash helper now inherits the source projection's convergence rule to avoid silently mixing a hybrid US path with a pure-exponential foreign path; no foreign calibration was performed.

Live projection and surface tasks succeeded. CSV checks confirm the initial and final nodes, and archive output hashes were verified. PNGs were visually inspected and corrected for title/tick overlap. The interactive HTML was generated, but live rotation/dropdown verification could not be performed because no connected browser was available.

## Sources

Official Treasury par-history archive: `data/20261007T030129_567ade64`. Current starting curve and selected anchors: `data/20261007T042404_anchor-review_c3a8a852`. These are the existing project sources; no new yield observations or historical macro anchors were fabricated.

[US Treasury interest-rate statistics and curve methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics).
