"""
Data-quality inspection of the RAW VN-Index file.

Nothing here modifies the data: every function only *reports*.  The output is
a dictionary that is serialised to results/data_quality_report.json so the
findings can be cited in the written report.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import config


def basic_shape(df: pd.DataFrame) -> dict:
    return {
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "first_date": str(df["Date"].min().date()),
        "last_date": str(df["Date"].max().date()),
        "calendar_span_days": int((df["Date"].max() - df["Date"].min()).days),
    }


def missing_values(df: pd.DataFrame) -> dict:
    n_missing = df.isna().sum()
    return {
        "missing_per_column": {c: int(v) for c, v in n_missing.items()},
        "rows_with_any_missing": int(df.isna().any(axis=1).sum()),
    }


def duplicates(df: pd.DataFrame) -> dict:
    dup_dates = df["Date"].duplicated(keep=False)
    dup_rows = df.duplicated(keep=False)
    examples = (
        df.loc[dup_dates, "Date"].dt.strftime("%Y-%m-%d").unique()[:10].tolist()
        if dup_dates.any()
        else []
    )
    return {
        "n_duplicated_dates": int(df["Date"].duplicated().sum()),
        "n_rows_in_duplicate_date_groups": int(dup_dates.sum()),
        "n_fully_identical_rows": int(dup_rows.sum()),
        "example_duplicate_dates": examples,
    }


def ordering(df: pd.DataFrame) -> dict:
    return {
        "is_monotonic_increasing": bool(df["Date"].is_monotonic_increasing),
        "n_out_of_order_steps": int((df["Date"].diff().dt.days < 0).sum()),
    }


def impossible_values(df: pd.DataFrame) -> dict:
    """Internal consistency of an OHLC bar."""
    price_cols = ["Open", "High", "Low", "Close"]
    checks = {
        "non_positive_price": int((df[price_cols] <= 0).any(axis=1).sum()),
        "high_lt_low": int((df["High"] < df["Low"]).sum()),
        "close_outside_high_low": int(
            ((df["Close"] > df["High"]) | (df["Close"] < df["Low"])).sum()
        ),
        "open_outside_high_low": int(
            ((df["Open"] > df["High"]) | (df["Open"] < df["Low"])).sum()
        ),
        "negative_volume": int((df["Volume"] < 0).sum()),
        "zero_volume_sessions": int((df["Volume"] == 0).sum()),
    }
    zero_vol_dates = df.loc[df["Volume"] == 0, "Date"]
    checks["zero_volume_date_range"] = (
        [str(zero_vol_dates.min().date()), str(zero_vol_dates.max().date())]
        if len(zero_vol_dates)
        else None
    )
    return checks


def trading_calendar(df: pd.DataFrame) -> dict:
    """
    Describe the observed trading calendar.

    A gap is expected for weekends and public holidays: this function does NOT
    fill anything, it only quantifies how the observed sessions sit inside the
    calendar so that "missing trading days" can be discussed honestly.
    """
    d = df["Date"].sort_values()
    gaps = d.diff().dt.days.dropna()

    business_days = pd.bdate_range(d.min(), d.max())
    observed = set(d.dt.normalize())
    missing_bdays = [x for x in business_days if x not in observed]

    weekday_counts = d.dt.day_name().value_counts().to_dict()

    long_gaps = (
        pd.DataFrame({"end": d.iloc[1:].values, "gap_days": gaps.values})
        .nlargest(10, "gap_days")
        .assign(end=lambda t: pd.to_datetime(t["end"]).dt.strftime("%Y-%m-%d"))
        .to_dict("records")
    )

    return {
        "n_sessions": int(len(d)),
        "n_business_days_in_span": int(len(business_days)),
        "n_business_days_without_a_session": int(len(missing_bdays)),
        "pct_business_days_covered": round(100 * len(d) / len(business_days), 2),
        "gap_days_distribution": {str(int(k)): int(v) for k, v in gaps.value_counts().sort_index().items()},
        "largest_gaps": long_gaps,
        "sessions_per_weekday": {str(k): int(v) for k, v in weekday_counts.items()},
        "n_weekend_sessions": int((d.dt.dayofweek >= 5).sum()),
    }


# Windows in which a multi-day closure of HOSE is expected.  Vietnamese public
# holidays are partly lunar, so the windows are deliberately generous: their
# purpose is to separate "almost certainly a holiday" from "needs explaining",
# not to reproduce the official holiday calendar.
_HOLIDAY_WINDOWS = {
    "New Year": ((12, 28), (1, 5)),
    "Tet (lunar new year)": ((1, 18), (2, 25)),
    "Hung Kings": ((4, 5), (4, 20)),
    "Reunification Day / Labour Day": ((4, 26), (5, 6)),
    "National Day": ((8, 28), (9, 6)),
}

# The longest plausible HOSE closure is the Tet break.  Anything longer than
# this many consecutive missing business days cannot be a holiday.
_MAX_PLAUSIBLE_HOLIDAY_BDAYS = 8


def _in_window(ts: pd.Timestamp, window) -> bool:
    (m1, d1), (m2, d2) = window
    start, end = (m1, d1), (m2, d2)
    cur = (ts.month, ts.day)
    if start <= end:
        return start <= cur <= end
    return cur >= start or cur <= end  # window wraps around new year


def _classify_gap(prev: pd.Timestamp, nxt: pd.Timestamp, missing_bdays: int) -> str:
    if missing_bdays > _MAX_PLAUSIBLE_HOLIDAY_BDAYS:
        return "UNEXPLAINED - too long to be a public holiday"
    for label, window in _HOLIDAY_WINDOWS.items():
        if _in_window(prev, window) or _in_window(nxt, window):
            return f"consistent with {label}"
    return "UNEXPLAINED - outside every known holiday window"


def gap_anomalies(df: pd.DataFrame, min_missing_bdays: int = 2) -> dict:
    """
    Classify every calendar gap that skips `min_missing_bdays` or more business
    days.  Gaps that fall in a known Vietnamese holiday window are expected;
    everything else is reported as UNEXPLAINED so it can be discussed rather
    than silently absorbed into the return series.
    """
    d = df.sort_values("Date").reset_index(drop=True)
    records = []
    for i in range(1, len(d)):
        prev, nxt = d.loc[i - 1, "Date"], d.loc[i, "Date"]
        missing = len(pd.bdate_range(prev + pd.Timedelta(days=1), nxt - pd.Timedelta(days=1)))
        if missing < min_missing_bdays:
            continue
        records.append({
            "prev_session": prev.strftime("%Y-%m-%d"),
            "next_session": nxt.strftime("%Y-%m-%d"),
            "calendar_gap_days": int((nxt - prev).days),
            "missing_business_days": int(missing),
            "classification": _classify_gap(prev, nxt, missing),
        })

    unexplained = [r for r in records if r["classification"].startswith("UNEXPLAINED")]
    return {
        "min_missing_business_days": min_missing_bdays,
        "n_gaps_examined": len(records),
        "n_holiday_consistent": len(records) - len(unexplained),
        "n_unexplained": len(unexplained),
        "unexplained_gaps": unexplained,
        "total_missing_business_days_in_unexplained_gaps": int(
            sum(r["missing_business_days"] for r in unexplained)
        ),
    }


def build_report(df: pd.DataFrame) -> dict:
    return {
        "shape": basic_shape(df),
        "missing": missing_values(df),
        "duplicates": duplicates(df),
        "ordering": ordering(df),
        "impossible_values": impossible_values(df),
        "trading_calendar": trading_calendar(df),
        "gap_anomalies": gap_anomalies(df),
    }


def series_quality(key: str) -> dict:
    """
    Compact quality report for ANY catalogued series, daily or intraday.

    The holiday-gap classifier only makes sense for HOSE-listed equity indices
    on a daily grid, so it is applied there and skipped elsewhere rather than
    producing a verdict it has no basis for. Intraday series are instead
    checked for session completeness: how many trading days carry the full
    complement of bars.
    """
    import catalog
    from preprocessing import load_features

    series = catalog.get(key)
    df = load_features(key)
    price_cols = ["Open", "High", "Low", "Close"]

    rep = {
        "key": key,
        "symbol": series.symbol,
        "timeframe": series.timeframe,
        "family": series.family,
        "role": series.role,
        "n_bars": int(len(df)),
        "n_trading_days": int(df["Date"].nunique()),
        "first": str(df["Timestamp"].min()),
        "last": str(df["Timestamp"].max()),
        "n_duplicate_timestamps": int(df["Timestamp"].duplicated().sum()),
        "monotonic": bool(df["Timestamp"].is_monotonic_increasing),
        "ohlcv_missing_rows": int(df[price_cols].isna().any(axis=1).sum()),
        "non_positive_price": int((df[price_cols] <= 0).any(axis=1).sum()),
        "high_lt_low": int((df["High"] < df["Low"]).sum()),
        "ohlc_inconsistent_bars": int(df["ohlc_inconsistent"].sum()),
        "weekend_bars": int((df["Timestamp"].dt.dayofweek >= 5).sum()),
        "has_volume": bool("Volume" in df.columns),
        "stale_open_share": round(
            float((df["Open"].sub(df["Close"].shift(1)).abs() < 1e-6).mean()), 4),
    }
    if "Volume" in df.columns:
        rep["zero_volume_bars"] = int((df["Volume"] == 0).sum())
        rep["negative_volume_bars"] = int((df["Volume"] < 0).sum())

    if series.is_intraday:
        per_day = df.groupby("Date").size()
        rep["bars_per_day_expected"] = series.bars_per_day
        rep["full_session_days"] = int((per_day == series.bars_per_day).sum())
        rep["partial_session_days"] = int((per_day != series.bars_per_day).sum())
        rep["pct_full_session_days"] = round(
            100 * float((per_day == series.bars_per_day).mean()), 2)
        rep["bars_per_day_distribution"] = {
            str(k): int(v) for k, v in per_day.value_counts().sort_index().items()}
        rep["gap_classification"] = "N/A (intraday)"
    elif catalog.ASSET_CLASS[series.symbol] == "equity index":
        ga = gap_anomalies(df[["Date"]].copy())
        rep["gaps_examined"] = ga["n_gaps_examined"]
        rep["gaps_holiday_consistent"] = ga["n_holiday_consistent"]
        rep["gaps_unexplained"] = ga["n_unexplained"]
        rep["unexplained_gap_details"] = ga["unexplained_gaps"]
        rep["gap_classification"] = "applied (HOSE holiday calendar)"
    else:
        gaps = df["MissingBusinessDaysBefore"].dropna()
        rep["gaps_ge_2_business_days"] = int((gaps >= 2).sum())
        rep["gap_classification"] = (
            "NOT APPLIED - this series does not follow the HOSE holiday "
            "calendar, so classifying its gaps against that calendar would be "
            "meaningless. Gap counts are reported without a verdict.")
    return rep


def all_series_quality() -> dict:
    import catalog
    return {s.key: series_quality(s.key) for s in catalog.SERIES}


def _print_report(rep: dict) -> None:
    def show(title, d, indent=2):
        print(f"\n{title}")
        print("-" * len(title))
        for k, v in d.items():
            if isinstance(v, dict) and len(v) > 12:
                v = dict(list(v.items())[:12])
                print(f"{' ' * indent}{k}: {v} ... (truncated)")
            else:
                print(f"{' ' * indent}{k}: {v}")

    show("1. SHAPE / DTYPES", rep["shape"])
    show("2. MISSING VALUES", rep["missing"])
    show("3. DUPLICATES", rep["duplicates"])
    show("4. CHRONOLOGICAL ORDERING", rep["ordering"])
    show("5. IMPOSSIBLE / SUSPICIOUS VALUES", rep["impossible_values"])
    show("6. TRADING CALENDAR", rep["trading_calendar"])

    ga = rep["gap_anomalies"]
    print("\n7. CALENDAR GAP CLASSIFICATION")
    print("-" * 29)
    print(f"  gaps skipping >= {ga['min_missing_business_days']} business days: {ga['n_gaps_examined']}")
    print(f"  consistent with a public holiday        : {ga['n_holiday_consistent']}")
    print(f"  UNEXPLAINED                             : {ga['n_unexplained']}"
          f"  ({ga['total_missing_business_days_in_unexplained_gaps']} business days of data)")
    for r in ga["unexplained_gaps"]:
        print(f"    {r['prev_session']} -> {r['next_session']}  "
              f"{r['missing_business_days']} business days missing  ({r['classification']})")


if __name__ == "__main__":
    from data_loader import load_raw

    raw = load_raw()
    report = build_report(raw)
    out = config.RESULTS_DIR / "data_quality_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _print_report(report)
    print(f"\nSaved -> {out}")
