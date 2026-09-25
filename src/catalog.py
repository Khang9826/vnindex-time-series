"""
Catalogue of every series in the Kaggle dataset `keithvo/vnstockdata`.

The dataset ships 19 CSV files in TWO families that differ in schema and in
how far they run:

  Family "HOSE"      time,open,high,low,close,55EMA,89EMA,200EMA,Plot
                     No volume. `Plot` is empty in every row. Ends 2024-12-09.
                     Timeframes: 1D, H1, H4, M30.

  Family "HOSE_DLY"  time,open,high,low,close,55EMA,89EMA,200EMA,Volume
                     Has volume. Ends 2025-12-12. Timeframes: 1D and M30 only.

Because neither family covers everything, the project picks a PRIMARY file per
(symbol, timeframe) and keeps the other family, where it overlaps, as an
independent cross-check vintage:

  * HOSE_DLY is primary wherever it exists (1D and M30 for the three indices):
    it carries volume and runs a year further.
  * HOSE is primary for H1 and H4, which HOSE_DLY does not publish at all,
    and for USD/VND, which only HOSE publishes.

Trading calendar (verified from the bar timestamps, not assumed):
HOSE runs a morning session 09:00-11:30 and an afternoon session 13:00-14:45,
Asia/Ho_Chi_Minh. So a full day has 10 M30 bars, 5 H1 bars and 2 H4 bars. Note
that the last bar of each session is a stub - the 11:30 M30 bar covers only
15 minutes and the 11:00 H1 bar only 30 - and that "H4" is really one bar per
half-day session rather than a four-hour clock bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import config

# --------------------------------------------------------------------------
# Trading session structure (verified against the data in notebooks/inventory)
# --------------------------------------------------------------------------
EXCHANGE_TZ = "Asia/Ho_Chi_Minh"

BARS_PER_DAY = {"1D": 1, "H4": 2, "H1": 5, "M30": 10}

# Bar open times observed for each intraday timeframe.
SESSION_BAR_TIMES = {
    "M30": ["09:00", "09:30", "10:00", "10:30", "11:00",
            "11:30", "13:00", "13:30", "14:00", "14:30"],
    "H1": ["09:00", "10:00", "11:00", "13:00", "14:00"],
    "H4": ["09:00", "13:00"],
}

TIMEFRAME_LABEL = {
    "1D": "Daily",
    "H4": "Half-day session (4H)",
    "H1": "Hourly",
    "M30": "30 minutes",
}

SYMBOL_LABEL = {
    "VNINDEX": "VN-Index (HOSE composite)",
    "VN30": "VN30 (30 large-cap HOSE stocks)",
    "VN100": "VN100 (VN30 + VNMidcap)",
    "USDVND": "USD/VND exchange rate",
}

ASSET_CLASS = {
    "VNINDEX": "equity index",
    "VN30": "equity index",
    "VN100": "equity index",
    "USDVND": "foreign exchange",
}


@dataclass(frozen=True)
class Series:
    key: str            # stable identifier, e.g. "VNINDEX_1D"
    symbol: str
    timeframe: str
    family: str         # "HOSE_DLY" or "HOSE"
    filename: str
    has_volume: bool
    role: str           # "primary" or "crosscheck"
    crosscheck_of: str | None = None

    @property
    def path(self):
        return config.KAGGLE_DIR / self.filename

    @property
    def label(self) -> str:
        return f"{self.symbol} {self.timeframe}"

    @property
    def is_intraday(self) -> bool:
        return self.timeframe != "1D"

    @property
    def bars_per_day(self) -> int:
        return BARS_PER_DAY[self.timeframe]


def _s(symbol, timeframe, family, filename, role, crosscheck_of=None) -> Series:
    return Series(
        key=f"{symbol}_{timeframe}" if role == "primary"
            else f"{symbol}_{timeframe}__{family}",
        symbol=symbol, timeframe=timeframe, family=family, filename=filename,
        has_volume=(family == "HOSE_DLY"), role=role, crosscheck_of=crosscheck_of,
    )


# --------------------------------------------------------------------------
# The registry. Every file in the dataset appears exactly once.
# --------------------------------------------------------------------------
SERIES: list[Series] = [
    # ---- PRIMARY: HOSE_DLY (has volume, runs to 2025-12-12) ----
    _s("VNINDEX", "1D",  "HOSE_DLY", "HOSE_DLY_VNINDEX1D.csv", "primary"),
    _s("VN30",    "1D",  "HOSE_DLY", "HOSE_DLY_VN301D.csv",    "primary"),
    _s("VN100",   "1D",  "HOSE_DLY", "HOSE_DLY_VN1001D.csv",   "primary"),
    _s("VNINDEX", "M30", "HOSE_DLY", "HOSE_DLY_VNINDEX30.csv", "primary"),
    _s("VN30",    "M30", "HOSE_DLY", "HOSE_DLY_VN3030.csv",    "primary"),
    _s("VN100",   "M30", "HOSE_DLY", "HOSE_DLY_VN10030.csv",   "primary"),

    # ---- PRIMARY: HOSE (only source for H1, H4 and USD/VND) ----
    _s("VNINDEX", "H1", "HOSE", "HOSEVNINDEXH1.csv", "primary"),
    _s("VN30",    "H1", "HOSE", "HOSEVN30H1.csv",    "primary"),
    _s("VN100",   "H1", "HOSE", "HOSEVN100H1.csv",   "primary"),
    _s("VNINDEX", "H4", "HOSE", "HOSEVNINDEXH4.csv", "primary"),
    _s("VN30",    "H4", "HOSE", "HOSEVN30H4.csv",    "primary"),
    _s("VN100",   "H4", "HOSE", "HOSEVN100H4.csv",   "primary"),
    _s("USDVND",  "1D", "HOSE", "USDVND1D.csv",      "primary"),

    # ---- CROSS-CHECK: HOSE duplicates of series HOSE_DLY also covers ----
    _s("VNINDEX", "1D",  "HOSE", "HOSEVNINDEX1D.csv",  "crosscheck", "VNINDEX_1D"),
    _s("VN30",    "1D",  "HOSE", "HOSEVN301D.csv",     "crosscheck", "VN30_1D"),
    _s("VN100",   "1D",  "HOSE", "HOSEVN1001D.csv",    "crosscheck", "VN100_1D"),
    _s("VNINDEX", "M30", "HOSE", "HOSEVNINDEXM30.csv", "crosscheck", "VNINDEX_M30"),
    _s("VN30",    "M30", "HOSE", "HOSEVN30M30.csv",    "crosscheck", "VN30_M30"),
    _s("VN100",   "M30", "HOSE", "HOSEVN100M30.csv",   "crosscheck", "VN100_M30"),
]

BY_KEY = {s.key: s for s in SERIES}

PRIMARY = [s for s in SERIES if s.role == "primary"]
CROSSCHECK = [s for s in SERIES if s.role == "crosscheck"]

# The headline series of the project - the one the deep-dive chapters analyse.
HEADLINE_KEY = "VNINDEX_1D"


def get(key: str) -> Series:
    if key not in BY_KEY:
        raise KeyError(f"unknown series '{key}'. Known: {sorted(BY_KEY)}")
    return BY_KEY[key]


def primary_keys(symbols=None, timeframes=None) -> list[str]:
    out = []
    for s in PRIMARY:
        if symbols and s.symbol not in symbols:
            continue
        if timeframes and s.timeframe not in timeframes:
            continue
        out.append(s.key)
    return out


def equity_index_keys(timeframe: str | None = None) -> list[str]:
    return [s.key for s in PRIMARY
            if ASSET_CLASS[s.symbol] == "equity index"
            and (timeframe is None or s.timeframe == timeframe)]


def describe() -> str:
    lines = [f"{'key':<22} {'symbol':<8} {'tf':<4} {'family':<9} {'vol':<4} {'role':<11} file"]
    lines.append("-" * 100)
    for s in SERIES:
        lines.append(
            f"{s.key:<22} {s.symbol:<8} {s.timeframe:<4} {s.family:<9} "
            f"{'yes' if s.has_volume else 'no':<4} {s.role:<11} {s.filename}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
    print()
    print(f"{len(SERIES)} files total: {len(PRIMARY)} primary, {len(CROSSCHECK)} cross-check")
    missing = [s.filename for s in SERIES if not s.path.exists()]
    print("missing files:", missing or "none")
