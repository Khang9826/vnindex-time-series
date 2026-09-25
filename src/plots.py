"""
Report-ready figures for the VN-Index analysis.

Every figure is written to figures/ as a 150-dpi PNG with a title, labelled
axes and explicit units.  The x-axis of every time-domain plot is the actual
trading date, in chronological order.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

import config

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "font.size": 10,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "legend.frameon": False,
})

LINE = "#1f4e79"
ACCENT = "#c0392b"
NEUTRAL = "#7f8c8d"


def _save(fig, name: str) -> str:
    path = config.FIGURES_DIR / name
    fig.savefig(path)
    plt.close(fig)
    return name


def _date_axis(ax):
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


# --------------------------------------------------------------------------
def fig_price(df: pd.DataFrame) -> str:
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    ax1.plot(df["Date"], df["Close"], color=LINE, lw=0.8)
    ax1.set_title(
        f"VN-Index closing level, {df['Date'].min():%Y-%m-%d} to {df['Date'].max():%Y-%m-%d} "
        f"({len(df):,} trading sessions)"
    )
    ax1.set_ylabel("Index level (points)")

    imax = df["Close"].idxmax()
    imin = df["Close"].idxmin()
    for i, color, va in ((imax, ACCENT, "bottom"), (imin, NEUTRAL, "top")):
        ax1.scatter(df.loc[i, "Date"], df.loc[i, "Close"], color=color, s=25, zorder=5)
        ax1.annotate(
            f"{df.loc[i, 'Close']:,.2f}\n{df.loc[i, 'Date']:%Y-%m-%d}",
            (df.loc[i, "Date"], df.loc[i, "Close"]),
            textcoords="offset points", xytext=(0, 8 if va == "bottom" else -28),
            ha="center", fontsize=8, color=color,
        )

    ax2.plot(df["Date"], df["Volume"] / 1e6, color=NEUTRAL, lw=0.5)
    ax2.set_ylabel("Matched volume\n(million shares)")
    ax2.set_xlabel("Date")
    _date_axis(ax2)
    fig.align_ylabels()
    return _save(fig, "01_vnindex_close_and_volume.png")


def fig_ohlc_recent(df: pd.DataFrame, n_days: int = 250) -> str:
    d = df.tail(n_days)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.vlines(d["Date"], d["Low"], d["High"], color=NEUTRAL, lw=0.7, label="High-Low range")
    ax.plot(d["Date"], d["Close"], color=LINE, lw=1.0, label="Close")
    ax.set_title(f"VN-Index daily high-low range and close, last {len(d)} sessions")
    ax.set_ylabel("Index level (points)")
    ax.set_xlabel("Date")
    ax.legend(loc="best")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    return _save(fig, "02_vnindex_ohlc_recent.png")


def fig_returns_series(df: pd.DataFrame) -> str:
    d = df.dropna(subset=["LogReturn_pct"])
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(d["Date"], d["LogReturn_pct"], color=LINE, lw=0.4)
    sd = d["LogReturn_pct"].std(ddof=1)
    for k, style in ((3, "--"), (-3, "--")):
        ax.axhline(k * sd, color=ACCENT, ls=style, lw=0.8)
    ax.text(d["Date"].iloc[5], 3 * sd, r"$\pm 3\sigma$", color=ACCENT, fontsize=8, va="bottom")
    ax.set_title("VN-Index daily log returns over time")
    ax.set_ylabel("Log return (%)")
    ax.set_xlabel("Date")
    _date_axis(ax)
    return _save(fig, "03_daily_log_returns.png")


def fig_return_distribution(df: pd.DataFrame) -> str:
    x = df["LogReturn_pct"].dropna()
    mu, sd = x.mean(), x.std(ddof=1)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))

    ax = axes[0]
    ax.hist(x, bins=100, density=True, color=LINE, alpha=0.75, label="Observed")
    grid = np.linspace(x.min(), x.max(), 500)
    ax.plot(grid, stats.norm.pdf(grid, mu, sd), color=ACCENT, lw=1.5,
            label=f"Normal({mu:.3f}, {sd:.3f})")
    ax.set_title("Histogram vs fitted normal")
    ax.set_xlabel("Daily log return (%)")
    ax.set_ylabel("Density")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.hist(x, bins=100, density=True, color=LINE, alpha=0.75)
    ax.plot(grid, stats.norm.pdf(grid, mu, sd), color=ACCENT, lw=1.5)
    ax.set_yscale("log")
    ax.set_title("Same histogram, log density (tails)")
    ax.set_xlabel("Daily log return (%)")
    ax.set_ylabel("Density (log scale)")

    ax = axes[2]
    stats.probplot(x, dist="norm", plot=ax)
    ax.get_lines()[0].set_markersize(2)
    ax.get_lines()[0].set_color(LINE)
    ax.get_lines()[1].set_color(ACCENT)
    ax.set_title("Normal Q-Q plot")
    ax.set_xlabel("Theoretical quantiles (normal)")
    ax.set_ylabel("Sample quantiles (%)")

    fig.suptitle(
        "Distribution of VN-Index daily log returns "
        f"(n={x.size:,}, skew={stats.skew(x, bias=False):.3f}, "
        f"excess kurtosis={stats.kurtosis(x, bias=False):.3f})",
        fontweight="bold",
    )
    fig.tight_layout()
    return _save(fig, "04_return_distribution.png")


def fig_return_boxplots(df: pd.DataFrame) -> str:
    d = df.dropna(subset=["LogReturn_pct"])
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5),
                             gridspec_kw={"width_ratios": [3, 1]})

    years = sorted(d["Year"].unique())
    axes[0].boxplot([d.loc[d["Year"] == y, "LogReturn_pct"] for y in years],
                    tick_labels=[str(y) for y in years], showfliers=True,
                    flierprops={"markersize": 2, "alpha": 0.4})
    axes[0].axhline(0, color=NEUTRAL, lw=0.8)
    axes[0].set_title("Daily log returns by calendar year")
    axes[0].set_ylabel("Log return (%)")
    axes[0].set_xlabel("Year")
    axes[0].tick_params(axis="x", rotation=90, labelsize=8)

    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    present = [w for w in order if (d["Weekday"] == w).any()]
    axes[1].boxplot([d.loc[d["Weekday"] == w, "LogReturn_pct"] for w in present],
                    tick_labels=[w[:3] for w in present], showfliers=True,
                    flierprops={"markersize": 2, "alpha": 0.4})
    axes[1].axhline(0, color=NEUTRAL, lw=0.8)
    axes[1].set_title("Daily log returns by weekday")
    axes[1].set_xlabel("Weekday")

    fig.tight_layout()
    return _save(fig, "05_return_boxplots.png")


def fig_rolling_volatility(df: pd.DataFrame) -> str:
    d = df.dropna(subset=["LogReturn_pct"]).set_index("Date")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    colors = [LINE, ACCENT, "#27ae60"]
    for w, c in zip(config.ROLLING_WINDOWS, colors):
        roll = d["LogReturn_pct"].rolling(w).std(ddof=1) * np.sqrt(config.TRADING_DAYS_PER_YEAR)
        ax1.plot(roll.index, roll, color=c, lw=0.8, label=f"{w}-session window")
    ax1.set_title("Annualised rolling volatility of VN-Index log returns")
    ax1.set_ylabel("Annualised volatility (%)")
    ax1.legend(loc="upper right", fontsize=8)

    ax2.plot(d.index, d["LogReturn_pct"].abs(), color=NEUTRAL, lw=0.4)
    ax2.set_title("Absolute daily log return (volatility clustering)")
    ax2.set_ylabel("|Log return| (%)")
    ax2.set_xlabel("Date")
    _date_axis(ax2)
    fig.align_ylabels()
    fig.tight_layout()
    return _save(fig, "06_rolling_volatility.png")


def fig_calendar_effects(df: pd.DataFrame) -> str:
    d = df.dropna(subset=["LogReturn_pct"])
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))

    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    present = [w for w in order if (d["Weekday"] == w).any()]
    wk = d.groupby("Weekday")["LogReturn_pct"].agg(["mean", "sem"]).reindex(present)
    axes[0].bar(range(len(wk)), wk["mean"], yerr=1.96 * wk["sem"], color=LINE,
                capsize=3, alpha=0.85)
    axes[0].set_xticks(range(len(wk)))
    axes[0].set_xticklabels([w[:3] for w in present])
    axes[0].axhline(0, color=NEUTRAL, lw=0.8)
    axes[0].set_title("Mean log return by weekday")
    axes[0].set_ylabel("Mean daily log return (%)")
    axes[0].set_xlabel("Weekday (95% CI)")

    mo = d.groupby("Month")["LogReturn_pct"].agg(["mean", "sem"])
    axes[1].bar(mo.index, mo["mean"], yerr=1.96 * mo["sem"], color=LINE,
                capsize=3, alpha=0.85)
    axes[1].axhline(0, color=NEUTRAL, lw=0.8)
    axes[1].set_xticks(range(1, 13))
    axes[1].set_title("Mean log return by calendar month")
    axes[1].set_ylabel("Mean daily log return (%)")
    axes[1].set_xlabel("Month (95% CI)")

    yr = d.groupby("Year")["LogReturn_pct"].sum()
    axes[2].bar(yr.index, yr, color=[ACCENT if v < 0 else LINE for v in yr], alpha=0.85)
    axes[2].axhline(0, color=NEUTRAL, lw=0.8)
    axes[2].set_title("Cumulative log return by year")
    axes[2].set_ylabel("Sum of daily log returns (%)")
    axes[2].set_xlabel("Year")
    axes[2].tick_params(axis="x", rotation=90, labelsize=8)

    fig.tight_layout()
    return _save(fig, "07_calendar_effects.png")


def build_all(df: pd.DataFrame) -> list:
    return [
        fig_price(df),
        fig_ohlc_recent(df),
        fig_returns_series(df),
        fig_return_distribution(df),
        fig_return_boxplots(df),
        fig_rolling_volatility(df),
        fig_calendar_effects(df),
    ]


if __name__ == "__main__":
    from preprocessing import load_features

    df = load_features()
    for name in build_all(df):
        print(f"figures/{name}")
