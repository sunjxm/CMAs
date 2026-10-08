# Fresh-Machine Setup Through Yield Curve Surfaces

Windows PowerShell walkthrough, checked against the project on October 8, 2026.
Run each command separately and continue only when it succeeds. Commands below
assume a fresh clone, not a directory containing an existing project.

## 1. Prepare The New Machine

Install 64-bit Git for Windows, Miniconda and VS Code. Install VS Code's Python
extension. For Bloomberg downloads, also install your authorized Bloomberg
Terminal/Desktop API and log in on this machine. Installing Python packages or
cloning GitHub does not transfer Bloomberg licenses, credentials or entitlements.

Official references:

- [Git for Windows](https://git-scm.com/download/win)
- [Miniconda installation](https://www.anaconda.com/docs/getting-started/miniconda/install)
- [Conda shell initialization](https://docs.conda.io/projects/conda/en/latest/commands/init.html)
- [GitHub cloning](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository)
- [xbbg installation and Bloomberg runtime requirements](https://pypi.org/project/xbbg/)

From a Miniconda/Anaconda prompt, initialize PowerShell once:

```powershell
conda init powershell
```

Close and reopen VS Code and its PowerShell terminal after initialization. If
your employer blocks PowerShell profiles, use an approved Anaconda prompt or ask
IT; do not disable company security policies to make activation work.

## 2. Clone The Repository

In PowerShell on the new machine:

```powershell
git --version
conda --version
New-Item -ItemType Directory -Path "$HOME\Python" -Force
Set-Location "$HOME\Python"
git clone https://github.com/sunjxm/CMAs.git
Set-Location .\CMAs
git status -sb
git log -1 --oneline
code .
```

Authenticate using Git's approved GitHub sign-in flow if the repository is
private. Do not put passwords or tokens into commands or project files. If
`code` is unavailable, open this folder through VS Code's File > Open Folder.
The path uses the new machine's username rather than assuming it is Jeff.

If you already cloned the project, do not clone into it again. Instead:

```powershell
Set-Location "$HOME\Python\CMAs"
git status -sb
git pull --ff-only
```

Resolve any local changes or diverged branches before continuing; do not reset
or discard them just to update the project.

## 3. Create And Activate Python

Python 3.14 matches the working source machine. The environment name is local to
each computer: cloning does not create or transfer `my_env`.

```powershell
conda create -n my_env python=3.14 pip -y
conda activate my_env
python --version
python -c "import sys; print(sys.executable)"
python -m pip install --upgrade pip
python -m pip install -e ".[official,plots,pricing]"
python -m pip check
```

If `my_env` already exists and has a suitable Python version, skip the creation
line and activate it. In VS Code, use Python: Select Interpreter and select this
environment. The `official` extra installs Excel readers; `plots` installs
Matplotlib and Plotly. `pricing` installs QuantLib for the broader project's
tests/return workflow, although it is not used to draw these par surfaces.

## 4. Install And Check Bloomberg (Optional For Surfaces)

Use these versions to match the working source machine's Bloomberg adapter.
The explicit PyArrow dependency supports the newer xbbg dataframe conversions.

```powershell
python -m pip install "xbbg[pandas]==1.5.0" pyarrow
python -m pip install --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ "blpapi==3.26.8.1"
python -m pip check
python -c "import xbbg, blpapi; print(xbbg.__version__); print(blpapi.version())"
python main.py --task check
python main.py --task metadata
```

Bloomberg must be running and logged in. Default connection: `localhost:8194`.
The port check proves reachability only; a successful metadata response is the
first actual data request. Metadata is a current snapshot, not a September 2026
historical snapshot. Review the returned security names and values. Catalog
`verified=False` flags are review markers, not proof that requests failed.

If this machine has no Bloomberg access, skip this entire section and the
Bloomberg history command below. Official Treasury par curves and public macro
sources are sufficient for anchor review, projection and all surface plots.

## 5. Download The Input Data

From the repository root with `my_env` active, run:

```powershell
python main.py --task history --start 1996-10-01 --end 2026-09-30 --frequency monthly
python main.py --task treasury-par --start 1996-10-01 --end 2026-09-30 --frequency monthly
python main.py --task official-inputs
```

The first line requires Bloomberg and downloads Treasury, cash and real-rate
groups for comparison. It is optional for the surface pipeline. The remaining
two lines are required and use public sources:

- `treasury-par`: official Treasury daily par data, sampled at the last available
  observation in each completed month. The download makes annual requests for
  1996 through 2026 and prints progress. Historical gaps remain unfilled here.
- `official-inputs`: HLW current and real-time estimates, LW current estimates,
  SPF CPI and long-run headline PCE forecasts, and ACM term-premium diagnostics.

These dates cover 30 complete years of monthly history, or 360 calendar months.
Individual nodes can have fewer observations because their histories differ.
Data are month-end observations, not monthly averages. The end date remains
September 30, 2026, even if you run this later. Official files may include newer
periods; analysis filters observations to the cutoff but does not undo revisions.

Alternatively, with Bloomberg working, this single command performs all five
download/check stages (do not also repeat the commands above unnecessarily):

```powershell
python main.py --task all --start 1996-10-01 --end 2026-09-30 --frequency monthly
```

`all` does not run analysis or plots. It stops at the first failed download;
previously completed exports are retained. Fix the failure and rerun its task
rather than restarting every successful download.

## 6. Process And Review The Anchors

```powershell
python main.py --task process-inputs --start 1996-10-01 --end 2026-09-30
python main.py --task anchor-review --start 1996-10-01 --end 2026-09-30
```

`process-inputs` parses and checks the official archive, saving normalized
observations and source inventory. `anchor-review` also performs processing, so
the first command is optional, but gives a separate audit checkpoint.

Review these files in the printed `*_anchor-review_*` output folder:

| File | What to check |
| --- | --- |
| `run_summary.md` | Source coverage, assumptions, candidate comparison and caveats |
| `candidate_anchors.csv` | Anchors in percent and decimals, candidate and node |
| `macro_components.csv` | Real-neutral and inflation inputs, periods and smoothing |
| `slope_diagnostics.csv` | Historical slopes in bps and paired-month coverage |
| `starting_par_curve.csv` | Common starting date and observed par-node values |
| `acm_diagnostics.csv` | Zero-coupon term-premium cross-check, not an added par spread |

In `anchor_settings.json`, confirm `primary_candidate` is `hlw_median20`.
This is the median of 20 quarters of HLW real-neutral estimates, not 20 years.
The main historical slope assumption separately uses the 30-year window and
mean spreads. The zero policy-to-bill and inflation adjustments remain explicit
provisional assumptions. Choosing this candidate does not change research-draft
outputs into committee-approved assumptions.

## 7. Generate The Projected Curve Paths

```powershell
python main.py --task curve-projection
```

This selects the latest anchor review and uses `projection_settings.json`:

- Monthly paths for 40 years, with 3-, 5- and 10-year half-lives; base is 5 years.
- Exponential convergence through year 25.
- Linear convergence from the year-25 value to the exact anchor at year 30.
- Constant anchor values after year 30.

Inspect `projected_par_curves.csv`, `run_summary.md` and `manifest.json` in the
printed `*_curve-projection_*` folder. These are par-yield projections, not
zero-coupon discount curves or fixed-income expected returns. If you change
anchor settings, rerun `anchor-review` before generating new projections.

## 8. Generate And Open The Surfaces

```powershell
python main.py --task curve-surfaces
$surface = Get-ChildItem .\data -Directory -Filter '*_curve-surfaces_*' | Sort-Object Name -Descending | Select-Object -First 1
Invoke-Item (Join-Path $surface.FullName 'interactive_curve_surfaces.html')
```

The HTML works locally without a web server. It includes scenario selection,
mesh controls, fitted yield-axis and color ranges, and the historical surface
at the bottom. Maturity is the x axis; projection year is the y axis for forward
scenarios, while the historical panel uses calendar dates. Yields are percent.

The static `yield_curve_surface_grid.png` is a 5 x 3 comparison: current
September 30, 2026, followed by December 29, 2006; December 31, 2009;
July 31, 2020; and June 30, 2023. Columns use 3-, 5- and 10-year half-lives.
`current_curve_surfaces.png` and `historical_yield_surface.png` are separate views.

Historical surface interpolation is across maturity within an observed date,
not across calendar time. It does not extrapolate outside available maturities;
unavailable regions can remain blank. See `historical_surface_coverage.csv`,
`historical_excluded_quotes.csv` and `run_summary.md` for the treatment of gaps.
The historical starting scenarios use the same current-vintage anchors as the
current scenario; they are not historical point-in-time forecasts or backtests.

## 9. Verify And Preserve The Review Trail

The complete test suite also tests Word conversion. Install its optional
dependencies before running the suite; they are not needed for surfaces.

```powershell
python -m pip install -e ".[documents]"
python -m unittest discover -s tests -v
git rev-parse HEAD
python -m pip freeze
```

Tests validate code behavior; they do not prove Bloomberg authorization, source
availability or economic suitability. Preserve the Git commit, environment
versions, configuration files, raw bundles and analysis/plot bundles for a
reviewed numerical snapshot. Each run writes a dated folder under `data/` with
a manifest and source/output hashes; processing and analysis runs also write
Markdown summaries. Do not edit archived inputs in place.

`data/` is excluded from GitHub. A clone retrieves code, configuration and
methodology documents, not downloaded data or generated plots. A fresh download
uses the source's available vintage and may not reproduce an old run exactly.
Existing manifests also contain local absolute paths, so copying an old `data/`
directory to a different path is not a guaranteed portable reproduction method.
The commands above rebuild a consistent chain of bundles on the new machine.

By default, each task chooses the latest applicable bundle by manifest kind.
For multiple research runs, pin inputs with `--official-archive` and
`--treasury-bundle` for analysis, `--review-bundle` for projection, and
`--curve-bundle` for surfaces. Use the printed local bundle paths. See
`python main.py --help` for all flags.

Bond benchmark histories, analytics, the Bloomberg composition workbook,
credit loss assumptions and foreign-cash calibration are not prerequisites for
this yield-curve surface workflow. Word conversion dependencies are also
optional and are outside this walkthrough.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `conda` not recognized | Initialize using the installed Anaconda/Miniconda prompt; reopen the terminal |
| Wrong Python or missing packages | Activate `my_env`, check `sys.executable`, install with `python -m pip` |
| Bloomberg port unavailable | Confirm local Terminal/Desktop API is installed, running and logged in; otherwise use public-only path |
| Bloomberg entitlement or DLL error | Check authorized API access and the Bloomberg runtime; a reachable port is not enough |
| Treasury download appears slow | Watch annual progress; the request timeout is 30 seconds; retry a failed task after checking network/proxy access |
| Official-source download or parser fails | Read the named source/error; inspect its archive, rather than silently substituting or filling missing data |
| No applicable archived bundle | Run the prerequisite task and confirm it finished successfully |
| Settings/hash mismatch | Keep archives unchanged; rerun the upstream review/projection with the intended settings |
| Blank regions in historical surface | Inspect coverage; missing edge maturities are deliberately not extrapolated |

## Make This Guide Available On GitHub

This file and the README link must be committed and pushed from the source
machine before another computer can clone them. If these are the only changes
you intend to publish, run from the source repository:

```powershell
git status -sb
git add README.md docs/FRESH_MACHINE_SETUP.md
git commit -m "Document fresh-machine yield curve workflow"
git push origin main
```

Do not commit credentials or redistribute Bloomberg data contrary to your data
license. The guide does not upload or push anything automatically.
