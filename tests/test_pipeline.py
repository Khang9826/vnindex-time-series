"""
Tests for the data pipeline.

They run against the artefacts actually produced by src/run_all.py, so a green
run is evidence that the numbers quoted in the report come from a consistent
dataset - not just that the functions compile.

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

import config  # noqa: E402
import preprocessing  # noqa: E402
from data_loader import load_raw  # noqa: E402


@pytest.fixture(scope="module")
def raw() -> pd.DataFrame:
    if not config.RAW_CSV.exists():
        pytest.skip("raw data not downloaded yet - run src/data_loader.py first")
    return load_raw()


@pytest.fixture(scope="module")
def feat() -> pd.DataFrame:
    if not config.FEATURES_CSV.exists():
        pytest.skip("feature table not built yet - run src/preprocessing.py first")
    return preprocessing.load_features()


# --- raw data integrity ---------------------------------------------------
def test_raw_has_expected_columns(raw):
    for col in ("Date", "Open", "High", "Low", "Close", "Volume"):
        assert col in raw.columns


def test_raw_dates_unique_and_sorted(raw):
    assert raw["Date"].is_unique
    assert raw["Date"].is_monotonic_increasing


def test_raw_prices_are_positive(raw):
    assert (raw[["Open", "High", "Low", "Close"]] > 0).all().all()


def test_no_weekend_sessions(raw):
    assert (raw["Date"].dt.dayofweek < 5).all()


# --- preprocessing correctness -------------------------------------------
def test_clean_preserves_every_session(raw, feat):
    """Cleaning must not silently drop observations."""
    assert len(feat) == len(raw)


def test_simple_return_definition(feat):
    p = feat["Close"]
    expected = (p - p.shift(1)) / p.shift(1)
    pd.testing.assert_series_equal(
        feat["SimpleReturn"], expected, check_names=False, rtol=1e-12
    )


def test_log_return_definition(feat):
    p = feat["Close"]
    expected = np.log(p / p.shift(1))
    pd.testing.assert_series_equal(
        feat["LogReturn"], expected, check_names=False, rtol=1e-12
    )


def test_log_and_simple_return_are_consistent(feat):
    """r = ln(1 + R) must hold for every observation."""
    d = feat.dropna(subset=["LogReturn", "SimpleReturn"])
    assert np.allclose(d["LogReturn"], np.log1p(d["SimpleReturn"]), atol=1e-12)


def test_first_return_is_nan_and_never_filled(feat):
    assert pd.isna(feat.loc[0, "LogReturn"])
    assert feat["LogReturn"].isna().sum() == 1


def test_returns_use_only_past_information(feat):
    """
    Guard against look-ahead: the return at row i must be reconstructable from
    rows i-1 and i alone. Checked on a deterministic random sample.
    """
    rng = np.random.default_rng(config.RANDOM_SEED)
    idx = rng.choice(np.arange(1, len(feat)), size=200, replace=False)
    for i in idx:
        expected = np.log(feat.loc[i, "Close"] / feat.loc[i - 1, "Close"])
        assert feat.loc[i, "LogReturn"] == pytest.approx(expected, rel=1e-12)


def test_change_column_matches_close_diff(feat):
    d = feat.dropna(subset=["Change"])
    assert np.allclose(d["Change"], feat["Close"].diff().dropna(), atol=1e-9)


# --- calendar features ----------------------------------------------------
def test_calendar_features_match_the_date(feat):
    assert (feat["Year"] == feat["Date"].dt.year).all()
    assert (feat["Month"] == feat["Date"].dt.month).all()
    assert (feat["Weekday"] == feat["Date"].dt.day_name()).all()


def test_ohlc_flag_is_boolean_and_rare(feat):
    flags = feat["ohlc_inconsistent"].astype(bool)
    # the flagged rows are kept; they must stay a small minority of the sample
    assert flags.mean() < 0.01


# --- chronological split --------------------------------------------------
def test_split_fractions_are_valid():
    assert 0 < config.TRAIN_FRAC < 1
    assert 0 < config.VAL_FRAC < 1
    assert config.TRAIN_FRAC + config.VAL_FRAC < 1


# --- primary-source ingestion --------------------------------------------
@pytest.fixture(scope="module")
def meta() -> dict:
    import json
    if not config.RAW_META.exists():
        pytest.skip("raw metadata not built yet - run src/data_loader.py first")
    return json.loads(config.RAW_META.read_text(encoding="utf-8"))


def test_vendored_source_file_is_present():
    """The analysis must not depend on a live network fetch."""
    assert config.KAGGLE_CSV.exists(), (
        "the primary source file is vendored into data/raw/ on purpose - "
        "without it the reported numbers are not reproducible"
    )


def test_partial_final_bar_was_dropped(meta, raw):
    assert meta["n_rows_after_dropping_partial_bar"] == meta["n_rows_in_source_file"] - 1
    dropped_date = pd.Timestamp(meta["dropped_final_partial_bar"]["date"])
    assert dropped_date not in set(raw["Date"])
    # the drop must be justified by the volume anomaly that motivated it
    d = meta["dropped_final_partial_bar"]
    assert d["volume"] < 0.6 * d["median_volume_last_21_sessions"]


def test_indicator_columns_are_not_carried_into_the_analysis(raw, feat):
    """Pre-computed EMAs from the source file must never reach the models."""
    for frame in (raw, feat):
        for col in config.DROP_SOURCE_COLUMNS:
            assert col not in frame.columns


def test_provenance_metadata_is_complete(meta):
    for key in ("source_name", "source_url", "source_license",
                "n_rows", "first_date", "last_date"):
        assert meta.get(key), f"missing provenance field: {key}"


def test_raw_ohlc_bars_are_internally_consistent(raw):
    """The primary source has no Open/Close outside [Low, High]."""
    assert (raw["High"] >= raw["Low"]).all()
    assert ((raw["Close"] <= raw["High"]) & (raw["Close"] >= raw["Low"])).all()
    assert ((raw["Open"] <= raw["High"]) & (raw["Open"] >= raw["Low"])).all()
