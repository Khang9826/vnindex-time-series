"""
Exploratory / descriptive analysis of the VN-Index level and return series.

Every function returns plain Python objects so that results can be written to
results/*.json and *.csv and quoted verbatim in the report.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

import config


# --------------------------------------------------------------------------
# 4.1 Descriptive statistics
# --------------------------------------------------------------------------
def describe_series(s: pd.Series, name: str) -> dict:
    x = s.dropna().astype(float)
    q = x.quantile([0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99])
    return {
        "series": name,
        "n": int(x.size),
        "mean": float(x.mean()),
        "median": float(x.median()),
        "std": float(x.std(ddof=1)),
        "variance": float(x.var(ddof=1)),
        "min": float(x.min()),
        "max": float(x.max()),
        "range": float(x.max() - x.min()),
        "q01": float(q.loc[0.01]),
        "q05": float(q.loc[0.05]),
        "q25": float(q.loc[0.25]),
        "q50": float(q.loc[0.50]),
        "q75": float(q.loc[0.75]),
        "q95": float(q.loc[0.95]),
        "q99": float(q.loc[0.99]),
        "iqr": float(q.loc[0.75] - q.loc[0.25]),
        # Fisher skewness / excess kurtosis (0 for a normal distribution)
        "skewness": float(stats.skew(x, bias=False)),
        "excess_kurtosis": float(stats.kurtosis(x, fisher=True, bias=False)),
    }


def descriptive_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = [
        describe_series(df["Close"], "VN-Index closing level (points)"),
        describe_series(df["Change"], "Daily change (points)"),
        describe_series(df["SimpleReturn_pct"], "Daily simple return (%)"),
        describe_series(df["LogReturn_pct"], "Daily log return (%)"),
        describe_series(df["Volume"].astype("float"), "Matched volume (shares)"),
    ]
    return pd.DataFrame(rows).set_index("series")


# --------------------------------------------------------------------------
# 4.3 Is the return distribution consistent with a normal distribution?
# --------------------------------------------------------------------------
def normality_tests(s: pd.Series, name: str) -> list:
    """
    Formal tests, because a histogram or a QQ plot is not evidence.

    All three tests share H0: the sample comes from a normal distribution.
    Shapiro-Wilk is restricted to a 5000-observation sub-sample because the
    scipy implementation is only accurate up to that size; the sub-sample is
    drawn with the project seed so the result is reproducible.
    """
    x = s.dropna().astype(float).to_numpy()
    out = []

    jb_stat, jb_p = stats.jarque_bera(x)
    out.append({
        "series": name, "test": "Jarque-Bera",
        "H0": "Sample skewness and kurtosis match a normal distribution",
        "H1": "Skewness and/or kurtosis differ from normal",
        "statistic": float(jb_stat), "p_value": float(jb_p),
        "df": 2, "n": int(x.size),
    })

    k2_stat, k2_p = stats.normaltest(x)
    out.append({
        "series": name, "test": "DAgostino-Pearson K2",
        "H0": "Sample comes from a normal distribution",
        "H1": "Sample does not come from a normal distribution",
        "statistic": float(k2_stat), "p_value": float(k2_p),
        "df": 2, "n": int(x.size),
    })

    rng = np.random.default_rng(config.RANDOM_SEED)
    sub = x if x.size <= 5000 else rng.choice(x, size=5000, replace=False)
    sw_stat, sw_p = stats.shapiro(sub)
    out.append({
        "series": name, "test": f"Shapiro-Wilk (n={sub.size} sub-sample)",
        "H0": "Sample comes from a normal distribution",
        "H1": "Sample does not come from a normal distribution",
        "statistic": float(sw_stat), "p_value": float(sw_p),
        "df": None, "n": int(sub.size),
    })
    return out


def tail_comparison(s: pd.Series) -> dict:
    """
    How often do |returns| exceed k standard deviations, observed vs. the
    frequency a normal distribution with the same mean/sd would imply?
    """
    x = s.dropna().astype(float)
    mu, sd = x.mean(), x.std(ddof=1)
    z = (x - mu) / sd
    res = {}
    for k in (2, 3, 4, 5):
        obs = int((z.abs() > k).sum())
        expected = float(2 * stats.norm.sf(k) * x.size)
        res[f"gt_{k}_sigma"] = {
            "observed_days": obs,
            "expected_days_if_normal": round(expected, 2),
            "ratio_observed_to_normal": round(obs / expected, 2) if expected > 0 else None,
        }
    res["mean_pct"] = float(mu)
    res["sd_pct"] = float(sd)
    return res


# --------------------------------------------------------------------------
# 9. Extreme movements
# --------------------------------------------------------------------------
def extreme_moves(df: pd.DataFrame, n: int = 15, sigma_threshold: float = 4.0) -> dict:
    d = df.dropna(subset=["LogReturn_pct"]).copy()
    mu = d["LogReturn_pct"].mean()
    sd = d["LogReturn_pct"].std(ddof=1)
    d["z"] = (d["LogReturn_pct"] - mu) / sd

    cols = ["Date", "Close", "Change", "SimpleReturn_pct", "LogReturn_pct", "z", "ohlc_inconsistent"]

    def fmt(frame):
        f = frame[cols].copy()
        f["Date"] = f["Date"].dt.strftime("%Y-%m-%d")
        return f.round(4).to_dict("records")

    beyond = d[d["z"].abs() > sigma_threshold]
    return {
        "mean_log_return_pct": float(mu),
        "sd_log_return_pct": float(sd),
        "sigma_threshold": sigma_threshold,
        "n_beyond_threshold": int(len(beyond)),
        "pct_of_sample_beyond_threshold": round(100 * len(beyond) / len(d), 3),
        "largest_drops": fmt(d.nsmallest(n, "LogReturn_pct")),
        "largest_gains": fmt(d.nlargest(n, "LogReturn_pct")),
        "beyond_threshold_by_year": {
            str(k): int(v) for k, v in beyond["Date"].dt.year.value_counts().sort_index().items()
        },
        "n_beyond_threshold_flagged_ohlc": int(beyond["ohlc_inconsistent"].sum()),
    }


# --------------------------------------------------------------------------
# 8. Calendar / seasonal patterns
# --------------------------------------------------------------------------
_WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def day_of_week_effect(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["LogReturn_pct"])
    groups = [d.loc[d["Weekday"] == w, "LogReturn_pct"].to_numpy() for w in _WEEKDAY_ORDER]
    groups = [g for g in groups if g.size > 0]

    f_stat, f_p = stats.f_oneway(*groups)
    h_stat, h_p = stats.kruskal(*groups)
    lev_stat, lev_p = stats.levene(*groups, center="median")

    summary = (
        d.groupby("Weekday")["LogReturn_pct"]
        .agg(["count", "mean", "median", "std"])
        .reindex(_WEEKDAY_ORDER)
        .dropna(how="all")
        .round(4)
    )
    return {
        "group_summary": summary.reset_index().to_dict("records"),
        "tests": [
            {"test": "One-way ANOVA",
             "H0": "Mean log return is equal across weekdays",
             "H1": "At least one weekday has a different mean log return",
             "statistic": float(f_stat), "p_value": float(f_p)},
            {"test": "Kruskal-Wallis H",
             "H0": "Log-return distributions are identical across weekdays",
             "H1": "At least one weekday has a different distribution",
             "statistic": float(h_stat), "p_value": float(h_p)},
            {"test": "Levene (median-centred)",
             "H0": "Log-return variance is equal across weekdays",
             "H1": "Variance differs across weekdays",
             "statistic": float(lev_stat), "p_value": float(lev_p)},
        ],
    }


def month_effect(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["LogReturn_pct"])
    groups = [d.loc[d["Month"] == m, "LogReturn_pct"].to_numpy() for m in range(1, 13)]
    groups = [g for g in groups if g.size > 0]

    f_stat, f_p = stats.f_oneway(*groups)
    h_stat, h_p = stats.kruskal(*groups)

    summary = (
        d.groupby("Month")["LogReturn_pct"]
        .agg(["count", "mean", "median", "std"])
        .round(4)
        .reset_index()
    )
    return {
        "group_summary": summary.to_dict("records"),
        "tests": [
            {"test": "One-way ANOVA",
             "H0": "Mean daily log return is equal across calendar months",
             "H1": "At least one month has a different mean daily log return",
             "statistic": float(f_stat), "p_value": float(f_p)},
            {"test": "Kruskal-Wallis H",
             "H0": "Log-return distributions are identical across months",
             "H1": "At least one month has a different distribution",
             "statistic": float(h_stat), "p_value": float(h_p)},
        ],
    }


def yearly_summary(df: pd.DataFrame) -> list:
    d = df.dropna(subset=["LogReturn_pct"])
    g = d.groupby("Year").agg(
        sessions=("Close", "size"),
        first_close=("Close", "first"),
        last_close=("Close", "last"),
        mean_log_ret_pct=("LogReturn_pct", "mean"),
        sd_log_ret_pct=("LogReturn_pct", "std"),
        min_log_ret_pct=("LogReturn_pct", "min"),
        max_log_ret_pct=("LogReturn_pct", "max"),
    )
    g["year_return_pct"] = 100 * (g["last_close"] / g["first_close"] - 1)
    g["annualised_vol_pct"] = g["sd_log_ret_pct"] * np.sqrt(config.TRADING_DAYS_PER_YEAR)
    return g.round(4).reset_index().to_dict("records")


# --------------------------------------------------------------------------
if __name__ == "__main__":
    from preprocessing import load_features

    df = load_features()

    desc = descriptive_table(df)
    desc.to_csv(config.RESULTS_DIR / "descriptive_statistics.csv")

    norm = normality_tests(df["LogReturn_pct"], "Daily log return (%)")
    norm += normality_tests(df["SimpleReturn_pct"], "Daily simple return (%)")
    pd.DataFrame(norm).to_csv(config.RESULTS_DIR / "normality_tests.csv", index=False)

    payload = {
        "normality_tests": norm,
        "tail_comparison_log_returns": tail_comparison(df["LogReturn_pct"]),
        "extreme_moves": extreme_moves(df),
        "day_of_week_effect": day_of_week_effect(df),
        "month_effect": month_effect(df),
        "yearly_summary": yearly_summary(df),
    }
    (config.RESULTS_DIR / "eda_results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    pd.set_option("display.width", 200)
    print("=== DESCRIPTIVE STATISTICS ===")
    print(desc.T.to_string(float_format=lambda v: f"{v:,.4f}"))
    print("\n=== NORMALITY TESTS ===")
    print(pd.DataFrame(norm)[["series", "test", "statistic", "p_value", "n"]].to_string(index=False))
    print("\n=== TAIL FREQUENCY vs NORMAL (log returns) ===")
    print(json.dumps(payload["tail_comparison_log_returns"], indent=2))
    print("\nSaved -> results/descriptive_statistics.csv, normality_tests.csv, eda_results.json")
