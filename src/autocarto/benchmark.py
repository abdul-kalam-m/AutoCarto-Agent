"""Mini-benchmark: rejection behavior of the deterministic gate suite
against a scripted naive-proposal policy.

Purpose (Fable Review/02_CONFERENCE_PRESENTATION_GUIDE.md §8.2): replace the
unfalsifiable "23% of proposals rejected" poster badge with a number that
regenerates from a fixed, documented corpus by one command:

    autocarto benchmark [--out DIR]      # default DIR = ./benchmarks

The naive policy models an unconstrained LLM's default behavior, matching
what the demo and poster narrate:
  * classification: always propose Fisher-Jenks with quintile-derived breaks;
  * bivariate maps: always propose the bivariate encoding.

Everything is seeded; the report JSON contains no timestamps or timings, so
it is byte-identical across runs. THE RATE IS CORPUS-DEPENDENT — the corpus
composition is embedded in the report and must be quoted alongside the rate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from autocarto.execution.gates.gate2_classification import (
    ClassificationDiagnosticEngine,
    _dedupe_breaks,
)
from autocarto.execution.gates.gate3b_bivariate_correlation import (
    BivariateCorrelationGate,
)
from autocarto.demo import make_grid_polygons, spatial_autoregressive

# ----------------------------------------------------------------------
# Corpus definition (fixed; documented in the report)
# ----------------------------------------------------------------------
N_TRACTS = 243                 # census-tract-scale scenario size (demo convention)
GATE2_SEEDS = [11, 12, 13]     # three independent draws per regime
GATE3B_SEEDS = [21, 22, 23]
GRID_ROWS, GRID_COLS = 16, 16  # queen-contiguity lattice for SAR scenarios
PERMUTATIONS = 199
PERMUTATION_SEED = 7           # matches the demo's Gate-3b seed


def _gen_well_behaved(rng: np.random.Generator) -> np.ndarray:
    return rng.normal(loc=50, scale=12, size=N_TRACTS).clip(0, 100)


def _gen_zero_inflated(rng: np.random.Generator) -> np.ndarray:
    zeros = np.zeros(N_TRACTS // 2)
    tail = rng.pareto(2.0, size=N_TRACTS - len(zeros)) * 5 + 1
    arr = np.concatenate([zeros, tail])
    rng.shuffle(arr)
    return arr


def _gen_heavy_right_skew(rng: np.random.Generator) -> np.ndarray:
    return rng.lognormal(mean=10, sigma=1.2, size=N_TRACTS)


def _gen_discrete_ordinal(rng: np.random.Generator) -> np.ndarray:
    return rng.choice(
        [1, 2, 3, 4, 5], size=N_TRACTS, p=[0.3, 0.3, 0.2, 0.15, 0.05]
    ).astype(float)


def _gen_negative_skew(rng: np.random.Generator) -> np.ndarray:
    return rng.chisquare(df=2, size=N_TRACTS) - 0.8


# Each regime maps to its generator AND the ground-truth expected outcome — the
# whole point of a synthetic corpus is that we KNOW the right decision, so we can
# score the validator's correctness, not just tally rejections.
GATE2_REGIMES = {
    "well_behaved": (_gen_well_behaved, "PASS"),
    "zero_inflated": (_gen_zero_inflated, "REJECT"),
    "heavy_right_skew": (_gen_heavy_right_skew, "REJECT"),
    "discrete_ordinal": (_gen_discrete_ordinal, "REJECT"),
    "negative_right_skew": (_gen_negative_skew, "REJECT"),
}

# Bivariate: strong coupling should be APPROVE'd, independent fields REJECT'd.
# Weak coupling is intentionally borderline (APPROVE or WARN both acceptable),
# so it is excluded from the strict-correctness score but still reported.
GATE3B_REGIMES = {
    "strong_coupling": {"APPROVE"},
    "weak_coupling": {"APPROVE", "WARN"},
    "independent": {"REJECT"},
}


# ----------------------------------------------------------------------
# Naive proposal policy (the scripted "unconstrained LLM")
# ----------------------------------------------------------------------
def naive_classification_proposal(values: np.ndarray) -> Dict[str, Any]:
    """Always Fisher-Jenks with quintile-derived breaks — the demo/poster policy."""
    breaks = [float(np.percentile(values, p)) for p in (0, 20, 40, 60, 80, 100)]
    return {"method": "jenks", "breaks": _dedupe_breaks(breaks)}


# ----------------------------------------------------------------------
# Runners
# ----------------------------------------------------------------------
def run_gate2_scenarios() -> List[Dict[str, Any]]:
    results = []
    for regime, (gen, expected) in GATE2_REGIMES.items():
        for seed in GATE2_SEEDS:
            values = gen(np.random.default_rng(seed))
            proposal = naive_classification_proposal(values)
            engine = ClassificationDiagnosticEngine(random_state=0)
            res = engine.evaluate(
                values,
                proposed_method=proposal["method"],
                proposed_breaks=proposal["breaks"],
            )
            outcome = "PASS" if res.passed else "REJECT"
            results.append({
                "gate": "G2",
                "regime": regime,
                "seed": seed,
                "naive_proposal": proposal["method"],
                "outcome": outcome,
                "expected": expected,
                "correct": outcome == expected,
                "diagnosis": res.diagnosis,
                "gvf": round(res.gvf, 4),
                "prescribed_method": res.prescribed_method,
            })
    return results


def run_gate3b_scenarios() -> List[Dict[str, Any]]:
    _, W, _ = make_grid_polygons(GRID_ROWS, GRID_COLS)
    gate = BivariateCorrelationGate()
    results = []
    for regime, acceptable in GATE3B_REGIMES.items():
        for seed in GATE3B_SEEDS:
            x = spatial_autoregressive(W, rho=0.85, seed=seed * 100 + 1)
            if regime == "strong_coupling":
                y = 0.8 * x + 0.2 * spatial_autoregressive(W, rho=0.85, seed=seed * 100 + 2)
            elif regime == "weak_coupling":
                y = 0.2 * x + spatial_autoregressive(W, rho=0.4, seed=seed * 100 + 2)
            else:  # independent: spatially structured but unrelated
                y = spatial_autoregressive(W, rho=0.85, seed=seed * 100 + 2)
            res = gate.evaluate(
                x, y, W,
                standardized=False,
                permutations=PERMUTATIONS,
                random_state=PERMUTATION_SEED,
            )
            results.append({
                "gate": "G3b",
                "regime": regime,
                "seed": seed,
                "naive_proposal": "bivariate_choropleth",
                "outcome": res.decision,          # APPROVE | WARN | REJECT
                "expected": sorted(acceptable),
                "correct": res.decision in acceptable,
                "bivariate_morans_i": round(res.bivariate_morans_i, 4),
                "bivariate_morans_p": round(res.bivariate_morans_p, 4),
                "spearman_rho": round(res.spearman_rho, 4),
            })
    return results


def build_report() -> Dict[str, Any]:
    g2 = run_gate2_scenarios()
    g3b = run_gate3b_scenarios()
    all_results = g2 + g3b

    n = len(all_results)
    rejected = [r for r in all_results if r["outcome"] == "REJECT"]
    warned = [r for r in all_results if r["outcome"] == "WARN"]

    by_cause: Dict[str, int] = {}
    for r in rejected:
        cause = r.get("diagnosis") or "no_spatial_cross_correlation"
        by_cause[cause] = by_cause.get(cause, 0) + 1

    # Ground-truth classes. "Borderline" (weak coupling) is genuinely ambiguous
    # near the decision thresholds, so it is reported but excluded from the
    # strict accuracy denominator rather than counted for or against the gate.
    should_pass = [r for r in all_results
                   if r["expected"] in ("PASS", ["APPROVE"])]
    should_reject = [r for r in all_results
                     if r["expected"] in ("REJECT", ["REJECT"])]
    borderline = [r for r in all_results
                  if r not in should_pass and r not in should_reject]
    strict = should_pass + should_reject
    strict_correct = [r for r in strict if r["correct"]]

    # Surface any strict miss explicitly — these are scientifically informative,
    # not to be hidden (e.g. spurious cross-correlation of independent SAR fields
    # is the documented free-permutation null-model limitation; see R-2).
    notable_misses = [
        {k: r.get(k) for k in ("gate", "regime", "seed", "outcome", "expected",
                               "diagnosis", "bivariate_morans_i",
                               "bivariate_morans_p", "spearman_rho") if k in r}
        for r in strict if not r["correct"]
    ]

    return {
        "benchmark": "autocarto-mini-benchmark",
        "version": 2,
        "corpus": {
            "description": (
                "Seeded synthetic corpus with KNOWN ground-truth outcomes, so the "
                "validator's DECISION CORRECTNESS can be scored (not just a raw "
                "rejection tally). Deliberately adversarial: 4 of 5 Gate-2 regimes "
                "and 1 of 3 Gate-3b regimes are pathological by construction, so "
                "the rejection rate is high BY DESIGN and is only meaningful "
                "alongside this composition. Gate 2: 5 distribution regimes x 3 "
                "seeds, naive policy = Fisher-Jenks with quintile breaks. Gate 3b: "
                "3 spatial-coupling regimes x 3 seeds on a 16x16 queen lattice, "
                "naive policy = always propose bivariate encoding."
            ),
            "gate2_scenarios": len(g2),
            "gate3b_scenarios": len(g3b),
            "total": n,
            "seeds": {"gate2": GATE2_SEEDS, "gate3b": GATE3B_SEEDS,
                      "permutation": PERMUTATION_SEED},
        },
        "summary": {
            "total_scenarios": n,
            # Headline: decision correctness vs. known truth on unambiguous cases.
            "strict_decision_accuracy": round(len(strict_correct) / len(strict), 4),
            "strict_correct": len(strict_correct),
            "strict_total": len(strict),
            "correct_on_pathological": sum(1 for r in should_reject if r["correct"]),
            "pathological_total": len(should_reject),
            "correct_on_benign": sum(1 for r in should_pass if r["correct"]),
            "benign_total": len(should_pass),
            "borderline_reported_not_scored": len(borderline),
            "notable_misses": notable_misses,
            # Secondary, corpus-dependent: raw rejection tally.
            "rejected": len(rejected),
            "warned": len(warned),
            "passed_or_approved": n - len(rejected) - len(warned),
            "rejection_rate": round(len(rejected) / n, 4),
            "rejections_by_cause": dict(sorted(by_cause.items())),
        },
        "scenarios": all_results,
    }


def main(argv: List[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="autocarto benchmark",
        description="Run the deterministic mini-benchmark and write the report JSON.",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("benchmarks"),
        help="Output directory for the report (default: ./benchmarks)",
    )
    args = parser.parse_args(argv)

    report = build_report()
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / "mini_benchmark_report.json"
    with report_path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    s = report["summary"]
    print(f"scenarios: {s['total_scenarios']} "
          f"({s['borderline_reported_not_scored']} borderline, reported not scored)")
    print(f"strict decision accuracy vs. ground truth: "
          f"{s['strict_correct']}/{s['strict_total']} ({s['strict_decision_accuracy']:.1%})")
    print(f"  correct on benign inputs (expect pass):       {s['correct_on_benign']}/{s['benign_total']}")
    print(f"  correct on pathological inputs (expect reject): {s['correct_on_pathological']}/{s['pathological_total']}")
    for m in s["notable_misses"]:
        print(f"  notable miss: {m['gate']} {m['regime']} seed={m['seed']} "
              f"-> {m['outcome']} (expected {m['expected']})")
    print(f"rejection rate (corpus-dependent): {s['rejected']}/{s['total_scenarios']} "
          f"({s['rejection_rate']:.1%}); warned: {s['warned']}")
    print("rejections by cause:")
    for cause, count in s["rejections_by_cause"].items():
        print(f"  {cause}: {count}")
    print(f"-> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
