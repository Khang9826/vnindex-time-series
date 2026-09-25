"""
Comparative figures across the whole dataset: symbols, timeframes and asset
classes. The single-series figures live in plots.py.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import catalog
import config
from plots import ACCENT, LINE, NEUTRAL, _save
from preprocessing import load_features

SYMBOL_COLOR = {
    "VNINDEX": "#1f4e79",
    "VN30": "#c0392b",
    "VN100": "#27ae60",
    "USDVND": "#8e44ad",
}
TF_ORDER = ["M30", "H1", "H4", "1D"]


def _battery() -> dict:
    return json.loads(
        (config.RESULTS_DIR / "multiseries_battery.json").read_text(encoding="utf-8")
    )


# --------------------------------------------------------------------------
def fig_index_comparison() -> str:
    """Rebased price paths of the three equity indices, plus USD/VND."""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7.5), sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )

    # Rebase every index to 100 at the first date all three exist.
    frames = {s: load_features(f"{s}_1D").set_index("Date")["Close"]
              for s in ("VNINDEX", "VN30", "VN100")}
    start = max(f.index.min() for f in frames.values())
    for sym, s in frames.items():
        s = s[s.index >= start]
        ax1.plot(s.index, 100 * s / s.iloc[0], color=SYMBOL_COLOR[sym], lw=1.0, label=sym)
    ax1.axhline(100, color=NEUTRAL, lw=0.8, ls="--")
    ax1.set_title(f"Vietnamese equity indices rebased to 100 at {start:%Y-%m-%d}")
    ax1.set_ylabel("Index level (rebased)")
    ax1.legend(loc="upper left", fontsize=9)

    fx = load_features("USDVND_1D").set_index("Date")["Close"]
    fx = fx[fx.index >= start]
    ax2.plot(fx.index, fx, color=SYMBOL_COLOR["USDVND"], lw=1.0)
    ax2.set_title("USD/VND exchange rate over the same window")
    ax2.set_ylabel("VND per USD")
    ax2.set_xlabel("Date")
    ax2.xaxis.set_major_locator(mdates.YearLocator(1))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.align_ylabels()
    fig.tight_layout()
    return _save(fig, "10_index_and_fx_comparison.png")


def fig_frequency_scaling() -> str:
    """How volatility, tail weight and autocorrelation change with frequency."""
    b = _battery()
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))

    for sym, sc in b["frequency_scaling"].items():
        rows = {r["timeframe"]: r for r in sc["rows"]}
        tfs = [t for t in TF_ORDER if t in rows]
        xs = range(len(tfs))
        c = SYMBOL_COLOR[sym]
        axes[0].plot(xs, [rows[t]["sd_scaled_to_daily_pct"] for t in tfs],
                     "o-", color=c, label=sym, lw=1.2, ms=5)
        axes[1].plot(xs, [rows[t]["excess_kurtosis"] for t in tfs],
                     "o-", color=c, label=sym, lw=1.2, ms=5)
        axes[2].plot(xs, [rows[t]["acf1"] for t in tfs],
                     "o-", color=c, label=sym, lw=1.2, ms=5)

    for ax, title, ylab in zip(
        axes,
        ["Volatility scaled to daily units", "Tail weight", "First-order autocorrelation"],
        ["sd × √(bars per day)  (%)", "Excess kurtosis", "ACF(1) of returns"],
    ):
        ax.set_xticks(range(len(TF_ORDER)))
        ax.set_xticklabels(TF_ORDER)
        ax.set_title(title)
        ax.set_xlabel("Sampling frequency")
        ax.set_ylabel(ylab)
        ax.legend(fontsize=8)
    axes[1].axhline(0, color=NEUTRAL, lw=0.8, ls="--")
    axes[2].axhline(0, color=NEUTRAL, lw=0.8, ls="--")

    fig.suptitle(
        "Statistical properties across sampling frequencies "
        "(each frequency on its own sample period)", fontweight="bold")
    fig.tight_layout()
    return _save(fig, "11_frequency_scaling.png")


def fig_matched_period() -> str:
    """The control that matters: same dates for every symbol."""
    b = _battery()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # Left: raw (own sample) vs matched-period ACF(1) at daily frequency.
    raw = {r["symbol"]: r["acf1_return"] for r in b["series"]
           if r["timeframe"] == "1D" and r["symbol"] != "USDVND"}
    m = b["matched_period_comparison"]["1D"]
    matched = {s: v["acf1"] for s, v in m["stats"].items()}
    syms = ["VNINDEX", "VN30", "VN100"]
    x = np.arange(len(syms))
    w = 0.36
    axes[0].bar(x - w / 2, [raw[s] for s in syms], w, label="Full own sample",
                color=LINE, alpha=0.9)
    axes[0].bar(x + w / 2, [matched[s] for s in syms], w,
                label=f"Matched period ({m['start']}–{m['end']})",
                color=ACCENT, alpha=0.9)
    band = list(m["stats"].values())[0]["white_noise_band_95"]
    axes[0].axhline(band, color=NEUTRAL, ls="--", lw=0.9)
    axes[0].axhline(-band, color=NEUTRAL, ls="--", lw=0.9)
    axes[0].text(2.35, band, "95% white-noise band", fontsize=7,
                 color=NEUTRAL, va="bottom", ha="right")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(syms)
    axes[0].set_ylabel("ACF(1) of daily log returns")
    axes[0].set_title("Autocorrelation: sample period vs market segment")
    axes[0].legend(fontsize=8)

    # Right: correlation heatmap of daily returns.
    c = b["return_correlations"]["1D"]
    labels = c["symbols"]
    mat = np.array([[c["pearson"][a][bb] for bb in labels] for a in labels])
    im = axes[1].imshow(mat, cmap="RdYlBu_r", vmin=-1, vmax=1)
    axes[1].set_xticks(range(len(labels)))
    axes[1].set_xticklabels(labels, rotation=45, ha="right")
    axes[1].set_yticks(range(len(labels)))
    axes[1].set_yticklabels(labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            axes[1].text(j, i, f"{mat[i, j]:.3f}", ha="center", va="center",
                         fontsize=9,
                         color="white" if abs(mat[i, j]) > 0.6 else "black")
    axes[1].set_title(f"Daily log-return correlation\n({c['n_overlapping_bars']:,} "
                      f"common sessions, {c['overlap_start']}–{c['overlap_end']})")
    fig.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04)

    fig.tight_layout()
    return _save(fig, "12_matched_period_and_correlation.png")


def fig_return_distributions_by_timeframe(symbol: str = "VNINDEX") -> str:
    """Aggregational Gaussianity: distributions get less fat-tailed as bars widen."""
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.6), sharey=False)
    from scipy import stats as sps

    for ax, tf in zip(axes, TF_ORDER):
        key = f"{symbol}_{tf}"
        d = load_features(key)
        r = d.loc[d["IsRegularBar"], "LogReturn_pct"].dropna()
        z = (r - r.mean()) / r.std(ddof=1)
        ax.hist(z, bins=120, density=True, color=LINE, alpha=0.8, range=(-8, 8))
        grid = np.linspace(-8, 8, 400)
        ax.plot(grid, sps.norm.pdf(grid), color=ACCENT, lw=1.4)
        ax.set_yscale("log")
        ax.set_ylim(1e-5, 1)
        ax.set_title(f"{tf}  (n={r.size:,})\nexcess kurtosis "
                     f"{sps.kurtosis(r, bias=False):.2f}", fontsize=10)
        ax.set_xlabel("Standardised log return (σ)")
    axes[0].set_ylabel("Density (log scale)")
    fig.suptitle(f"{symbol}: standardised return distribution vs the normal "
                 f"(red) at four sampling frequencies", fontweight="bold")
    fig.tight_layout()
    return _save(fig, "13_distribution_by_timeframe.png")


def fig_intraday_pattern(symbol: str = "VNINDEX") -> str:
    """Time-of-day structure in 30-minute returns and volatility."""
    d = load_features(f"{symbol}_M30")
    d = d.dropna(subset=["LogReturn_pct"])
    order = catalog.SESSION_BAR_TIMES["M30"]

    g = d.groupby("BarTime")["LogReturn_pct"]
    mean = g.mean().reindex(order)
    sem = g.sem().reindex(order)
    sd = g.std().reindex(order)
    cnt = g.size().reindex(order)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.2))
    colors = [ACCENT if t in ("09:00", "13:00") else LINE for t in order]
    ax1.bar(range(len(order)), mean, yerr=1.96 * sem, color=colors, capsize=3, alpha=0.9)
    ax1.axhline(0, color=NEUTRAL, lw=0.8)
    ax1.set_xticks(range(len(order)))
    ax1.set_xticklabels(order, rotation=45)
    ax1.set_ylabel("Mean log return (%)")
    ax1.set_xlabel("Bar opening time (95% CI)")
    ax1.set_title("Mean 30-minute return by time of day")

    ax2.bar(range(len(order)), sd, color=colors, alpha=0.9)
    ax2.set_xticks(range(len(order)))
    ax2.set_xticklabels(order, rotation=45)
    ax2.set_ylabel("Std. dev. of log return (%)")
    ax2.set_xlabel("Bar opening time")
    ax2.set_title("30-minute return volatility by time of day")

    fig.suptitle(
        f"{symbol} intraday structure, {d['Date'].min():%Y-%m-%d} to "
        f"{d['Date'].max():%Y-%m-%d} ({int(cnt.sum()):,} bars). Red bars span a "
        f"session break (overnight / lunch).", fontweight="bold", fontsize=11)
    fig.tight_layout()
    return _save(fig, "14_intraday_pattern.png")


def build_all() -> list:
    return [
        fig_index_comparison(),
        fig_frequency_scaling(),
        fig_matched_period(),
        fig_return_distributions_by_timeframe(),
        fig_intraday_pattern(),
    ]


if __name__ == "__main__":
    for n in build_all():
        print(f"figures/{n}")
