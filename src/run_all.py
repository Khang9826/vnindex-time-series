"""
Reproducible end-to-end pipeline runner.

    python src/run_all.py                    # everything
    python src/run_all.py --headline-only    # only the VN-Index daily deep dive
    python src/run_all.py --refresh-crosscheck   # re-pull the external API vintage

Stage 1-3 cover all 19 catalogued series; stages 4-7 are the VN-Index daily
deep dive; stage 8 is the comparative analysis across the whole dataset.
Each stage prints a short status line, and stages that are not implemented yet
are listed explicitly so the execution status is never ambiguous.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

STAGES_NOT_IMPLEMENTED: list[str] = [
    "ARCH-LM test and GARCH estimation",
    "Chronological train/validation/test split",
    "Forecasting models (naive, moving average, exponential smoothing, ARIMA)",
    "Forecast evaluation against the naive baseline (MAE/RMSE/MAPE/MASE)",
    "Residual diagnostics of fitted models",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="VN-Index time-series pipeline")
    ap.add_argument("--headline-only", action="store_true",
                    help="skip the multi-series stages")
    ap.add_argument("--refresh-crosscheck", action="store_true",
                    help="re-download the external API vintage")
    args = ap.parse_args()

    t0 = time.time()
    print("=" * 78)
    print("VN-INDEX TIME-SERIES PIPELINE")
    print("=" * 78)

    import catalog
    import data_loader
    import data_quality
    import preprocessing

    keys = [catalog.HEADLINE_KEY] if args.headline_only else [s.key for s in catalog.SERIES]

    # 1 - ingest every catalogued series ----------------------------------
    metas = data_loader.build_all(keys)
    trimmed = sum(1 for m in metas.values() if m["trim"].get("applied"))
    total_bars = sum(m["n_rows"] for m in metas.values())
    print(f"[1/8] ingest               OK  {len(metas)} series, {total_bars:,} bars, "
          f"{trimmed} incomplete tails trimmed")

    # 2 - preprocessing ----------------------------------------------------
    feats = preprocessing.build_all(keys)
    print(f"[2/8] preprocessing        OK  {sum(len(f) for f in feats.values()):,} bars, "
          f"{sum(int(f['LogReturn'].notna().sum()) for f in feats.values()):,} returns")

    # 3 - data quality across every series ---------------------------------
    q = {k: data_quality.series_quality(k) for k in keys}
    (config.RESULTS_DIR / "series_quality.json").write_text(
        json.dumps(q, indent=2), encoding="utf-8")
    defects = sum(r["n_duplicate_timestamps"] + r["ohlcv_missing_rows"]
                  + r["non_positive_price"] + r["high_lt_low"]
                  + r["ohlc_inconsistent_bars"] + r["weekend_bars"]
                  for r in q.values())
    print(f"[3/8] data quality         OK  {len(q)} series checked, {defects} defects found")

    # --- headline deep dive ------------------------------------------------
    headline = preprocessing.load_features(catalog.HEADLINE_KEY)
    raw_head = data_loader.load_raw(catalog.HEADLINE_KEY)

    report = data_quality.build_report(raw_head)
    (config.RESULTS_DIR / "data_quality_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    import data_crosscheck
    try:
        cc = data_crosscheck.compare(
            raw_head, data_crosscheck.load_crosscheck(refresh=args.refresh_crosscheck))
        (config.RESULTS_DIR / "source_crosscheck.json").write_text(
            json.dumps(cc, indent=2), encoding="utf-8")
        print(f"[4/8] external crosscheck  OK  corr={cc['close_correlation']:.8f}, "
              f"median |rel diff|={cc['median_abs_rel_diff']:.2e}")
    except Exception as exc:
        print(f"[4/8] external crosscheck  SKIPPED ({type(exc).__name__}: {exc})")

    # 5 - descriptive / EDA -------------------------------------------------
    import analysis
    import pandas as pd
    desc = analysis.descriptive_table(headline)
    desc.to_csv(config.RESULTS_DIR / "descriptive_statistics.csv")
    norm = (analysis.normality_tests(headline["LogReturn_pct"], "Daily log return (%)")
            + analysis.normality_tests(headline["SimpleReturn_pct"], "Daily simple return (%)"))
    pd.DataFrame(norm).to_csv(config.RESULTS_DIR / "normality_tests.csv", index=False)
    payload = {
        "normality_tests": norm,
        "tail_comparison_log_returns": analysis.tail_comparison(headline["LogReturn_pct"]),
        "extreme_moves": analysis.extreme_moves(headline),
        "day_of_week_effect": analysis.day_of_week_effect(headline),
        "month_effect": analysis.month_effect(headline),
        "yearly_summary": analysis.yearly_summary(headline),
    }
    (config.RESULTS_DIR / "eda_results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    print("[5/8] descriptive / EDA    OK  descriptive_statistics.csv, eda_results.json")

    # 6 - stationarity -------------------------------------------------------
    import stationarity
    suite = stationarity.run_suite(headline)
    (config.RESULTS_DIR / "stationarity_tests.json").write_text(
        json.dumps(suite, indent=2), encoding="utf-8")
    stationarity.to_table(suite).to_csv(
        config.RESULTS_DIR / "stationarity_tests.csv", index=False)
    print("[6/8] stationarity         OK")
    for r in suite["tests"]:
        print(f"        [{r['regression']}] {r['series']:<38} "
              f"{r['verdict'].split(' (')[0]}")

    # 7 - autocorrelation + headline figures ---------------------------------
    import autocorrelation
    import plots
    figs = plots.build_all(headline)
    ac = autocorrelation.run(headline)
    (config.RESULTS_DIR / "autocorrelation.json").write_text(
        json.dumps(ac, indent=2), encoding="utf-8")
    pd.DataFrame(ac["ljung_box"]).to_csv(
        config.RESULTS_DIR / "ljung_box_tests.csv", index=False)
    print(f"[7/8] ACF/PACF + figures   OK  {len(figs) + len(ac['figures'])} figures")

    # 8 - comparative analysis across the whole dataset ----------------------
    if args.headline_only:
        print("[8/8] multi-series         SKIPPED (--headline-only)")
    else:
        import multiseries
        import plots_multiseries
        mres = multiseries.run()
        mfigs = plots_multiseries.build_all()
        n_nonstat = sum(1 for s in mres["series"] if s["level_verdict"] == "NON-STATIONARY")
        n_nonnorm = sum(1 for s in mres["series"] if s["jarque_bera"]["reject_normal"])
        print(f"[8/8] multi-series         OK  {len(mres['series'])} series analysed, "
              f"{len(mfigs)} comparative figures")
        print(f"        level non-stationary : {n_nonstat}/{len(mres['series'])}")
        print(f"        returns non-normal   : {n_nonnorm}/{len(mres['series'])}")

    print("-" * 78)
    print(f"Finished in {time.time() - t0:.1f}s")
    if STAGES_NOT_IMPLEMENTED:
        print("\nNOT IMPLEMENTED YET:")
        for s in STAGES_NOT_IMPLEMENTED:
            print(f"  - {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
