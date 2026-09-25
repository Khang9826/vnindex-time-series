"""
Build the canonical raw VN-Index daily OHLCV file from the primary source.

Primary source
--------------
Kaggle dataset `keithvo/vnstockdata` ("Vietnam Stock Intraday (VNINDEX, VN30,
VN100)"), file `HOSE_DLY_VNINDEX1D.csv`, licensed DbCL-1.0.  The file is
vendored into data/raw/ so the exact vintage used for every reported number is
stored with the project and the analysis stays reproducible after the dataset
is updated upstream.

Its schema is a TradingView-style export:
    time    int    bar timestamp, UNIX seconds
    open/high/low/close   float
    55EMA / 89EMA / 200EMA  float   pre-computed indicators (dropped on load)
    Volume  int

Two source-side properties are handled explicitly here rather than silently:

1.  The final bar of the file is an INCOMPLETE session.  The dataset was
    published 2025-12-12 06:36 UTC, i.e. during the 2025-12-12 Vietnamese
    trading session, so that bar records a partial day: its volume is roughly
    half of its neighbours' and its close is the single largest disagreement
    with the independent cross-check source in the whole sample.  It is
    dropped, and the drop is recorded in the metadata.

2.  `open` is frequently a carry-over of the previous session's close rather
    than the true opening print.  This is a property of the upstream feed.
    The analysis is built on `Close`, so it is documented and flagged, not
    repaired.

To re-download the file (needs a Kaggle API token in ~/.kaggle/kaggle.json):

    kaggle datasets download keithvo/vnstockdata \
        -f HOSE_DLY_VNINDEX1D.csv -p data/raw --unzip
    mv data/raw/HOSE_DLY_VNINDEX1D.csv data/raw/kaggle_HOSE_DLY_VNINDEX1D.csv
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

import config

_RENAME = {"open": "Open", "high": "High", "low": "Low", "close": "Close"}


def _read_source() -> pd.DataFrame:
    if not config.KAGGLE_CSV.exists():
        raise FileNotFoundError(
            f"Primary source file missing: {config.KAGGLE_CSV}\n"
            "Re-download it with the kaggle command in this module's docstring."
        )
    return pd.read_csv(config.KAGGLE_CSV)


def build_raw() -> tuple[pd.DataFrame, dict]:
    """Read the vendored source file and return (raw frame, provenance notes)."""
    src = _read_source()
    n_source_rows = len(src)

    df = src.drop(columns=[c for c in config.DROP_SOURCE_COLUMNS if c in src.columns])
    df = df.rename(columns=_RENAME)

    # Bar timestamps are UNIX seconds; convert to the exchange calendar date.
    df["Date"] = (
        pd.to_datetime(df["time"], unit="s", utc=True)
        .dt.tz_convert("Asia/Ho_Chi_Minh")
        .dt.normalize()
        .dt.tz_localize(None)
    )
    df = df.sort_values("Date", kind="mergesort").reset_index(drop=True)

    # --- drop the incomplete final session (see module docstring) ----------
    last = df.iloc[-1]
    median_vol = df["Volume"].tail(21).median()
    dropped = {
        "date": str(last["Date"].date()),
        "close": float(last["Close"]),
        "volume": int(last["Volume"]),
        "median_volume_last_21_sessions": float(median_vol),
        "reason": (
            "Dataset published during this trading session; the bar is partial "
            "(volume far below the recent median) and is the largest single "
            "disagreement with the independent cross-check source."
        ),
    }
    df = df.iloc[:-1].reset_index(drop=True)

    notes = {
        "n_rows_in_source_file": int(n_source_rows),
        "n_rows_after_dropping_partial_bar": int(len(df)),
        "dropped_final_partial_bar": dropped,
        "dropped_indicator_columns": [
            c for c in config.DROP_SOURCE_COLUMNS if c in src.columns
        ],
    }
    return df[["Date", "Open", "High", "Low", "Close", "Volume", "time"]], notes


def save_raw(raw: pd.DataFrame, notes: dict) -> None:
    raw.to_csv(config.RAW_CSV, index=False)

    stale_open = float(
        (raw["Open"].sub(raw["Close"].shift(1)).abs() < 1e-6).mean()
    )

    meta = {
        "source_name": config.SOURCE_NAME,
        "source_url": config.SOURCE_URL,
        "source_license": config.SOURCE_LICENSE,
        "source_file_vendored_at": str(config.KAGGLE_CSV.relative_to(config.PROJECT_ROOT)),
        "upstream_last_updated": "2025-12-12",
        "symbol": config.SYMBOL,
        "resolution": config.RESOLUTION,
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows": int(len(raw)),
        "first_date": str(raw["Date"].min().date()),
        "last_date": str(raw["Date"].max().date()),
        "columns": list(raw.columns),
        "share_of_rows_where_open_equals_previous_close": round(stale_open, 4),
        "adjusted_close_available": False,
        "adjusted_close_note": (
            "VN-Index is a price index; no adjusted-close series is published "
            "for it by this or any other source."
        ),
        **notes,
    }
    config.RAW_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_raw() -> pd.DataFrame:
    """Read the canonical raw CSV back from disk."""
    return pd.read_csv(config.RAW_CSV, parse_dates=["Date"])


if __name__ == "__main__":
    raw, notes = build_raw()
    save_raw(raw, notes)
    d = notes["dropped_final_partial_bar"]
    print(f"Source file rows      : {notes['n_rows_in_source_file']:,}")
    print(f"Dropped partial bar   : {d['date']} "
          f"(volume {d['volume']:,} vs 21-session median {d['median_volume_last_21_sessions']:,.0f})")
    print(f"Canonical raw rows    : {len(raw):,}")
    print(f"Period                : {raw['Date'].min().date()} -> {raw['Date'].max().date()}")
    print(f"Written               : {config.RAW_CSV.name}, {config.RAW_META.name}")
