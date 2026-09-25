"""
Tests for the multi-series layer: the catalogue, per-series ingestion, the
intraday session bookkeeping and the comparative battery.

    python -m pytest tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import catalog  # noqa: E402
import config  # noqa: E402
from preprocessing import load_features  # noqa: E402

ALL_KEYS = [s.key for s in catalog.SERIES]
PRIMARY_KEYS = catalog.primary_keys()
INTRADAY_KEYS = [s.key for s in catalog.SERIES if s.is_intraday]
DAILY_KEYS = [s.key for s in catalog.SERIES if not s.is_intraday]


def _features(key):
    path = (config.FEATURES_CSV if key == catalog.HEADLINE_KEY
            else config.series_features_csv(key))
    if not path.exists():
        pytest.skip(f"{key} not built yet - run src/run_all.py first")
    return load_features(key)


# --- catalogue integrity ---------------------------------------------------
def test_catalogue_covers_every_vendored_file():
    """No file in the dataset may be silently ignored."""
    on_disk = {p.name for p in config.KAGGLE_DIR.glob("*.csv")}
    catalogued = {s.filename for s in catalog.SERIES}
    assert on_disk == catalogued, (
        f"only in dataset: {sorted(on_disk - catalogued)}; "
        f"only in catalogue: {sorted(catalogued - on_disk)}"
    )


def test_catalogue_keys_are_unique():
    keys = [s.key for s in catalog.SERIES]
    assert len(keys) == len(set(keys))


def test_every_crosscheck_points_at_a_real_primary():
    for s in catalog.CROSSCHECK:
        assert s.crosscheck_of in catalog.BY_KEY
        target = catalog.get(s.crosscheck_of)
        assert target.role == "primary"
        assert target.symbol == s.symbol and target.timeframe == s.timeframe


def test_only_hose_dly_family_claims_volume():
    for s in catalog.SERIES:
        assert s.has_volume == (s.family == "HOSE_DLY")


# --- per-series data integrity --------------------------------------------
@pytest.mark.parametrize("key", ALL_KEYS)
def test_series_is_ordered_and_unique(key):
    df = _features(key)
    assert df["Timestamp"].is_monotonic_increasing
    assert df["Timestamp"].is_unique


@pytest.mark.parametrize("key", ALL_KEYS)
def test_series_prices_are_positive_and_consistent(key):
    df = _features(key)
    cols = ["Open", "High", "Low", "Close"]
    assert (df[cols] > 0).all().all()
    assert (df["High"] >= df["Low"]).all()
    assert df[cols].notna().all().all()


@pytest.mark.parametrize("key", ALL_KEYS)
def test_log_return_definition_holds(key):
    df = _features(key)
    expected = np.log(df["Close"] / df["Close"].shift(1))
    pd.testing.assert_series_equal(
        df["LogReturn"], expected, check_names=False, rtol=1e-12)


@pytest.mark.parametrize("key", ALL_KEYS)
def test_first_return_is_nan_and_never_filled(key):
    df = _features(key)
    assert pd.isna(df.loc[0, "LogReturn"])
    assert df["LogReturn"].isna().sum() == 1


@pytest.mark.parametrize("key", ALL_KEYS)
def test_no_weekend_bars(key):
    df = _features(key)
    assert (df["Timestamp"].dt.dayofweek < 5).all()


# --- intraday session bookkeeping -----------------------------------------
@pytest.mark.parametrize("key", INTRADAY_KEYS)
def test_intraday_bar_times_match_the_known_session(key):
    series = catalog.get(key)
    df = _features(key)
    allowed = set(catalog.SESSION_BAR_TIMES[series.timeframe])
    assert set(df["BarTime"].unique()) <= allowed


@pytest.mark.parametrize("key", INTRADAY_KEYS)
def test_intraday_never_exceeds_a_full_session(key):
    """A day may be short (halt, early data) but never longer than the session."""
    series = catalog.get(key)
    df = _features(key)
    assert df.groupby("Date").size().max() <= series.bars_per_day


@pytest.mark.parametrize("key", INTRADAY_KEYS)
def test_overnight_flag_marks_exactly_the_first_bar_of_each_day(key):
    df = _features(key)
    first_of_day = df["Date"].ne(df["Date"].shift(1))
    first_of_day.iloc[0] = False  # the very first row has no predecessor
    pd.testing.assert_series_equal(
        df["SpansOvernight"], first_of_day, check_names=False)


@pytest.mark.parametrize("key", INTRADAY_KEYS)
def test_break_spanning_bars_are_excluded_from_regular_bars(key):
    series = catalog.get(key)
    df = _features(key)
    if series.timeframe == "H4":
        # Every H4 bar spans a break, so the distinction collapses by design.
        assert df["IsRegularBar"].equals(df["LogReturn"].notna())
        return
    overlap = df["IsRegularBar"] & (df["SpansOvernight"] | df["SpansLunchBreak"])
    assert not overlap.any()
    assert df["IsRegularBar"].sum() > 0


def test_trimmed_tail_left_only_full_sessions():
    """The incomplete final day must be gone from every intraday series."""
    for key in INTRADAY_KEYS:
        series = catalog.get(key)
        df = _features(key)
        last_day = df["Date"].max()
        n = int((df["Date"] == last_day).sum())
        assert n == series.bars_per_day, (
            f"{key}: final day {last_day.date()} has {n} bars, "
            f"expected {series.bars_per_day}"
        )


# --- daily gap bookkeeping -------------------------------------------------
@pytest.mark.parametrize("key", DAILY_KEYS)
def test_gap_classification_is_scoped_to_hose_equities(key):
    """
    The holiday classifier encodes the HOSE calendar. It must not be applied
    to USD/VND, which trades on a different one.
    """
    series = catalog.get(key)
    df = _features(key)
    is_equity = catalog.ASSET_CLASS[series.symbol] == "equity index"
    assert bool(df["GapClassified"].iloc[0]) is is_equity
    if not is_equity:
        assert not df["SpansUnexplainedGap"].any()


# --- comparative battery ---------------------------------------------------
def test_battery_results_cover_every_primary_series():
    import json
    path = config.RESULTS_DIR / "multiseries_battery.json"
    if not path.exists():
        pytest.skip("battery not run yet - run src/run_all.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert {r["key"] for r in payload["series"]} == set(PRIMARY_KEYS)


def test_matched_period_uses_identical_sample_sizes():
    """
    The whole point of the matched-period control is that every symbol is
    measured on the same observations.
    """
    import json
    path = config.RESULTS_DIR / "multiseries_battery.json"
    if not path.exists():
        pytest.skip("battery not run yet - run src/run_all.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for tf, m in payload["matched_period_comparison"].items():
        if not m.get("n_common"):
            continue
        sizes = {s: v["n"] for s, v in m["stats"].items()}
        assert len(set(sizes.values())) == 1, f"{tf}: unequal samples {sizes}"
        assert set(sizes.values()) == {m["n_common"]}
