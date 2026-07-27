#!/usr/bin/env python3
"""gate3b_null_model_comparison.py — R-2: free permutation vs. toroidal shift.

Runs BOTH null models across the exact same G3b benchmark corpus
(benchmark.py's GATE3B_REGIMES x GATE3B_SEEDS on the 16x16 queen grid) and
reports the compared rejection behavior — the deliverable the manual's R-2
research task asks for ("compare rejection behavior on the benchmark").

This does NOT change Gate 3b's live decision logic (the p-value is not
currently wired into the APPROVE/WARN/REJECT matrix at all, by design --
see gate3b_bivariate_correlation.py). It answers a narrower, honest
question: for the same observed I_xy, how much does the null model change
the *significance* claim, and specifically, does it correct the one
documented false-approval case without weakening genuine-signal detection.

Run:  python scripts/gate3b_null_model_comparison.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from autocarto.benchmark import GATE3B_REGIMES, GATE3B_SEEDS, GRID_COLS, GRID_ROWS
from autocarto.demo import make_grid_polygons, spatial_autoregressive
from autocarto.execution.gates.gate3b_bivariate_correlation import BivariateCorrelationGate

PERMUTATIONS = 999  # higher resolution than the benchmark's own 199, to
                    # resolve near-alpha=0.05 cases precisely (see TD-8's
                    # lesson: coarse permutation counts blur exactly the
                    # boundary this comparison needs to be precise about)
PERMUTATION_SEED = 7


def run_comparison() -> List[Dict[str, Any]]:
    _, W, _ = make_grid_polygons(GRID_ROWS, GRID_COLS)
    gate = BivariateCorrelationGate()
    grid_shape = (GRID_ROWS, GRID_COLS)
    records = []

    for regime, acceptable in GATE3B_REGIMES.items():
        for seed in GATE3B_SEEDS:
            x = spatial_autoregressive(W, rho=0.85, seed=seed * 100 + 1)
            if regime == "strong_coupling":
                y = 0.8 * x + 0.2 * spatial_autoregressive(W, rho=0.85, seed=seed * 100 + 2)
            elif regime == "weak_coupling":
                y = 0.2 * x + spatial_autoregressive(W, rho=0.4, seed=seed * 100 + 2)
            else:  # independent
                y = spatial_autoregressive(W, rho=0.85, seed=seed * 100 + 2)

            free = gate.evaluate(
                x, y, W, standardized=False,
                permutations=PERMUTATIONS, random_state=PERMUTATION_SEED,
            )
            toroidal = gate.evaluate(
                x, y, W, standardized=False,
                permutations=PERMUTATIONS, random_state=PERMUTATION_SEED,
                null_model="toroidal_shift", grid_shape=grid_shape,
            )

            # Ground truth: is this regime's TRUE relationship one where a
            # human would call the p-value "should be significant"?
            truly_related = regime != "independent"

            records.append({
                "regime": regime, "seed": seed,
                "bivariate_morans_i": round(free.bivariate_morans_i, 4),
                "spearman_rho": round(free.spearman_rho, 4),
                "free_permutation_p": round(free.bivariate_morans_p, 4),
                "toroidal_shift_p": round(toroidal.bivariate_morans_p, 4),
                "p_ratio_toroidal_over_free": round(
                    toroidal.bivariate_morans_p / free.bivariate_morans_p, 2
                ) if free.bivariate_morans_p > 0 else None,
                "decision_unchanged": free.decision,  # decision matrix untouched by design
                "truly_related": truly_related,
                "free_perm_significant_at_05": free.bivariate_morans_p < 0.05,
                "toroidal_significant_at_05": toroidal.bivariate_morans_p < 0.05,
            })
    return records


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    # A "false positive" here means: truly unrelated (independent regime),
    # but the null model calls the observed I_xy significant at alpha=0.05.
    false_positives_free = [r for r in records if not r["truly_related"] and r["free_perm_significant_at_05"]]
    false_positives_toroidal = [r for r in records if not r["truly_related"] and r["toroidal_significant_at_05"]]
    # A "false negative" would mean: truly related, but not significant --
    # checks the fix doesn't overcorrect and start missing real signal.
    false_negatives_free = [r for r in records if r["truly_related"] and not r["free_perm_significant_at_05"]]
    false_negatives_toroidal = [r for r in records if r["truly_related"] and not r["toroidal_significant_at_05"]]

    ratios = [r["p_ratio_toroidal_over_free"] for r in records
              if r["p_ratio_toroidal_over_free"] is not None and not r["truly_related"]]

    return {
        "n_scenarios": len(records),
        "false_positives_at_alpha_0.05": {
            "free_permutation": len(false_positives_free),
            "toroidal_shift": len(false_positives_toroidal),
            "improvement": len(false_positives_free) - len(false_positives_toroidal),
        },
        "false_negatives_at_alpha_0.05": {
            "free_permutation": len(false_negatives_free),
            "toroidal_shift": len(false_negatives_toroidal),
            "regression": len(false_negatives_toroidal) - len(false_negatives_free),
        },
        "mean_p_value_inflation_on_independent_regime": (
            round(sum(ratios) / len(ratios), 2) if ratios else None
        ),
        "note": (
            "The decision matrix (APPROVE/WARN/REJECT) is NOT changed by "
            "this comparison -- it currently depends only on |I_xy|/|rho| "
            "magnitude, never on the p-value, by original design. This "
            "study answers a narrower question: does the null model's "
            "significance claim become more honest, without weakening "
            "real-signal detection. Wiring significance into the decision "
            "matrix is a separate, not-yet-made design choice, flagged "
            "here rather than silently applied."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gate 3b null-model comparison (R-2)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output")
    args = parser.parse_args(argv)

    print("Running free-permutation and toroidal-shift null models across "
          f"the G3b benchmark corpus ({len(GATE3B_REGIMES)} regimes x "
          f"{len(GATE3B_SEEDS)} seeds, {PERMUTATIONS} permutations each)...")
    records = run_comparison()
    summary = summarize(records)
    report = {"study": "gate3b-null-model-comparison", "version": 1,
              "permutations": PERMUTATIONS, "summary": summary, "scenarios": records}

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "gate3b_null_model_comparison.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{'regime':16s} {'seed':4s} {'I_xy':>8s} {'free_p':>8s} {'toroidal_p':>10s} {'ratio':>6s}")
    for r in records:
        print(f"{r['regime']:16s} {r['seed']:4d} {r['bivariate_morans_i']:+8.4f} "
              f"{r['free_permutation_p']:8.4f} {r['toroidal_shift_p']:10.4f} "
              f"{str(r['p_ratio_toroidal_over_free']):>6s}")

    fp = summary["false_positives_at_alpha_0.05"]
    fn = summary["false_negatives_at_alpha_0.05"]
    print(f"\nFalse positives (independent regime called significant) at alpha=0.05:")
    print(f"  free_permutation: {fp['free_permutation']}/{sum(1 for r in records if not r['truly_related'])}")
    print(f"  toroidal_shift:   {fp['toroidal_shift']}/{sum(1 for r in records if not r['truly_related'])}")
    print(f"False negatives (related regime called non-significant) at alpha=0.05:")
    print(f"  free_permutation: {fn['free_permutation']}/{sum(1 for r in records if r['truly_related'])}")
    print(f"  toroidal_shift:   {fn['toroidal_shift']}/{sum(1 for r in records if r['truly_related'])}")
    print(f"Mean p-value inflation on independent regime: {summary['mean_p_value_inflation_on_independent_regime']}x")
    print(f"\n-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
