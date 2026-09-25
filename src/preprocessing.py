"""
Reproducible preprocessing pipeline: raw -> clean -> feature table.

Design decisions (all of them auditable, none of them silent):

1.  The raw file is never edited.  This module reads it and writes NEW files
    under data/processed/.
2.  Rows are ordered chronologically and de-duplicated on Date.  (The quality
    report shows zero duplicates in the current vintage; the step is kept so
    the pipeline stays correct for future re-downloads.)
3.  Non-trading days are NOT inserted and NOT interpolated.  The series is
    treated as an ordered sequence of trading sessions, which is the standard
    convention for financial time series: inserting weekends/holidays would
    create artificial zero returns and bias every variance estimate downwards.
4.  Bars whose Open/Close fall outside [Low, High] are FLAGGED, not removed.
    They are a source-side recording issue in the High/Low fields; the Close
    series - the only price series used in the analysis - is unaffected.
5.  Outliers in the return series are NOT removed here.  Whether an extreme
    return is a genuine market move or a data error is decided in the outlier
    analysis (src/analysis.py), not by a blanket rule in preprocessing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
from data_loader import load_raw

PRICE_COLS = ["Open", "High", "Low", "Close"]


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()

    # 1. types ------------------------------------------------------------
    df["Date"] = pd.to_datetime(df["Date"])
    for c in PRICE_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").astype("Int64")

    # 2. chronological order, one row per session -------------------------
    df = df.sort_values("Date", kind="mergesort").reset_index(drop=True)
    n_before = len(df)
    df = df.drop_duplicates(subset="Date", keep="last").reset_index(drop=True)
    n_dropped_dup = n_before - len(df)

    # 3. flag internally inconsistent OHLC bars (keep the rows) -----------
    df["ohlc_inconsistent"] = (
        (df["High"] < df["Low"])
        | (df["Close"] > df["High"])
        | (df["Close"] < df["Low"])
        | (df["Open"] > df["High"])
        | (df["Open"] < df["Low"])
    )

    # 4. drop the source-internal unix timestamp helper column ------------
    df = df.drop(columns=[c for c in ("t",) if c in df.columns])

    df.attrs["n_dropped_duplicate_dates"] = n_dropped_dup
    return df


def add_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add price-change and return columns based on the closing price.

        Change_t = P_t - P_{t-1}
        R_t      = (P_t - P_{t-1}) / P_{t-1}          (simple return)
        r_t      = ln(P_t / P_{t-1})                  (log return)

    Returns are expressed as fractions; *_pct columns give percent for
    readability.  The first observation has no predecessor and is NaN by
    construction - it is never filled.
    """
    out = df.copy()
    p = out["Close"]

    out["Change"] = p.diff()
    out["SimpleReturn"] = p.pct_change()
    out["LogReturn"] = np.log(p / p.shift(1))
    out["SimpleReturn_pct"] = out["SimpleReturn"] * 100.0
    out["LogReturn_pct"] = out["LogReturn"] * 100.0

    # calendar features used later by the seasonality analysis
    out["Year"] = out["Date"].dt.year
    out["Month"] = out["Date"].dt.month
    out["Weekday"] = out["Date"].dt.day_name()
    out["SessionGapDays"] = out["Date"].diff().dt.days

    # How many business days the source skipped before this session, and
    # whether that skip is explained by a public holiday.  A return computed
    # across an unexplained gap is a multi-session move mislabelled as a
    # one-day move; the flag lets any downstream step exclude those rows with
    # an explicit justification instead of a silent filter.
    out["MissingBusinessDaysBefore"] = _missing_business_days_before(out["Date"])
    out["SpansUnexplainedGap"] = _unexplained_gap_flag(out["Date"])

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


def run() -> pd.DataFrame:
    raw = load_raw()
    cleaned = clean(raw)
    features = add_returns(cleaned)

    cleaned.to_csv(config.CLEAN_CSV, index=False)
    features.to_csv(config.FEATURES_CSV, index=False)

    print(f"raw rows            : {len(raw)}")
    print(f"duplicate dates drop: {cleaned.attrs['n_dropped_duplicate_dates']}")
    print(f"clean rows          : {len(cleaned)}")
    print(f"OHLC-inconsistent   : {int(cleaned['ohlc_inconsistent'].sum())} rows (flagged, kept)")
    print(f"period              : {cleaned['Date'].min().date()} -> {cleaned['Date'].max().date()}")
    print(f"returns available   : {int(features['LogReturn'].notna().sum())} observations")
    print(f"spans unexplained gap: {int(features['SpansUnexplainedGap'].sum())} returns flagged (kept)")
    print(f"NaN log-returns     : {int(features['LogReturn'].isna().sum())} (first session, by construction)")
    print(f"written             : {config.CLEAN_CSV.name}, {config.FEATURES_CSV.name}")
    return features


def load_features() -> pd.DataFrame:
    """Load the feature table with a proper DatetimeIndex kept as a column too."""
    df = pd.read_csv(config.FEATURES_CSV, parse_dates=["Date"])
    return df


if __name__ == "__main__":
    run()
