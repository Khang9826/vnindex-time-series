"""
Central configuration for the VN-Index time-series project.

All paths are resolved relative to the project root so that every script /
notebook can be executed from any working directory and still write to the
same place.
"""
from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FIGURES_DIR = PROJECT_ROOT / "figures"
RESULTS_DIR = PROJECT_ROOT / "results"
REPORTS_DIR = PROJECT_ROOT / "reports"

for _d in (RAW_DIR, PROCESSED_DIR, FIGURES_DIR, RESULTS_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Primary source: the Kaggle dataset the user supplied (vendored into data/raw).
KAGGLE_CSV = RAW_DIR / "kaggle_HOSE_DLY_VNINDEX1D.csv"

# Canonical raw / processed artefacts consumed by every downstream stage.
RAW_CSV = RAW_DIR / "vnindex_raw.csv"          # built from KAGGLE_CSV by data_loader
RAW_META = RAW_DIR / "vnindex_raw_meta.json"
CLEAN_CSV = PROCESSED_DIR / "vnindex_clean.csv"
FEATURES_CSV = PROCESSED_DIR / "vnindex_features.csv"

# --------------------------------------------------------------------------
# Data source
# --------------------------------------------------------------------------
# PRIMARY - user-supplied Kaggle dataset.
SOURCE_NAME = "Kaggle: keithvo/vnstockdata (Vietnam Stock Intraday), file HOSE_DLY_VNINDEX1D.csv"
SOURCE_URL = "https://www.kaggle.com/datasets/keithvo/vnstockdata"
SOURCE_LICENSE = "Database Contents License (DbCL) v1.0"
SYMBOL = "VNINDEX"
RESOLUTION = "1D"

# SECONDARY / cross-check only - DNSE Entrade public chart API. Used by
# data_crosscheck.py to independently corroborate the Kaggle series; never the
# source of the reported numbers.
CROSSCHECK_NAME = "DNSE Entrade public chart API"
CROSSCHECK_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs/index"
HISTORY_START = "2000-01-01"

# The Kaggle file ships pre-computed indicator columns (55/89/200 EMA). They are
# derived from Close and are dropped on load: recomputing anything we need keeps
# the pipeline self-contained and avoids importing look-ahead-shaped features.
DROP_SOURCE_COLUMNS = ("55EMA", "89EMA", "200EMA", "Plot")

# --------------------------------------------------------------------------
# Analysis settings
# --------------------------------------------------------------------------
RANDOM_SEED = 42
ALPHA = 0.05                 # significance level used throughout
TRADING_DAYS_PER_YEAR = 252  # annualisation factor for volatility

# Chronological split fractions (train / validation / test).
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
# test fraction is the remainder (0.15)

# Rolling windows used in the volatility analysis (trading days).
ROLLING_WINDOWS = (21, 63, 252)

# Maximum lag used for ACF/PACF plots and Ljung-Box tests.
MAX_LAG = 40
