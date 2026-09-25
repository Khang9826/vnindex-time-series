"""
Stationarity analysis of the VN-Index.

Two tests with OPPOSITE null hypotheses are used, because a single test can
easily be ambiguous:

    ADF   H0: the series has a unit root          -> NON-stationary
          H1: the series is (trend-)stationary
          Reject H0 (small p) => evidence FOR stationarity.

    KPSS  H0: the series is (trend-)stationary
          H1: the series has a unit root          -> NON-stationary
          Reject H0 (small p) => evidence AGAINST stationarity.

Reading the pair together:
    ADF rejects  + KPSS does not reject  -> stationary
    ADF does not + KPSS rejects          -> unit root / non-stationary
    both reject / neither rejects        -> ambiguous, report as such
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, kpss

import config


def adf_test(s: pd.Series, name: str, regression: str = "c") -> dict:
    """Augmented Dickey-Fuller. Lag order chosen by AIC (statsmodels default)."""
    x = s.dropna().astype(float).to_numpy()
    try:
        # statsmodels >= 0.15 warns about a coming change of return type
        stat, p, used_lag, nobs, crit, icbest = adfuller(
            x, regression=regression, autolag="AIC", result_object=False
        )
    except TypeError:  # older statsmodels without the keyword
        stat, p, used_lag, nobs, crit, icbest = adfuller(
            x, regression=regression, autolag="AIC"
        )
    return {
        "series": name,
        "test": "ADF (Augmented Dickey-Fuller)",
        "regression": regression,
        "H0": "The series contains a unit root (non-stationary)",
        "H1": "The series is stationary"
              + (" around a deterministic trend" if regression == "ct" else ""),
        "statistic": float(stat),
        "p_value": float(p),
        "lags_used": int(used_lag),
        "n_obs": int(nobs),
        "critical_values": {k: float(v) for k, v in crit.items()},
        "alpha": config.ALPHA,
        "reject_H0": bool(p < config.ALPHA),
        "conclusion": (
            "Reject H0 at alpha=%.2f: evidence of stationarity" % config.ALPHA
            if p < config.ALPHA
            else "Fail to reject H0 at alpha=%.2f: unit root cannot be ruled out" % config.ALPHA
        ),
    }


def kpss_test(s: pd.Series, name: str, regression: str = "c") -> dict:
    """KPSS with automatic (Newey-West) bandwidth."""
    x = s.dropna().astype(float).to_numpy()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        stat, p, lags, crit = kpss(x, regression=regression, nlags="auto")
        # statsmodels warns when p is outside the tabulated range
        note = "; ".join(str(w.message) for w in caught) or None
    return {
        "series": name,
        "test": "KPSS",
        "regression": regression,
        "H0": ("The series is stationary around a constant"
               if regression == "c" else
               "The series is stationary around a deterministic trend"),
        "H1": "The series is non-stationary (unit root)",
        "statistic": float(stat),
        "p_value": float(p),
        "lags_used": int(lags),
        "critical_values": {k: float(v) for k, v in crit.items()},
        "alpha": config.ALPHA,
        "reject_H0": bool(p < config.ALPHA),
        "p_value_note": note,
        "conclusion": (
            "Reject H0 at alpha=%.2f: evidence against stationarity" % config.ALPHA
            if p < config.ALPHA
            else "Fail to reject H0 at alpha=%.2f: stationarity is not contradicted" % config.ALPHA
        ),
    }


def combined_verdict(adf: dict, kpss_res: dict) -> str:
    a, k = adf["reject_H0"], kpss_res["reject_H0"]
    if a and not k:
        return "STATIONARY (ADF rejects a unit root, KPSS does not reject stationarity)"
    if not a and k:
        return "NON-STATIONARY (ADF cannot reject a unit root, KPSS rejects stationarity)"
    if a and k:
        return ("AMBIGUOUS - both tests reject their own H0. Often a sign of a "
                "trend-stationary or structurally breaking series; differencing "
                "or de-trending should be examined.")
    return ("AMBIGUOUS - neither test rejects. The sample is not informative "
            "enough to discriminate.")


def run_suite(df: pd.DataFrame) -> dict:
    close = df["Close"]
    log_close = np.log(df["Close"])
    log_ret = df["LogReturn_pct"]
    diff_close = df["Change"]

    targets = [
        (close, "VN-Index level (points)", "c"),
        (close, "VN-Index level (points)", "ct"),
        (log_close, "log(VN-Index level)", "c"),
        (log_close, "log(VN-Index level)", "ct"),
        (diff_close, "First difference of level (points)", "c"),
        (log_ret, "Daily log return (%)", "c"),
    ]

    results = []
    for s, name, reg in targets:
        a = adf_test(s, name, reg)
        k = kpss_test(s, name, reg)
        results.append({
            "series": name,
            "regression": reg,
            "adf": a,
            "kpss": k,
            "verdict": combined_verdict(a, k),
        })
    return {"alpha": config.ALPHA, "tests": results}


def to_table(suite: dict) -> pd.DataFrame:
    rows = []
    for r in suite["tests"]:
        rows.append({
            "series": r["series"],
            "regression": r["regression"],
            "ADF_stat": round(r["adf"]["statistic"], 4),
            "ADF_p": r["adf"]["p_value"],
            "ADF_lags": r["adf"]["lags_used"],
            "ADF_crit_5%": round(r["adf"]["critical_values"]["5%"], 4),
            "KPSS_stat": round(r["kpss"]["statistic"], 4),
            "KPSS_p": r["kpss"]["p_value"],
            "KPSS_lags": r["kpss"]["lags_used"],
            "KPSS_crit_5%": round(r["kpss"]["critical_values"]["5%"], 4),
            "verdict": r["verdict"].split(" (")[0].split(" -")[0],
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from preprocessing import load_features

    df = load_features()
    suite = run_suite(df)

    (config.RESULTS_DIR / "stationarity_tests.json").write_text(
        json.dumps(suite, indent=2), encoding="utf-8"
    )
    table = to_table(suite)
    table.to_csv(config.RESULTS_DIR / "stationarity_tests.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)
    print("=== STATIONARITY TESTS (alpha = %.2f) ===" % config.ALPHA)
    print(table.to_string(index=False))
    print("\nVerdicts:")
    for r in suite["tests"]:
        print(f"  [{r['regression']}] {r['series']}: {r['verdict']}")
    print("\nSaved -> results/stationarity_tests.{json,csv}")
