# Phân tích dữ liệu chuỗi thời gian VN-Index

Reproducible time-series analysis of the VN-Index (HOSE composite index), from
data collection through statistical testing to forecasting.

**Project status: IN PROGRESS** — stages 1–7 of the workflow are implemented
and executed; volatility modelling, forecasting, evaluation and the written
report are not yet implemented (see *Execution status* below).

---

## 1. Data

**Source** — Kaggle dataset
[`keithvo/vnstockdata`](https://www.kaggle.com/datasets/keithvo/vnstockdata)
("Vietnam Stock Intraday (VNINDEX, VN30, VN100)"), licensed **DbCL-1.0**,
upstream last updated 2025-12-12.

**All 19 CSV files in the dataset are used.** Every one is vendored into
`data/raw/kaggle/` so the exact vintage behind every reported number ships with
the project. [src/catalog.py](src/catalog.py) is the registry describing what
each file is; `results/series_inventory.json` records what was built from it.

**225,945 bars across 19 series.**

The dataset ships two families that differ in schema and in how far they run:

| Family | Schema | Volume | Ends | Timeframes |
|---|---|---|---|---|
| `HOSE_DLY_*` (6 files) | `time,open,high,low,close,55EMA,89EMA,200EMA,Volume` | yes | 2025-12-12 | 1D, M30 |
| `HOSE*` (13 files) | `time,open,high,low,close,55EMA,89EMA,200EMA,Plot` | no | 2024-12-09 | 1D, H1, H4, M30 |

Neither family covers everything, so the project picks a **primary** file per
(symbol, timeframe) and keeps the overlapping other-family file as an
independent **cross-check** vintage:

* `HOSE_DLY` is primary wherever it exists — it carries volume and runs a year
  further.
* `HOSE` is primary for H1 and H4, which `HOSE_DLY` does not publish at all,
  and for USD/VND, which only `HOSE` publishes.

**13 primary series + 6 cross-check vintages:**

| Symbol | 1D | H4 | H1 | M30 |
|---|---|---|---|---|
| VN-Index | 2000-07-28 → 2025-12-11 (6,179) | 2012-02-24 → 2024-12-09 (6,378) | 2012-02-24 → 2024-12-09 (15,924) | 2017-01-03 → 2025-12-11 (22,212) |
| VN30 | 2012-09-10 → 2025-12-11 (3,310) | 2012-09-10 → 2024-12-09 (6,106) | 2012-09-10 → 2024-12-09 (15,252) | 2017-01-03 → 2025-12-11 (22,028) |
| VN100 | 2014-01-27 → 2025-12-11 (2,963) | 2014-01-27 → 2024-12-09 (5,417) | 2014-01-27 → 2024-12-09 (13,543) | 2017-01-03 → 2025-12-11 (22,179) |
| USD/VND | 1997-08-20 → 2024-12-09 (6,515) | — | — | — |

VN-Index daily remains the **headline series** — the one the deep-dive chapters
and the written report analyse. The rest support the comparative analysis in
section 2b.

### Trading calendar (verified from the bar timestamps, not assumed)

HOSE runs 09:00–11:30 and 13:00–14:45 (Asia/Ho_Chi_Minh), so a full day is
**10 M30 bars, 5 H1 bars, 2 H4 bars**. Two consequences are handled explicitly
rather than ignored:

* The last bar of each session is a **stub** — the 11:30 M30 bar covers only
  15 minutes and the 11:00 H1 bar only 30. "H4" is really one bar per half-day
  session, not a four-hour clock bar.
* On an intraday grid consecutive bars are **not equally spaced in real time**.
  The first bar of a day spans the overnight gap (~18 hours) and the 13:00 bar
  spans the lunch break. These are flagged (`SpansOvernight`,
  `SpansLunchBreak`) and excluded from the intraday statistics, because mixing
  a one-day return into a sample of 30-minute returns would corrupt every
  moment estimate. At H4 every bar spans a break, so there the distinction
  collapses and all bars are used — stated, not silently special-cased.

### Handling of source quirks

* **Incomplete tails.** The `HOSE_DLY` files were published mid-session on
  2025-12-12. Daily bars are dropped when volume falls below 60 % of the recent
  median (observed 0.40–0.47 across the three indices); intraday series drop the
  whole final day when it carries fewer bars than a full session (observed 7 of
  10). **6 incomplete tails trimmed.** The `HOSE` family ends with complete
  sessions and is not trimmed — verified, not assumed.
* **Pre-computed indicators.** 55/89/200 EMA are derived from Close and are
  dropped on load so nothing indicator-shaped leaks into the models. The `HOSE`
  family's `Plot` column is empty in every row and is dropped too.
* **Stale opens.** `Open` sometimes merely repeats the previous close — 18.6 %
  of rows for VN-Index daily and **64.7 % for USD/VND**. The analysis is built
  on `Close`; the rate is measured and recorded per series rather than
  "repaired".
* **Adjusted close does not exist** for any of these series — they are price
  indices and an FX rate.

### Cross-checks

Two independent checks, because a single third-party redistribution is weak
evidence on its own:

1. **Against a different vendor** (`results/source_crosscheck.json`) — the
   DNSE/Entrade public API, for VN-Index daily: close correlation
   **0.99999942**, median absolute relative difference **3.08e-08** over 6,136
   common sessions. The Kaggle file additionally covers 43 sessions the API
   lacks (including all of 2021-01-21 → 2021-02-04) and is missing none the API
   has.
2. **Between the two families** (`results/cross_family_checks.csv`) — VN100
   daily agrees to float precision (max relative difference 7.7e-08). VN-Index
   and VN30 daily disagree on 1.9 % and 2.8 % of bars by more than 0.1 %, and
   **those disagreements sit almost entirely in 2012–2013** (111 of 112 cases
   for VN-Index). That window is a known weak spot in this dataset and is
   reported as a limitation.

### Data-quality findings (verified, `results/data_quality_report.json`)

* 0 missing values, 0 duplicated dates, 0 fully duplicated rows.
* Dates strictly increasing; 0 weekend sessions.
* 0 non-positive prices, 0 negative volumes, 0 zero-volume sessions.
* **0 bars** with `Open` or `Close` outside `[Low, High]`, and 0 with
  `High < Low` — the OHLC bars are internally consistent throughout.
* Of the 71 calendar gaps skipping ≥ 2 business days, **70 are consistent with
  a Vietnamese public-holiday window** (Tết, Hung Kings, Reunification/Labour,
  National Day, New Year) and **1 is unexplained**: 2008-05-26 → 2008-05-30,
  3 business days. The single return computed across it is flagged
  (`SpansUnexplainedGap`), not removed.
* The 2000–2002 period, when HOSE traded only three sessions per week, is
  visible as a cluster of two-calendar-day gaps in the gap distribution.

### Preprocessing decisions

* Non-trading days are **not** inserted and **not** interpolated. The series is
  an ordered sequence of trading sessions; inserting weekends/holidays would
  create artificial zero returns and bias every variance estimate downwards.
* Extreme returns are **not** removed in preprocessing. Whether a move is a
  genuine market event or a data error is decided in the outlier analysis.
* Pre-computed indicator columns shipped in the source file (55/89/200 EMA) are
  dropped on load — they are derived from `Close`, and recomputing anything we
  need keeps the pipeline self-contained.
* Returns are computed from `Close`:
  `Change_t = P_t − P_{t−1}`, `R_t = (P_t − P_{t−1})/P_{t−1}`,
  `r_t = ln(P_t/P_{t−1})`. The first observation is NaN by construction and is
  never filled.

---

## 2. Verified findings so far

All numbers below were produced by an actual execution of the code in this
repository against the vintage described above.

**Descriptive statistics** (`results/descriptive_statistics.csv`)

| | Close (points) | Daily log return (%) |
|---|---|---|
| n | 6,179 | 6,178 |
| mean | 688.59 | 0.0458 |
| median | 573.20 | 0.0672 |
| std | 387.15 | 1.4384 |
| min / max | 100.00 / 1,766.85 | −7.6557 / 6.6561 |
| skewness | 0.508 | −0.419 |
| excess kurtosis | −0.752 | 3.581 |

The return range is bounded near ±7 %, consistent with the HOSE daily
price-limit band applying to the constituent stocks.

**Normality of returns** — rejected by all three tests
(`results/normality_tests.csv`): Jarque-Bera = 3475.06 (p ≈ 0),
D'Agostino-Pearson K² = 685.15 (p = 1.7e-149), Shapiro-Wilk on a seeded
5,000-observation sub-sample W = 0.9376 (p = 1.3e-41). Days beyond ±3σ: 116
observed vs 16.7 expected under normality (7.0×); beyond ±4σ: 36 vs 0.39 (92×).

**Stationarity** (`results/stationarity_tests.csv`, α = 0.05) — ADF and KPSS agree:

| Series | ADF stat | ADF p | KPSS stat | KPSS p | Verdict |
|---|---|---|---|---|---|
| Level (c) | −0.738 | 0.837 | 10.121 | ≤0.01 | non-stationary |
| Level (ct) | −2.604 | 0.278 | 0.969 | ≤0.01 | non-stationary |
| log(level) (c) | −2.056 | 0.262 | 10.265 | ≤0.01 | non-stationary |
| log(level) (ct) | −3.355 | 0.058 | 0.428 | ≤0.01 | non-stationary |
| First difference | −12.107 | 2.0e-22 | 0.102 | ≥0.10 | stationary |
| Log return | −17.510 | 4.3e-30 | 0.091 | ≥0.10 | stationary |

The level behaves as an I(1) process; first differencing (i.e. working in
returns) achieves stationarity.

**Autocorrelation** (`results/autocorrelation.json`, `ljung_box_tests.csv`)

* Log returns: ACF(1) = 0.237, then a sharp drop. 17 of 40 lags exceed the
  ±0.0248 white-noise band. Ljung-Box rejects white noise at every horizon
  tested (Q(10) = 483.46, p = 1.5e-97).
* Volatility proxies are far more persistent: ACF(1) = 0.460 for |r| and 0.509
  for r², significant at **all 40 lags**.

Read together: returns carry a genuine but modest short-lag dependence (an AR(1)
or low-order ARMA mean model is justified), and their magnitudes cluster strongly
(a conditional-variance model is justified — to be tested formally in the
volatility stage).

**Calendar effects** (`results/eda_results.json`)

* Day-of-week: ANOVA F = 6.088 (p = 6.9e-05) and Kruskal-Wallis H = 16.608
  (p = 0.0023) both reject equality of the weekday return distributions.
  Monday has the lowest mean (−0.084 %), Friday the highest (+0.149 %).
  Levene's test also rejects equal variance across weekdays
  (W = 13.625, p = 4.6e-11).
* Calendar month: ANOVA F = 1.181 (p = 0.294) and Kruskal-Wallis H = 17.234
  (p = 0.101) — **neither rejects at α = 0.05**. There is no statistical
  evidence of a monthly effect in this sample, and therefore no justification
  for a seasonal (SARIMA) specification on that basis.

A statistically detectable weekday effect is *not* the same as seasonality in
the time-series sense, and not the same as a tradable pattern. Whether it
survives controls for volatility and sub-period is not yet tested.

**Extreme movements** (`results/eda_results.json`)

36 sessions (0.58 %) lie beyond ±4σ. **29 of them fall in 2001**, when HOSE
listed only a handful of stocks; the rest are 2014 (1), 2020 (2), 2021 (1) and
2025 (3). None coincides with an OHLC-inconsistent bar or the unexplained
calendar gap, so none is attributable to a known data defect. The largest
single-day move in the sample is **−7.66 % on 2001-07-11**; the largest gain is
**+6.66 % on 2001-10-08**. **No outlier is removed**; any later exclusion will be
stated and justified where it is made.

---

## 2b. Comparative findings across the whole dataset

Produced by [src/multiseries.py](src/multiseries.py) →
`results/multiseries_battery.json`, `multiseries_summary.csv`. Intraday
statistics use **regular bars only** (see the trading-calendar note above).

### What holds everywhere

Across all **13 primary series** — three equity indices, four sampling
frequencies, and an FX rate:

* **Every price level is non-stationary** (13/13, ADF and KPSS agreeing).
* **Every return distribution is non-normal** (13/13, Jarque-Bera rejecting at
  any conventional level).
* **Volatility clustering is universal** — Ljung-Box on squared returns rejects
  white noise at p < 1e-130 for every single series.

These are not VN-Index quirks. They are properties of the market.

### The result that required a control

The naive comparison looks dramatic: VN-Index daily has ACF(1) = **0.2366**
against VN30's 0.0411 and VN100's 0.0464 — five times the autocorrelation,
which invites the story that the broad index is far more predictable because it
holds illiquid small caps that price-adjust slowly.

**That story does not survive the control.** VN-Index daily starts in 2000,
VN30 in 2012 and VN100 in 2014, so the raw comparison confounds market segment
with sample period. Restricted to the 2,962 sessions all three cover
(2014-02-06 → 2025-12-11):

| Symbol | ACF(1), own sample | ACF(1), matched period | Significant? |
|---|---|---|---|
| VN-Index | 0.2366 | **0.0579** | yes |
| VN30 | 0.0411 | **0.0345** | no |
| VN100 | 0.0464 | **0.0464** | yes |

The gap collapses from 5× to about 1.7×. VN-Index's high autocorrelation is
overwhelmingly a **period effect** — it lives in the thin, narrow-band market
of 2000–2013, not in a structural difference between segments today. Any
statement about VN-Index's serial dependence that quotes the full-sample figure
without this caveat is misleading. See `figures/12_matched_period_and_correlation.png`.

### Sampling frequency

| Timeframe | sd (%) | sd × √(bars/day) | Excess kurtosis |
|---|---|---|---|
| M30 | 0.2991 | 0.9458 | 10.85 |
| H1 | 0.4073 | 0.9107 | 7.92 |
| H4 | 0.7993 | 1.1304 | 8.36 |
| 1D | 1.4384 | 1.4384 | 3.58 |

(VN-Index; each row is its own sample period, so this is indicative rather than
a controlled test.) Two patterns: volatility scales roughly with √time for VN30
and VN100 (0.94–1.16 against a daily 1.19), while VN-Index's daily figure is
inflated by its long early history; and **tail weight falls monotonically as
bars widen** — excess kurtosis drops from ~11 at 30 minutes to ~3.6 daily,
the classic aggregational-Gaussianity effect.

### Intraday structure

30-minute VN-Index returns show a clear time-of-day pattern
(`figures/14_intraday_pattern.png`): volatility peaks at the 09:00 open,
declines through the morning, and rises again into the 14:00 bar ahead of the
close. The 11:30 bar has visibly the lowest volatility of the day — which is an
artefact worth naming, since that bar covers only 15 minutes, not 30.

### Cross-asset

Daily log returns over 2,700 common sessions: the three equity indices move
almost as one (VN30–VN100 0.989, VN-Index–VN100 0.974, VN-Index–VN30 0.966),
while **USD/VND is mildly negatively correlated with all three (≈ −0.10)** —
VND depreciation tends to coincide with equity weakness, though the association
is weak.

### USD/VND is a different animal — and the weakest data

Reported with caveats rather than presented as a peer of the equity series:

* Excess kurtosis **107.5**, against 3.6–5.2 for the equity indices.
* ACF(1) = **−0.3617** — strong *negative* autocorrelation, the opposite sign
  to every equity series.
* `Open` repeats the previous close on **64.7 %** of rows, so its O/H/L are
  largely uninformative.
* 121 gaps of ≥ 2 business days, **98 of them before 2007**, i.e. the early
  history is sparse rather than daily.

These are consistent with a managed exchange rate quoted in whole VND: long
flat stretches punctuated by discrete jumps, which mechanically produce both
huge kurtosis and mean-reverting first differences. The pre-2007 portion should
not be treated as a clean daily series.

### Where the tests disagree

Return-series stationarity is **AMBIGUOUS** (both ADF and KPSS reject their own
null) for all three H1 series and for USD/VND. Reported as ambiguous rather
than resolved in whichever direction would be tidier.

## 3. Project structure

```
TimeSeries/
├── data/
│   ├── raw/
│   │   ├── kaggle/     all 19 vendored source CSVs (the dataset, verbatim)
│   │   ├── vnindex_raw.csv + _meta.json   canonical headline series
│   │   └── entrade_api_vnindex_1d.csv     external cross-check vintage
│   └── processed/
│       ├── vnindex_clean.csv, vnindex_features.csv   headline series
│       ├── series_raw/        canonical raw, one file per catalogued series
│       └── series_features/   feature tables, one file per series
├── src/
│   ├── config.py            paths, seed, alpha, split fractions
│   ├── catalog.py           registry of all 19 files: symbol, timeframe,
│   │                        family, primary/cross-check role, session structure
│   ├── data_loader.py       ingest any series; trim incomplete tails
│   ├── data_crosscheck.py   corroboration against an external feed
│   ├── data_quality.py      inspection only, changes nothing
│   ├── preprocessing.py     clean + returns + calendar/session bookkeeping
│   ├── analysis.py          descriptives, normality, outliers, calendar effects
│   ├── stationarity.py      ADF + KPSS suite
│   ├── autocorrelation.py   ACF/PACF + Ljung-Box
│   ├── multiseries.py       the battery across every series + matched-period
│   │                        control, frequency scaling, correlations
│   ├── plots.py             headline figures (01-09)
│   ├── plots_multiseries.py comparative figures (10-14)
│   └── run_all.py           end-to-end pipeline runner
├── figures/        01..14 PNG, 150 dpi
├── results/        JSON + CSV, one file per analysis stage
├── reports/        build_report.js  — generates the Word report from results/
│                   BaoCao_PhanTichChuoiThoiGian_VNIndex.docx
├── tests/          pytest suite (test_pipeline.py, test_multiseries.py)
└── requirements.txt
```

## 4. How to run

```bash
pip install -r requirements.txt
python src/run_all.py
python -m pytest tests -q
```

The full run covers all 19 series in about 66 seconds and needs **no network
access** — everything comes from the vendored files. Useful variants:

```bash
python src/run_all.py --headline-only      # just the VN-Index daily deep dive
python src/run_all.py --refresh-crosscheck # re-pull the external API vintage
```

The external cross-check stage is skipped gracefully if the network is
unavailable. Individual stages run on their own from inside `src/`, e.g.
`python catalog.py`, `python multiseries.py`, `python stationarity.py`.

Reproducibility: `config.RANDOM_SEED = 42` is used for every sampling step
(currently the Shapiro-Wilk sub-sample); no other stage uses randomness. Because
the primary source is a vendored file rather than a live API, re-running the
pipeline reproduces the numbers above exactly.

---

## 5. Execution status

| Component | Status |
|---|---|
| Series catalogue (`catalog.py`) | **VERIFIED** — all 19 dataset files registered, none ignored |
| Multi-series ingestion (`data_loader.py`) | **VERIFIED** — 225,945 bars, 6 incomplete tails trimmed |
| External cross-check (`data_crosscheck.py`) | **VERIFIED** — corr 0.99999942 vs independent feed |
| Cross-family checks (`multiseries.py`) | **VERIFIED** — 6 HOSE/HOSE_DLY pairs compared |
| Data quality, all series (`data_quality.py`) | **VERIFIED** — 19 series, **0 defects** |
| Preprocessing / returns (`preprocessing.py`) | **VERIFIED** — 225,926 returns, session bookkeeping |
| Descriptive statistics + normality (`analysis.py`) | **VERIFIED** |
| Outlier / extreme-move listing (`analysis.py`) | **VERIFIED** |
| Calendar-effect tests (`analysis.py`) | **VERIFIED** |
| Stationarity ADF + KPSS (`stationarity.py`) | **VERIFIED** — headline series |
| ACF / PACF + Ljung-Box (`autocorrelation.py`) | **VERIFIED** — headline series |
| Comparative battery (`multiseries.py`) | **VERIFIED** — 13 primary series |
| Matched-period control (`multiseries.py`) | **VERIFIED** — 4 timeframes |
| Frequency scaling + correlations (`multiseries.py`) | **VERIFIED** |
| Figures 01–14 | **VERIFIED** — files exist on disk |
| Test suite (`tests/`) | **VERIFIED** — 176 passed |
| Vietnamese Word report (`reports/`) | **VERIFIED** — 50 pages, 23 tables, 14 figures; covers the headline series **and** the multi-series analysis |
| Volatility modelling (ARCH-LM, GARCH) | **NOT IMPLEMENTED** |
| Chronological train/val/test split | **NOT IMPLEMENTED** |
| Forecasting models (naive, MA, ETS, ARIMA) | **NOT IMPLEMENTED** |
| Forecast evaluation vs naive baseline | **NOT IMPLEMENTED** |
| Residual diagnostics of fitted models | **NOT IMPLEMENTED** |
| Notebooks | **NOT IMPLEMENTED** |

## 6. Sources

**SOURCE-DERIVED INFORMATION**

1. Kaggle dataset `keithvo/vnstockdata`, "Vietnam Stock Intraday (VNINDEX,
   VN30, VN100)", file `HOSE_DLY_VNINDEX1D.csv`, licensed DbCL-1.0, upstream
   last updated 2025-12-12. <https://www.kaggle.com/datasets/keithvo/vnstockdata>
   — the VN-Index price and volume data analysed here.
2. DNSE / Entrade public chart API,
   `https://services.entrade.com.vn/chart-api/v2/ohlcs/index` — used **only**
   to corroborate source 1, never as the basis of a reported number.

**RESULTS GENERATED BY THIS PROJECT** — every statistic, test result and figure
in `results/` and `figures/`.

No external literature is cited yet. References will be added only when they are
actually consulted.
