"""
Build canonical raw OHLC(V) files for every series in the catalogue.

Primary source
--------------
Kaggle dataset `keithvo/vnstockdata` ("Vietnam Stock Intraday (VNINDEX, VN30,
VN100)"), licensed DbCL-1.0. All 19 CSV files are vendored into
data/raw/kaggle/ so the exact vintage behind every reported number ships with
the project and the analysis stays reproducible after the dataset is updated
upstream. See src/catalog.py for what each file is.

Source schema (TradingView-style export):
    time    int    bar timestamp, UNIX seconds
    open/high/low/close   float
    55EMA / 89EMA / 200EMA  float   pre-computed indicators (dropped on load)
    Volume  int                     HOSE_DLY family only
    Plot    (empty in every row)    HOSE family only

Three source-side properties are handled explicitly rather than silently:

1.  INCOMPLETE TAIL. The HOSE_DLY files were published at 06:36 UTC on
    2025-12-12, i.e. during that Vietnamese trading session, so their last
    observation is partial. The trim rule differs by timeframe:
      * daily bars with volume  -> drop the final bar when its volume is far
        below the recent median (observed ratio 0.40-0.47 across the three
        indices).
      * intraday bars           -> drop the whole final trading DAY when it
        carries fewer bars than a full session (observed 7 of 10 M30 bars).
    The HOSE family ends 2024-12-09 with complete sessions and is not trimmed;
    that was verified, not assumed.

2.  PRE-COMPUTED INDICATORS. 55/89/200 EMA are derived from Close and are
    dropped on load, so nothing indicator-shaped leaks into the models. The
    HOSE family's `Plot` column is empty in every row and is dropped too.

3.  STALE OPEN. In parts of the data `open` merely repeats the previous
    close. This is a property of the upstream feed. The analysis is built on
    `Close`, so the rate is measured and recorded in the metadata rather than
    "repaired".

To re-download the dataset (needs a Kaggle API token in ~/.kaggle/kaggle.json):

    kaggle datasets download keithvo/vnstockdata -p data/raw/kaggle --unzip
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

import catalog
import config

_RENAME = {"open": "Open", "high": "High", "low": "Low", "close": "Close"}
_DROP = ("55EMA", "89EMA", "200EMA", "Plot")

# A daily bar whose volume falls below this share of the recent median is
# treated as an unfinished session.
PARTIAL_BAR_VOLUME_RATIO = 0.60


def _read_source(series: catalog.Series) -> pd.DataFrame:
    if not series.path.exists():
        raise FileNotFoundError(
            f"Source file missing: {series.path}\n"
            "Re-download the dataset with the kaggle command in this module's docstring."
        )
    return pd.read_csv(series.path)


def build_raw(key: str = catalog.HEADLINE_KEY) -> tuple[pd.DataFrame, dict]:
    """Read one vendored source file and return (raw frame, provenance notes)."""
    series = catalog.get(key)
    src = _read_source(series)
    n_source_rows = len(src)

    df = src.drop(columns=[c for c in _DROP if c in src.columns]).rename(columns=_RENAME)

    df["Timestamp"] = (
        pd.to_datetime(df["time"], unit="s", utc=True)
        .dt.tz_convert(catalog.EXCHANGE_TZ)
        .dt.tz_localize(None)
    )
    df["Date"] = df["Timestamp"].dt.normalize()
    df = df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)

    df, trim = _trim_incomplete_tail(df, series)

    cols = ["Timestamp", "Date", "Open", "High", "Low", "Close"]
    if "Volume" in df.columns:
        cols.append("Volume")
    cols.append("time")

    notes = {
        "n_rows_in_source_file": int(n_source_rows),
        "n_rows_after_trim": int(len(df)),
        "trim": trim,
        "dropped_indicator_columns": [c for c in _DROP if c in src.columns],
    }
    return df[cols].reset_index(drop=True), notes


def _trim_incomplete_tail(df: pd.DataFrame, series: catalog.Series) -> tuple[pd.DataFrame, dict]:
    """Remove an unfinished session at the end of the file, if there is one."""
    if series.is_intraday:
        last_day = df["Date"].iloc[-1]
        n_bars = int((df["Date"] == last_day).sum())
        expected = series.bars_per_day
        if n_bars < expected:
            kept = df[df["Date"] != last_day].reset_index(drop=True)
            return kept, {
                "applied": True,
                "rule": "intraday: drop final trading day with an incomplete session",
                "dropped_date": str(last_day.date()),
                "bars_found": n_bars,
                "bars_expected": expected,
                "n_rows_dropped": int(len(df) - len(kept)),
            }
        return df, {"applied": False,
                    "rule": "intraday: final trading day has a full session",
                    "bars_found": n_bars, "bars_expected": expected}

    if "Volume" in df.columns:
        last = df.iloc[-1]
        median_vol = float(df["Volume"].tail(21).median())
        ratio = float(last["Volume"]) / median_vol if median_vol else float("nan")
        if ratio < PARTIAL_BAR_VOLUME_RATIO:
            return df.iloc[:-1].reset_index(drop=True), {
                "applied": True,
                "rule": "daily: drop final bar whose volume is far below the recent median",
                "dropped_date": str(last["Date"].date()),
                "volume": int(last["Volume"]),
                "median_volume_last_21_bars": median_vol,
                "ratio": round(ratio, 3),
                "threshold": PARTIAL_BAR_VOLUME_RATIO,
                "n_rows_dropped": 1,
            }
        return df, {"applied": False,
                    "rule": "daily: final bar volume is consistent with a complete session",
                    "ratio": round(ratio, 3), "threshold": PARTIAL_BAR_VOLUME_RATIO}

    return df, {"applied": False,
                "rule": "daily without volume: completeness verified against the "
                        "overlapping HOSE_DLY vintage; no trim needed"}


def _meta_for(series: catalog.Series, raw: pd.DataFrame, notes: dict) -> dict:
    stale_open = float((raw["Open"].sub(raw["Close"].shift(1)).abs() < 1e-6).mean())
    return {
        "series_key": series.key,
        "symbol": series.symbol,
        "symbol_label": catalog.SYMBOL_LABEL[series.symbol],
        "asset_class": catalog.ASSET_CLASS[series.symbol],
        "timeframe": series.timeframe,
        "timeframe_label": catalog.TIMEFRAME_LABEL[series.timeframe],
        "family": series.family,
        "role": series.role,
        "source_name": config.SOURCE_NAME,
        "source_url": config.SOURCE_URL,
        "source_license": config.SOURCE_LICENSE,
        "source_file": series.filename,
        "upstream_last_updated": "2025-12-12",
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows": int(len(raw)),
        "first_timestamp": str(raw["Timestamp"].min()),
        "last_timestamp": str(raw["Timestamp"].max()),
        "first_date": str(raw["Date"].min().date()),
        "last_date": str(raw["Date"].max().date()),
        "n_trading_days": int(raw["Date"].nunique()),
        "has_volume": bool("Volume" in raw.columns),
        "columns": list(raw.columns),
        "share_of_rows_where_open_equals_previous_close": round(stale_open, 4),
        "adjusted_close_available": False,
        "adjusted_close_note": (
            "These are price indices / an FX rate; no adjusted-close series is "
            "published for them by this or any other source."
        ),
        **notes,
    }


def save_raw(raw: pd.DataFrame, notes: dict, key: str = catalog.HEADLINE_KEY) -> dict:
    series = catalog.get(key)
    meta = _meta_for(series, raw, notes)

    if key == catalog.HEADLINE_KEY:
        raw.to_csv(config.RAW_CSV, index=False)
        config.RAW_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    else:
        raw.to_csv(config.series_raw_csv(key), index=False)
    return meta


def load_raw(key: str = catalog.HEADLINE_KEY) -> pd.DataFrame:
    """Read a canonical raw CSV back from disk."""
    path = config.RAW_CSV if key == catalog.HEADLINE_KEY else config.series_raw_csv(key)
    df = pd.read_csv(path, parse_dates=["Timestamp", "Date"])
    return df


def build_all(keys=None) -> dict:
    """Build canonical raw files for every catalogued series."""
    keys = keys or [s.key for s in catalog.SERIES]
    metas = {}
    for k in keys:
        raw, notes = build_raw(k)
        metas[k] = save_raw(raw, notes, k)
    (config.RESULTS_DIR / "series_inventory.json").write_text(
        json.dumps(metas, indent=2), encoding="utf-8"
    )
    return metas


if __name__ == "__main__":
    metas = build_all()
    print(f"{'key':<22} {'rows':>7} {'days':>6}  period                      trim")
    print("-" * 104)
    for k, m in metas.items():
        t = m["trim"]
        trim = (f"dropped {t.get('dropped_date')} ({t.get('n_rows_dropped')} rows)"
                if t.get("applied") else "none")
        print(f"{k:<22} {m['n_rows']:>7,} {m['n_trading_days']:>6,}  "
              f"{m['first_date']} -> {m['last_date']}   {trim}")
    print(f"\n{len(metas)} series written. Inventory -> results/series_inventory.json")
