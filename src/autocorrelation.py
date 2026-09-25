"""
Autocorrelation analysis (ACF / PACF) and portmanteau tests.

ACF/PACF are only interpretable for a stationary series, so the analysis is
run on the log-return series (shown stationary in src/stationarity.py).  The
index level is included only as a contrast, to make the unit-root behaviour
visible.

The transformations |r_t| and r_t^2 are included because they are the standard
diagnostics for volatility clustering: returns can be nearly uncorrelated
while their magnitudes are strongly autocorrelated.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import acf, pacf

import config
from plots import ACCENT, LINE, _save


def acf_pacf_values(s: pd.Series, name: str, nlags: int = config.MAX_LAG) -> dict:
    """ACF/PACF point estimates with the +/- 1.96/sqrt(n) white-noise band."""
    x = s.dropna().astype(float).to_numpy()
    n = x.size
    a = acf(x, nlags=nlags, fft=True)
    p = pacf(x, nlags=nlags, method="ywadjusted")
    band = 1.96 / np.sqrt(n)

    rows = []
    for lag in range(1, nlags + 1):
        rows.append({
            "lag": lag,
            "acf": float(a[lag]),
            "acf_significant": bool(abs(a[lag]) > band),
            "pacf": float(p[lag]),
            "pacf_significant": bool(abs(p[lag]) > band),
        })
    return {
        "series": name,
        "n": int(n),
        "white_noise_band_95": float(band),
        "n_significant_acf_lags": int(sum(r["acf_significant"] for r in rows)),
        "n_significant_pacf_lags": int(sum(r["pacf_significant"] for r in rows)),
        "values": rows,
    }


def ljung_box(s: pd.Series, name: str, lags=(5, 10, 20, 40), model_df: int = 0) -> list:
    """
    Ljung-Box Q test.

    H0: the autocorrelations of the series up to lag h are all zero
        (the series is white noise up to lag h)
    H1: at least one autocorrelation up to lag h is non-zero

    `model_df` subtracts the number of estimated ARMA parameters when the
    series being tested is a residual series.
    """
    x = s.dropna().astype(float)
    res = acorr_ljungbox(x, lags=list(lags), model_df=model_df, return_df=True)
    out = []
    for lag, row in res.iterrows():
        out.append({
            "series": name,
            "test": "Ljung-Box Q",
            "H0": f"No autocorrelation up to lag {lag}",
            "H1": f"At least one non-zero autocorrelation up to lag {lag}",
            "lag": int(lag),
            "statistic": float(row["lb_stat"]),
            "p_value": float(row["lb_pvalue"]),
            "df": int(lag - model_df),
            "reject_H0_at_5pct": bool(row["lb_pvalue"] < config.ALPHA),
        })
    return out


def fig_acf_pacf(series_map: dict, filename: str, suptitle: str) -> str:
    n = len(series_map)
    fig, axes = plt.subplots(n, 2, figsize=(12, 3.2 * n), squeeze=False)
    for i, (name, s) in enumerate(series_map.items()):
        x = s.dropna().astype(float)
        plot_acf(x, lags=config.MAX_LAG, ax=axes[i][0], alpha=0.05,
                 color=LINE, vlines_kwargs={"colors": LINE})
        axes[i][0].set_title(f"ACF - {name}")
        axes[i][0].set_xlabel("Lag (trading days)")
        axes[i][0].set_ylabel("Autocorrelation")

        plot_pacf(x, lags=config.MAX_LAG, ax=axes[i][1], alpha=0.05, method="ywm",
                  color=ACCENT, vlines_kwargs={"colors": ACCENT})
        axes[i][1].set_title(f"PACF - {name}")
        axes[i][1].set_xlabel("Lag (trading days)")
        axes[i][1].set_ylabel("Partial autocorrelation")
    fig.suptitle(suptitle, fontweight="bold")
    fig.tight_layout()
    return _save(fig, filename)


def run(df: pd.DataFrame) -> dict:
    r = df["LogReturn_pct"]
    series = {
        "VN-Index level (points)": df["Close"],
        "Daily log return (%)": r,
        "Absolute log return |r|": r.abs(),
        "Squared log return r^2": r ** 2,
    }

    values = {name: acf_pacf_values(s, name) for name, s in series.items()}

    lb = []
    lb += ljung_box(r, "Daily log return (%)")
    lb += ljung_box(r.abs(), "Absolute log return |r|")
    lb += ljung_box(r ** 2, "Squared log return r^2")

    figs = [
        fig_acf_pacf(
            {"VN-Index level (points)": df["Close"], "Daily log return (%)": r},
            "08_acf_pacf_level_and_returns.png",
            "Autocorrelation of the VN-Index level vs. its daily log returns",
        ),
        fig_acf_pacf(
            {"Absolute log return |r|": r.abs(), "Squared log return r^2": r ** 2},
            "09_acf_pacf_volatility_proxies.png",
            "Autocorrelation of volatility proxies (evidence of volatility clustering)",
        ),
    ]
    return {"acf_pacf": values, "ljung_box": lb, "figures": figs}


if __name__ == "__main__":
    from preprocessing import load_features

    df = load_features()
    res = run(df)

    (config.RESULTS_DIR / "autocorrelation.json").write_text(
        json.dumps(res, indent=2), encoding="utf-8"
    )
    pd.DataFrame(res["ljung_box"]).to_csv(
        config.RESULTS_DIR / "ljung_box_tests.csv", index=False
    )

    pd.set_option("display.width", 200)
    print("=== ACF / PACF SUMMARY (lags 1..%d, 95%% band) ===" % config.MAX_LAG)
    for name, v in res["acf_pacf"].items():
        print(f"\n{name}  (n={v['n']:,}, band=+/-{v['white_noise_band_95']:.4f})")
        print(f"  significant ACF lags : {v['n_significant_acf_lags']}/{config.MAX_LAG}")
        print(f"  significant PACF lags: {v['n_significant_pacf_lags']}/{config.MAX_LAG}")
        head = pd.DataFrame(v["values"]).head(10)[["lag", "acf", "pacf"]].round(4)
        print("  first 10 lags:")
        print(head.to_string(index=False).replace("\n", "\n  "))

    print("\n=== LJUNG-BOX TESTS ===")
    print(pd.DataFrame(res["ljung_box"])[
        ["series", "lag", "statistic", "p_value", "reject_H0_at_5pct"]
    ].to_string(index=False))
    print("\nFigures:", ", ".join(res["figures"]))
    print("Saved -> results/autocorrelation.json, results/ljung_box_tests.csv")
