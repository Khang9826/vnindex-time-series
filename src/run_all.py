"""
Reproducible end-to-end pipeline runner.

    python src/run_all.py            # run every implemented stage
    python src/run_all.py --skip-download   # reuse data/raw/vnindex_raw.csv

Each stage writes its artefacts to results/ and figures/ and prints a short
status line.  Stages that are not implemented yet are listed explicitly so the
execution status of the project is never ambiguous.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402


STAGES_NOT_IMPLEMENTED: list[str] = []


def main() -> int:
    ap = argparse.ArgumentParser(description="VN-Index time-series pipeline")
    ap.add_argument("--refresh-crosscheck", action="store_true",
                    help="re-download the secondary feed instead of using the stored vintage")
    args = ap.parse_args()

    t0 = time.time()
    print("=" * 72)
    print("VN-INDEX TIME-SERIES PIPELINE")
    print("=" * 72)

    # 1 - build canonical raw from the vendored primary source -------------
    import data_loader
    raw, notes = data_loader.build_raw()
    data_loader.save_raw(raw, notes)
    print(f"[1/7] raw build            OK  {len(raw):,} sessions "
          f"{raw['Date'].min().date()} -> {raw['Date'].max().date()} "
          f"(dropped 1 partial bar: {notes['dropped_final_partial_bar']['date']})")

    # 2 - data quality -----------------------------------------------------
    import json

    import data_quality
    raw = data_loader.load_raw()
    report = data_quality.build_report(raw)
    (config.RESULTS_DIR / "data_quality_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"[2/7] data quality         OK  {report['shape']['n_rows']:,} rows, "
          f"{report['duplicates']['n_duplicated_dates']} duplicate dates, "
          f"{report['missing']['rows_with_any_missing']} rows with missing values, "
          f"{report['gap_anomalies']['n_unexplained']} unexplained gaps")

    # 2b - independent corroboration of the primary source -----------------
    import data_crosscheck
    try:
        cc = data_crosscheck.compare(
            raw, data_crosscheck.load_crosscheck(refresh=args.refresh_crosscheck)
        )
        (config.RESULTS_DIR / "source_crosscheck.json").write_text(
            json.dumps(cc, indent=2), encoding="utf-8")
        print(f"[2b/7] source cross-check  OK  corr={cc['close_correlation']:.8f}, "
              f"median |rel diff|={cc['median_abs_rel_diff']:.2e}, "
              f"{cc['n_sessions_only_in_secondary']} sessions missing from primary")
    except Exception as exc:  # network down, stored vintage absent, ...
        print(f"[2b/7] source cross-check  SKIPPED ({type(exc).__name__}: {exc})")

    # 3 - preprocessing ----------------------------------------------------
    import preprocessing
    features = preprocessing.run()
    print(f"[3/7] preprocessing        OK  {len(features):,} sessions, "
          f"{int(features['LogReturn'].notna().sum()):,} returns")

    # 4 - descriptive / EDA ------------------------------------------------
    import analysis
    desc = analysis.descriptive_table(features)
    desc.to_csv(config.RESULTS_DIR / "descriptive_statistics.csv")
    payload = {
        "normality_tests": analysis.normality_tests(features["LogReturn_pct"],
                                                    "Daily log return (%)")
        + analysis.normality_tests(features["SimpleReturn_pct"],
                                   "Daily simple return (%)"),
        "tail_comparison_log_returns": analysis.tail_comparison(features["LogReturn_pct"]),
        "extreme_moves": analysis.extreme_moves(features),
        "day_of_week_effect": analysis.day_of_week_effect(features),
        "month_effect": analysis.month_effect(features),
        "yearly_summary": analysis.yearly_summary(features),
    }
    (config.RESULTS_DIR / "eda_results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    print("[4/7] descriptive / EDA    OK  descriptive_statistics.csv, eda_results.json")

    # 5 - stationarity -----------------------------------------------------
    import stationarity
    suite = stationarity.run_suite(features)
    (config.RESULTS_DIR / "stationarity_tests.json").write_text(
        json.dumps(suite, indent=2), encoding="utf-8")
    stationarity.to_table(suite).to_csv(
        config.RESULTS_DIR / "stationarity_tests.csv", index=False)
    verdicts = {r["series"] + f" [{r['regression']}]": r["verdict"].split(" (")[0]
                for r in suite["tests"]}
    print("[5/7] stationarity         OK")
    for k, v in verdicts.items():
        print(f"        {k:<45} {v}")

    # 6 - autocorrelation + figures ---------------------------------------
    import autocorrelation
    import plots
    figs = plots.build_all(features)
    ac = autocorrelation.run(features)
    (config.RESULTS_DIR / "autocorrelation.json").write_text(
        json.dumps(ac, indent=2), encoding="utf-8")
    import pandas as pd
    pd.DataFrame(ac["ljung_box"]).to_csv(
        config.RESULTS_DIR / "ljung_box_tests.csv", index=False)
    print(f"[6/7] ACF/PACF + figures   OK  {len(figs) + len(ac['figures'])} figures written")

    print("-" * 72)
    print(f"Finished in {time.time() - t0:.1f}s")
    if STAGES_NOT_IMPLEMENTED:
        print("\nNOT IMPLEMENTED YET:")
        for s in STAGES_NOT_IMPLEMENTED:
            print(f"  - {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
