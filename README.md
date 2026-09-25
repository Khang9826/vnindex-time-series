# Phân tích dữ liệu chuỗi thời gian VN-Index

Reproducible time-series analysis of the VN-Index (HOSE composite index), from
data collection through statistical testing to forecasting.

**Project status: IN PROGRESS** — stages 1–7 of the workflow are implemented
and executed; volatility modelling, forecasting, evaluation and the written
report are not yet implemented (see *Execution status* below).

---

## 1. Data

**Primary source** — Kaggle dataset
[`keithvo/vnstockdata`](https://www.kaggle.com/datasets/keithvo/vnstockdata)
("Vietnam Stock Intraday (VNINDEX, VN30, VN100)"), file
`HOSE_DLY_VNINDEX1D.csv`, licensed **DbCL-1.0**, upstream last updated
2025-12-12.

| Item | Value |
|---|---|
| Series | VN-Index daily OHLCV |
| Period **actually used** | 2000-07-28 → 2025-12-11 |
| Observations | 6,179 trading sessions |
| Variables | `Date, Open, High, Low, Close, Volume` |
| Adjusted close | **Not available** — VN-Index is a price index; no source publishes one |

The source file is **vendored** into `data/raw/kaggle_HOSE_DLY_VNINDEX1D.csv`
so the exact vintage behind every reported number ships with the project and
the analysis stays reproducible after the dataset is updated upstream.
`data/raw/vnindex_raw.csv` is the canonical file built from it; provenance is in
`data/raw/vnindex_raw_meta.json`. Neither is edited by any downstream stage.

Two source-side properties are handled explicitly rather than silently:

* **The final bar (2025-12-12) is an incomplete session and is dropped.** The
  dataset was published at 06:36 UTC on that date, i.e. mid-session in Vietnam.
  Its volume is 288.0 M against a 21-session median of 723.2 M, and it is the
  single largest disagreement with the independent cross-check feed in the whole
  sample. The drop is recorded in the metadata.
* **`Open` is a carry-over of the previous close on 18.6 % of rows** — an
  upstream feed artefact. The analysis is built on `Close`, so this is
  documented and reported in the metadata, not repaired.

The dataset also contains VN30, VN100 and USD/VND series and 30 M / 1 H / 4 H
intraday bars. **None of them is used yet**; only the daily VN-Index file is in
scope for the current milestone.

### Source cross-check (verified, `results/source_crosscheck.json`)

The primary source is a third-party redistribution, not an official HOSE
publication, so it is corroborated against a completely independent feed — the
DNSE/Entrade public chart API (`src/data_crosscheck.py`). That feed's vintage is
stored in `data/raw/entrade_api_vnindex_1d.csv`.

| Metric | Result |
|---|---|
| Common sessions | 6,136 |
| Close correlation | 0.99999942 |
| Median abs. relative difference | 3.08e-08 |
| Max abs. relative difference | 1.67e-02 |
| Sessions only in primary | 43 |
| Sessions only in secondary | **0** |
| Unexplained calendar gaps — primary | **1** (3 business days) |
| Unexplained calendar gaps — secondary | 6 (26 business days) |

The two feeds agree to floating-point precision on a typical day. Level
disagreements above 0.1 % (505 sessions, 8.2 %) are concentrated in the
thin-market years 2003–2008 and never exceed 2 % on any session. Critically,
**the primary source covers 43 sessions the secondary feed is missing and is
missing none that the secondary has** — including the entire
2021-01-21 → 2021-02-04 stretch (11 consecutive sessions) absent from the API
feed. Residual vendor disagreement is reported as a limitation, not hidden.

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

## 3. Project structure

```
TimeSeries/
├── data/
│   ├── raw/        kaggle_HOSE_DLY_VNINDEX1D.csv   (vendored primary source)
│   │               vnindex_raw.csv + _meta.json    (canonical, never edited)
│   │               entrade_api_vnindex_1d.csv      (secondary, cross-check only)
│   └── processed/  vnindex_clean.csv, vnindex_features.csv
├── src/
│   ├── config.py           paths, seed, alpha, split fractions, source config
│   ├── data_loader.py      build canonical raw from the vendored source
│   ├── data_crosscheck.py  independent corroboration vs. a second feed
│   ├── data_quality.py     inspection only, changes nothing
│   ├── preprocessing.py    clean + returns + calendar features
│   ├── analysis.py         descriptive stats, normality, outliers, calendar effects
│   ├── stationarity.py     ADF + KPSS suite
│   ├── autocorrelation.py  ACF/PACF + Ljung-Box
│   ├── plots.py            report-ready figures
│   └── run_all.py          end-to-end pipeline runner
├── figures/        01..09 PNG, 150 dpi
├── results/        JSON + CSV, one file per analysis stage
├── reports/        build_report.js  — generates the Word report from results/
│                   BaoCao_PhanTichChuoiThoiGian_VNIndex.docx (+ .pdf)
├── tests/          pytest suite
└── requirements.txt
```

## 4. How to run

```bash
pip install -r requirements.txt
python src/run_all.py
python -m pytest tests -q
```

The pipeline runs entirely from the vendored source file — no network access is
required. `python src/run_all.py --refresh-crosscheck` re-downloads the
secondary feed instead of using its stored vintage; the cross-check stage is
skipped gracefully if the network is unavailable. Individual stages can be run
on their own from inside `src/`, e.g. `python stationarity.py`.

Reproducibility: `config.RANDOM_SEED = 42` is used for every sampling step
(currently the Shapiro-Wilk sub-sample); no other stage uses randomness. Because
the primary source is a vendored file rather than a live API, re-running the
pipeline reproduces the numbers above exactly.

---

## 5. Execution status

| Component | Status |
|---|---|
| Primary-source ingestion (`data_loader.py`) | **VERIFIED** — 6,179 sessions, 1 partial bar dropped |
| Source cross-check (`data_crosscheck.py`) | **VERIFIED** — corr 0.99999942 vs independent feed |
| Data-quality inspection (`data_quality.py`) | **VERIFIED** — 0 defects, 1 unexplained calendar gap |
| Preprocessing / returns (`preprocessing.py`) | **VERIFIED** — 6,178 returns computed |
| Descriptive statistics + normality (`analysis.py`) | **VERIFIED** |
| Outlier / extreme-move listing (`analysis.py`) | **VERIFIED** |
| Calendar-effect tests (`analysis.py`) | **VERIFIED** |
| Stationarity ADF + KPSS (`stationarity.py`) | **VERIFIED** |
| ACF / PACF + Ljung-Box (`autocorrelation.py`) | **VERIFIED** |
| Figures 01–09 | **VERIFIED** — files exist on disk |
| Test suite (`tests/`) | **VERIFIED** — 19 passed |
| Vietnamese Word report (`reports/`) | **VERIFIED** — 40 pages, built from `results/`, TOC/figure/table lists populated |
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
