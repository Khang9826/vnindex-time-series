"""
Run the core statistical battery across EVERY series in the catalogue.

The headline deep-dive (analysis.py, stationarity.py, autocorrelation.py) stays
focused on VN-Index daily. This module answers the comparative questions the
rest of the dataset makes possible:

    * Do the VN-Index findings hold for VN30 and VN100, i.e. across market
      segments, or are they specific to the broad index?
    * How do the same properties change with sampling frequency
      (30-minute -> hourly -> half-day -> daily)?
    * Does an FX series from the same region behave like the equity indices?

For intraday series the battery is computed on REGULAR bars only - returns
measured over the timeframe's ordinary interval - because a bar spanning the
overnight gap or the lunch break covers a different amount of real time and is
not a comparable observation. The exception is H4, where every bar is a session
bar; see preprocessing._add_intraday_flags.

Nothing here is a forecast. This is descriptive and inferential statistics on
data that has actually been loaded.
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import acf, adfuller, kpss

import analysis
import catalog
import config
from preprocessing import load_features


def return_sample(key: str) -> pd.Series:
    """Log returns in percent, restricted to comparable (regular) bars."""
    df = load_features(key)
    s = df.loc[df["IsRegularBar"], "LogReturn_pct"]
    return s.dropna().astype(float)


# --------------------------------------------------------------------------
def _adf(x: np.ndarray, regression: str = "c") -> dict:
    try:
        stat, p, lags, nobs, crit, _ = adfuller(
            x, regression=regression, autolag="AIC", result_object=False)
    except TypeError:
        stat, p, lags, nobs, crit, _ = adfuller(x, regression=regression, autolag="AIC")
    return {"stat": float(stat), "p": float(p), "lags": int(lags),
            "crit_5pct": float(crit["5%"]), "reject_H0": bool(p < config.ALPHA)}


def _kpss(x: np.ndarray, regression: str = "c") -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        stat, p, lags, crit = kpss(x, regression=regression, nlags="auto")
    return {"stat": float(stat), "p": float(p), "lags": int(lags),
            "crit_5pct": float(crit["5%"]), "reject_H0": bool(p < config.ALPHA)}


def _verdict(a: dict, k: dict) -> str:
    if a["reject_H0"] and not k["reject_H0"]:
        return "STATIONARY"
    if not a["reject_H0"] and k["reject_H0"]:
        return "NON-STATIONARY"
    return "AMBIGUOUS"


def battery(key: str) -> dict:
    """Descriptives + normality + stationarity + autocorrelation for one series."""
    series = catalog.get(key)
    df = load_features(key)
    r = return_sample(key)
    x = r.to_numpy()
    close = df["Close"].dropna().astype(float)

    # --- stationarity: price level and returns -------------------------
    lvl_adf, lvl_kpss = _adf(close.to_numpy(), "c"), _kpss(close.to_numpy(), "c")
    ret_adf, ret_kpss = _adf(x, "c"), _kpss(x, "c")

    # --- normality -----------------------------------------------------
    jb_stat, jb_p = stats.jarque_bera(x)
    rng = np.random.default_rng(config.RANDOM_SEED)
    sub = x if x.size <= 5000 else rng.choice(x, size=5000, replace=False)
    sw_stat, sw_p = stats.shapiro(sub)

    # --- tails ----------------------------------------------------------
    mu, sd = x.mean(), x.std(ddof=1)
    z = np.abs((x - mu) / sd)
    tails = {}
    for kk in (3, 4):
        obs = int((z > kk).sum())
        exp = float(2 * stats.norm.sf(kk) * x.size)
        tails[f"gt_{kk}_sigma"] = {
            "observed": obs, "expected_if_normal": round(exp, 2),
            "ratio": round(obs / exp, 2) if exp > 0 else None,
        }

    # --- autocorrelation -------------------------------------------------
    nlags = min(config.MAX_LAG, max(10, x.size // 10))
    a_r = acf(x, nlags=nlags, fft=True)
    a_abs = acf(np.abs(x), nlags=nlags, fft=True)
    a_sq = acf(x ** 2, nlags=nlags, fft=True)
    band = 1.96 / np.sqrt(x.size)

    lb_r = acorr_ljungbox(x, lags=[10], return_df=True)
    lb_sq = acorr_ljungbox(x ** 2, lags=[10], return_df=True)

    return {
        "key": key,
        "symbol": series.symbol,
        "symbol_label": catalog.SYMBOL_LABEL[series.symbol],
        "asset_class": catalog.ASSET_CLASS[series.symbol],
        "timeframe": series.timeframe,
        "family": series.family,
        "role": series.role,
        "n_bars": int(len(df)),
        "n_returns_used": int(x.size),
        "n_trading_days": int(df["Date"].nunique()),
        "first_date": str(df["Date"].min().date()),
        "last_date": str(df["Date"].max().date()),
        "close_first": float(close.iloc[0]),
        "close_last": float(close.iloc[-1]),
        "ohlc_inconsistent_bars": int(df["ohlc_inconsistent"].sum()),

        "mean_pct": float(mu),
        "median_pct": float(np.median(x)),
        "sd_pct": float(sd),
        "min_pct": float(x.min()),
        "max_pct": float(x.max()),
        "skewness": float(stats.skew(x, bias=False)),
        "excess_kurtosis": float(stats.kurtosis(x, fisher=True, bias=False)),

        "jarque_bera": {"stat": float(jb_stat), "p": float(jb_p),
                        "reject_normal": bool(jb_p < config.ALPHA)},
        "shapiro_wilk": {"stat": float(sw_stat), "p": float(sw_p), "n": int(sub.size),
                         "reject_normal": bool(sw_p < config.ALPHA)},
        "tails": tails,

        "level_adf": lvl_adf, "level_kpss": lvl_kpss,
        "level_verdict": _verdict(lvl_adf, lvl_kpss),
        "return_adf": ret_adf, "return_kpss": ret_kpss,
        "return_verdict": _verdict(ret_adf, ret_kpss),

        "acf_lags_tested": int(nlags),
        "white_noise_band_95": float(band),
        "acf1_return": float(a_r[1]),
        "acf1_abs_return": float(a_abs[1]),
        "acf1_sq_return": float(a_sq[1]),
        "n_significant_acf_return": int(np.sum(np.abs(a_r[1:]) > band)),
        "n_significant_acf_abs": int(np.sum(np.abs(a_abs[1:]) > band)),
        "n_significant_acf_sq": int(np.sum(np.abs(a_sq[1:]) > band)),
        "ljung_box_return_Q10": float(lb_r["lb_stat"].iloc[0]),
        "ljung_box_return_p10": float(lb_r["lb_pvalue"].iloc[0]),
        "ljung_box_sq_Q10": float(lb_sq["lb_stat"].iloc[0]),
        "ljung_box_sq_p10": float(lb_sq["lb_pvalue"].iloc[0]),
    }


# --------------------------------------------------------------------------
def cross_family_check(primary_key: str, cc_key: str) -> dict:
    """Compare a HOSE_DLY series with its HOSE counterpart, bar by bar."""
    a = load_features(primary_key)[["Timestamp", "Close"]]
    b = load_features(cc_key)[["Timestamp", "Close"]]
    m = a.merge(b, on="Timestamp", how="outer", suffixes=("_primary", "_cc"),
                indicator=True)
    both = m[m["_merge"] == "both"].copy()
    both["rel"] = ((both["Close_primary"] - both["Close_cc"]).abs()
                   / both["Close_cc"])
    return {
        "primary": primary_key,
        "crosscheck": cc_key,
        "n_common_bars": int(len(both)),
        "n_only_in_primary": int((m["_merge"] == "left_only").sum()),
        "n_only_in_crosscheck": int((m["_merge"] == "right_only").sum()),
        "close_correlation": float(both["Close_primary"].corr(both["Close_cc"])),
        "median_abs_rel_diff": float(both["rel"].median()),
        "max_abs_rel_diff": float(both["rel"].max()),
        "pct_bars_differing_gt_0.1pct": round(100 * float((both["rel"] > 1e-3).mean()), 3),
    }


# --------------------------------------------------------------------------
def correlation_matrix(timeframe: str = "1D") -> dict:
    """
    Contemporaneous correlation of log returns across symbols at one
    timeframe, computed on the overlapping period only.

    Daily series are aligned on the trading DATE, not the bar timestamp: the
    equity bars are stamped 09:00 while the USD/VND bars are stamped 05:00, so
    a timestamp join would find zero overlap and silently drop the FX series.
    """
    keys = catalog.primary_keys(timeframes=[timeframe])
    join_col = "Date" if timeframe == "1D" else "Timestamp"
    frames = {}
    for k in keys:
        d = load_features(k)
        d = d[d["IsRegularBar"]]
        frames[catalog.get(k).symbol] = d.set_index(join_col)["LogReturn_pct"]
    wide = pd.DataFrame(frames).dropna()
    if wide.empty or wide.shape[1] < 2:
        return {"timeframe": timeframe, "n_overlapping_bars": 0, "note": "no overlap"}
    corr = wide.corr()
    return {
        "timeframe": timeframe,
        "symbols": list(wide.columns),
        "n_overlapping_bars": int(len(wide)),
        "overlap_start": str(wide.index.min().date()),
        "overlap_end": str(wide.index.max().date()),
        "pearson": {a: {b: round(float(corr.loc[a, b]), 4) for b in corr.columns}
                    for a in corr.index},
    }


# --------------------------------------------------------------------------
def matched_period(timeframe: str = "1D", symbols=None) -> dict:
    """
    Recompute the headline statistics for several symbols on their COMMON
    period.

    This control matters. VN-Index daily starts in 2000, VN30 in 2012 and
    VN100 in 2014, so any raw comparison between them confounds the market
    segment with the sample period - the early 2000s were a far thinner, more
    erratic market. Restricting every series to the dates all of them cover
    isolates the segment effect.
    """
    symbols = symbols or ["VNINDEX", "VN30", "VN100"]
    keys = [f"{s}_{timeframe}" for s in symbols]
    join_col = "Date" if timeframe == "1D" else "Timestamp"

    frames = {}
    for k in keys:
        d = load_features(k)
        d = d[d["IsRegularBar"]]
        frames[catalog.get(k).symbol] = d.set_index(join_col)["LogReturn_pct"]
    wide = pd.DataFrame(frames).dropna()
    if wide.empty:
        return {"timeframe": timeframe, "n_common": 0, "note": "no overlap"}

    out = {}
    for sym in wide.columns:
        x = wide[sym].to_numpy()
        a = acf(x, nlags=10, fft=True)
        band = 1.96 / np.sqrt(x.size)
        lb = acorr_ljungbox(x, lags=[10], return_df=True)
        out[sym] = {
            "n": int(x.size),
            "mean_pct": round(float(x.mean()), 4),
            "sd_pct": round(float(x.std(ddof=1)), 4),
            "skewness": round(float(stats.skew(x, bias=False)), 3),
            "excess_kurtosis": round(float(stats.kurtosis(x, fisher=True, bias=False)), 3),
            "acf1": round(float(a[1]), 4),
            "acf1_significant": bool(abs(a[1]) > band),
            "white_noise_band_95": round(float(band), 4),
            "ljung_box_Q10": round(float(lb["lb_stat"].iloc[0]), 2),
            "ljung_box_p10": float(lb["lb_pvalue"].iloc[0]),
        }
    return {
        "timeframe": timeframe,
        "symbols": list(wide.columns),
        "n_common": int(len(wide)),
        "start": str(pd.Timestamp(wide.index.min()).date()),
        "end": str(pd.Timestamp(wide.index.max()).date()),
        "stats": out,
    }


def frequency_scaling(symbol: str = "VNINDEX") -> dict:
    """
    Does return volatility scale with the square root of the sampling
    interval, as an i.i.d. random walk would imply?

    Each timeframe is measured on its own sample, so the comparison is
    indicative rather than a controlled test; the periods differ and that is
    recorded alongside the numbers.
    """
    rows = []
    for tf in ("M30", "H1", "H4", "1D"):
        key = f"{symbol}_{tf}"
        if key not in catalog.BY_KEY:
            continue
        r = return_sample(key)
        d = load_features(key)
        bars = catalog.BARS_PER_DAY[tf]
        rows.append({
            "timeframe": tf,
            "bars_per_day": bars,
            "n_returns": int(r.size),
            "period": f"{d['Date'].min().date()}..{d['Date'].max().date()}",
            "sd_pct": round(float(r.std(ddof=1)), 4),
            "sd_scaled_to_daily_pct": round(float(r.std(ddof=1)) * np.sqrt(bars), 4),
            "excess_kurtosis": round(float(stats.kurtosis(r, fisher=True, bias=False)), 3),
            "acf1": round(float(acf(r.to_numpy(), nlags=1, fft=True)[1]), 4),
        })
    return {
        "symbol": symbol,
        "note": ("sd_scaled_to_daily = sd x sqrt(bars per day). Under an i.i.d. "
                 "random walk these would all equal the daily sd. Samples cover "
                 "different periods, so treat this as indicative."),
        "rows": rows,
    }


# --------------------------------------------------------------------------
def to_table(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "series": r["key"],
            "symbol": r["symbol"],
            "tf": r["timeframe"],
            "n_ret": r["n_returns_used"],
            "period": f"{r['first_date']}..{r['last_date']}",
            "mean%": round(r["mean_pct"], 4),
            "sd%": round(r["sd_pct"], 4),
            "skew": round(r["skewness"], 3),
            "exkurt": round(r["excess_kurtosis"], 3),
            "JB_p": r["jarque_bera"]["p"],
            "level": r["level_verdict"],
            "returns": r["return_verdict"],
            "ACF1_r": round(r["acf1_return"], 4),
            "ACF1_|r|": round(r["acf1_abs_return"], 4),
            "ACF1_r2": round(r["acf1_sq_return"], 4),
            "LB_r_p": r["ljung_box_return_p10"],
            "LB_r2_p": r["ljung_box_sq_p10"],
        })
    return pd.DataFrame(rows)


def run() -> dict:
    primary = [battery(k) for k in catalog.primary_keys()]
    crosschecks = [cross_family_check(s.crosscheck_of, s.key) for s in catalog.CROSSCHECK]
    corrs = {tf: correlation_matrix(tf) for tf in ("1D", "M30", "H1", "H4")}

    matched = {tf: matched_period(tf) for tf in ("1D", "M30", "H1", "H4")}
    scaling = {sym: frequency_scaling(sym) for sym in ("VNINDEX", "VN30", "VN100")}

    payload = {
        "alpha": config.ALPHA,
        "note": ("Intraday batteries use REGULAR bars only (returns over the "
                 "timeframe's ordinary interval); bars spanning the overnight "
                 "gap or lunch break are excluded because they cover a "
                 "different amount of real time. At H4 every bar is a session "
                 "bar, so all bars are used."),
        "series": primary,
        "cross_family_checks": crosschecks,
        "return_correlations": corrs,
        "matched_period_comparison": matched,
        "frequency_scaling": scaling,
    }
    (config.RESULTS_DIR / "multiseries_battery.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    table = to_table(primary)
    table.to_csv(config.RESULTS_DIR / "multiseries_summary.csv", index=False)
    pd.DataFrame(crosschecks).to_csv(
        config.RESULTS_DIR / "cross_family_checks.csv", index=False)
    return payload


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)
    payload = run()
    t = to_table(payload["series"])

    def fp(v):
        return "<1e-300" if v == 0 else (f"{v:.2e}" if v < 1e-3 else f"{v:.4f}")

    show = t.copy()
    for c in ("JB_p", "LB_r_p", "LB_r2_p"):
        show[c] = show[c].map(fp)

    print("=== STATISTICAL BATTERY ACROSS ALL PRIMARY SERIES ===")
    print(show.to_string(index=False))

    print("\n=== CROSS-FAMILY CHECKS (HOSE_DLY primary vs HOSE vintage) ===")
    cc = pd.DataFrame(payload["cross_family_checks"])
    cc["median_abs_rel_diff"] = cc["median_abs_rel_diff"].map(lambda v: f"{v:.2e}")
    cc["close_correlation"] = cc["close_correlation"].map(lambda v: f"{v:.8f}")
    print(cc.to_string(index=False))

    print("\n=== RETURN CORRELATIONS ===")
    for tf, c in payload["return_correlations"].items():
        if c.get("n_overlapping_bars"):
            print(f"\n{tf}: {c['n_overlapping_bars']:,} overlapping bars "
                  f"({c['overlap_start']} .. {c['overlap_end']})")
            print(pd.DataFrame(c["pearson"]).to_string())

    print("\n=== MATCHED-PERIOD COMPARISON (identical dates for every symbol) ===")
    for tf, m in payload["matched_period_comparison"].items():
        if not m.get("n_common"):
            continue
        print(f"\n{tf}: {m['n_common']:,} common bars ({m['start']} .. {m['end']})")
        print(pd.DataFrame(m["stats"]).T[
            ["n", "sd_pct", "skewness", "excess_kurtosis", "acf1",
             "acf1_significant", "ljung_box_Q10"]].to_string())

    print("\n=== VOLATILITY SCALING WITH SAMPLING FREQUENCY ===")
    for sym, sc in payload["frequency_scaling"].items():
        print(f"\n{sym}")
        print(pd.DataFrame(sc["rows"]).to_string(index=False))

    print("\nSaved -> results/multiseries_battery.json, multiseries_summary.csv, "
          "cross_family_checks.csv")
