"""
Reproducible preprocessing: raw -> clean -> feature table, for any series.

Design decisions (all auditable, none silent):

1.  The vendored source files are never edited. This module reads the
    canonical raw artefacts and writes NEW files under data/processed/.
2.  Rows are ordered chronologically and de-duplicated on the bar timestamp.
3.  Non-trading periods are NOT inserted and NOT interpolated. Each series is
    treated as an ordered sequence of bars, the standard convention for
    financial data: inserting weekends, holidays or the lunch break would
    create artificial zero returns and bias every variance estimate downwards.
4.  Bars whose Open/Close fall outside [Low, High] are FLAGGED, not removed.
5.  Outliers are NOT removed here. Whether an extreme return is a genuine
    market move or a data error is decided in the outlier analysis.

Intraday series get one extra piece of bookkeeping that daily series do not
need. A bar's return is measured against the PREVIOUS bar, and on an intraday
grid consecutive bars are not equally spaced in real time:

    * the first bar of a session spans the overnight gap (~18 hours),
    * the 13:00 bar spans the 11:45-13:00 lunch break,
    * every other bar spans one ordinary interval.

Lumping these together would mix a one-day return into a sample of 30-minute
returns. They are therefore flagged (`SpansOvernight`, `SpansLunchBreak`,
`IsRegularBar`) so any downstream step can restrict itself to comparable
observations with an explicit, stated choice.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import catalog
import config
from data_loader import load_raw

PRICE_COLS = ["Open", "High", "Low", "Close"]


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()

    # 1. types ------------------------------------------------------------
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df["Date"] = pd.to_datetime(df["Date"])
    for c in PRICE_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").astype("Int64")

    # 2. chronological order, one row per bar ------------------------------
    df = df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)
    n_before = len(df)
    df = df.drop_duplicates(subset="Timestamp", keep="last").reset_index(drop=True)
    n_dropped_dup = n_before - len(df)

    # 3. flag internally inconsistent OHLC bars (keep the rows) -----------
    df["ohlc_inconsistent"] = (
        (df["High"] < df["Low"])
        | (df["Close"] > df["High"])
        | (df["Close"] < df["Low"])
        | (df["Open"] > df["High"])
        | (df["Open"] < df["Low"])
    )

    df = df.drop(columns=[c for c in ("time",) if c in df.columns])
    df.attrs["n_dropped_duplicate_bars"] = n_dropped_dup
    return df


def add_returns(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """
    Add price-change and return columns based on the closing price.

        Change_t = P_t - P_{t-1}
        R_t      = (P_t - P_{t-1}) / P_{t-1}          (simple return)
        r_t      = ln(P_t / P_{t-1})                  (log return)

    Returns are fractions; *_pct columns give percent for readability. The
    first observation has no predecessor and is NaN by construction - it is
    never filled.
    """
    series = catalog.get(key)
    out = df.copy()
    p = out["Close"]

    out["Change"] = p.diff()
    out["SimpleReturn"] = p.pct_change()
    out["LogReturn"] = np.log(p / p.shift(1))
    out["SimpleReturn_pct"] = out["SimpleReturn"] * 100.0
    out["LogReturn_pct"] = out["LogReturn"] * 100.0

    # calendar features used by the seasonality analysis
    out["Year"] = out["Timestamp"].dt.year
    out["Month"] = out["Timestamp"].dt.month
    out["Weekday"] = out["Timestamp"].dt.day_name()
    out["BarTime"] = out["Timestamp"].dt.strftime("%H:%M")

    if series.is_intraday:
        out = _add_intraday_flags(out, series)
    else:
        out = _add_daily_gap_flags(out, series)

    return out


# --------------------------------------------------------------------------
# Intraday bookkeeping
# --------------------------------------------------------------------------
def _add_intraday_flags(out: pd.DataFrame, series: catalog.Series) -> pd.DataFrame:
    first_bar = catalog.SESSION_BAR_TIMES[series.timeframe][0]
    afternoon_open = "13:00"

    out["BarOfDay"] = out.groupby("Date").cumcount() + 1
    out["BarsInDay"] = out.groupby("Date")["Close"].transform("size")
    out["IsFullSessionDay"] = out["BarsInDay"] == series.bars_per_day

    # A return spans the overnight gap when its bar is the first of a new day.
    out["SpansOvernight"] = out["Date"].ne(out["Date"].shift(1))
    out.loc[out.index[0], "SpansOvernight"] = False

    # ... and the lunch break when it is the first bar of the afternoon
    # session (and not already the first bar of the day).
    out["SpansLunchBreak"] = (out["BarTime"] == afternoon_open) & (~out["SpansOvernight"])
    if series.timeframe == "H4":
        # H4 has exactly one bar per half-day session, so the 13:00 bar is the
        # afternoon session itself rather than a bar following a break.
        out["SpansLunchBreak"] = (out["BarTime"] == afternoon_open) & (~out["SpansOvernight"])

    if series.timeframe == "H4":
        # At H4 there is exactly one bar per half-day session, so EVERY bar's
        # return spans either the overnight gap or the lunch break. The
        # "regular interval" distinction collapses and filtering on it would
        # discard the whole series, so every bar with a return counts as
        # regular here; the two span flags still say which break each crossed.
        out["IsRegularBar"] = out["LogReturn"].notna()
    else:
        out["IsRegularBar"] = ~(out["SpansOvernight"] | out["SpansLunchBreak"])
        out.loc[out["LogReturn"].isna(), "IsRegularBar"] = False
    out.attrs["first_bar_time"] = first_bar
    return out


# --------------------------------------------------------------------------
# Daily calendar bookkeeping
# --------------------------------------------------------------------------
def _add_daily_gap_flags(out: pd.DataFrame, series: catalog.Series) -> pd.DataFrame:
    """
    How many business days the source skipped before this session, and whether
    that skip is explained by a public holiday. A return computed across an
    unexplained gap is a multi-session move mislabelled as a one-period move;
    the flag lets any downstream step exclude those rows with an explicit
    justification instead of a silent filter.

    The holiday classifier encodes the HOSE calendar, so it is applied only to
    the HOSE-listed equity indices. USD/VND trades on a different calendar
    entirely; for it the gaps are still counted but NOT classified, because
    calling an FX gap "unexplained" against a Vietnamese equity holiday list
    would be a meaningless verdict.
    """
    out["SessionGapDays"] = out["Date"].diff().dt.days
    out["MissingBusinessDaysBefore"] = _missing_business_days_before(out["Date"])

    if catalog.ASSET_CLASS[series.symbol] == "equity index":
        out["SpansUnexplainedGap"] = _unexplained_gap_flag(out["Date"])
        out["GapClassified"] = True
    else:
        out["SpansUnexplainedGap"] = False
        out["GapClassified"] = False

    out["IsRegularBar"] = out["LogReturn"].notna()
    return out


def _missing_business_days_before(dates: pd.Series) -> pd.Series:
    vals = [pd.NA]
    for prev, nxt in zip(dates.iloc[:-1], dates.iloc[1:]):
        vals.append(
            len(pd.bdate_range(prev + pd.Timedelta(days=1), nxt - pd.Timedelta(days=1)))
        )
    return pd.Series(vals, index=dates.index, dtype="Int64")


def _unexplained_gap_flag(dates: pd.Series) -> pd.Series:
    """True when the preceding gap is not explained by a public holiday."""
    from data_quality import _classify_gap

    flags = [False]
    for prev, nxt in zip(dates.iloc[:-1], dates.iloc[1:]):
        missing = len(
            pd.bdate_range(prev + pd.Timedelta(days=1), nxt - pd.Timedelta(days=1))
        )
        if missing < 2:
            flags.append(False)
        else:
            flags.append(_classify_gap(prev, nxt, missing).startswith("UNEXPLAINED"))
    return pd.Series(flags, index=dates.index, dtype=bool)


# --------------------------------------------------------------------------
def build(key: str = catalog.HEADLINE_KEY, verbose: bool = False) -> pd.DataFrame:
    raw = load_raw(key)
    cleaned = clean(raw)
    features = add_returns(cleaned, key)

    if key == catalog.HEADLINE_KEY:
        cleaned.to_csv(config.CLEAN_CSV, index=False)
        features.to_csv(config.FEATURES_CSV, index=False)
    else:
        features.to_csv(config.series_features_csv(key), index=False)

    if verbose:
        series = catalog.get(key)
        print(f"raw rows            : {len(raw):,}")
        print(f"duplicate bars drop : {cleaned.attrs['n_dropped_duplicate_bars']}")
        print(f"clean rows          : {len(cleaned):,}")
        print(f"OHLC-inconsistent   : {int(cleaned['ohlc_inconsistent'].sum())} bars (flagged, kept)")
        print(f"period              : {cleaned['Timestamp'].min()} -> {cleaned['Timestamp'].max()}")
        print(f"returns available   : {int(features['LogReturn'].notna().sum()):,}")
        if series.is_intraday:
            print(f"spans overnight     : {int(features['SpansOvernight'].sum()):,} flagged")
            print(f"spans lunch break   : {int(features['SpansLunchBreak'].sum()):,} flagged")
            print(f"regular bars        : {int(features['IsRegularBar'].sum()):,}")
        else:
            print(f"spans unexplained gap: {int(features['SpansUnexplainedGap'].sum())} flagged (kept)")
    return features


def build_all(keys=None) -> dict:
    keys = keys or [s.key for s in catalog.SERIES]
    return {k: build(k) for k in keys}


def load_features(key: str = catalog.HEADLINE_KEY) -> pd.DataFrame:
    path = config.FEATURES_CSV if key == catalog.HEADLINE_KEY else config.series_features_csv(key)
    return pd.read_csv(path, parse_dates=["Timestamp", "Date"])


# Backwards-compatible alias used by the headline deep-dive modules.
def run() -> pd.DataFrame:
    return build(catalog.HEADLINE_KEY, verbose=True)


if __name__ == "__main__":
    feats = build_all()
    print(f"{'key':<22} {'bars':>8} {'returns':>9} {'regular':>9}  flags")
    print("-" * 88)
    for k, f in feats.items():
        s = catalog.get(k)
        if s.is_intraday:
            flags = (f"overnight={int(f['SpansOvernight'].sum()):,} "
                     f"lunch={int(f['SpansLunchBreak'].sum()):,}")
        else:
            flags = f"unexplained_gap={int(f['SpansUnexplainedGap'].sum())}"
        print(f"{k:<22} {len(f):>8,} {int(f['LogReturn'].notna().sum()):>9,} "
              f"{int(f['IsRegularBar'].sum()):>9,}  {flags}")
