"""Structural tests for the R-2 null-model comparison study.

Full statistical assertions on the underlying SAR draws belong in
tests/gates/test_gate3b_null_model.py (which uses fixed, hand-picked
seeds known to reproduce specific documented outcomes). This file checks
the comparison script's own aggregation logic is self-consistent and
reproducible, not the SAR statistics themselves.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gate3b_null_model_comparison as comparison


def test_comparison_covers_full_benchmark_corpus():
    records = comparison.run_comparison()
    from autocarto.benchmark import GATE3B_REGIMES, GATE3B_SEEDS
    assert len(records) == len(GATE3B_REGIMES) * len(GATE3B_SEEDS)


def test_comparison_is_deterministic():
    r1 = comparison.run_comparison()
    r2 = comparison.run_comparison()
    assert r1 == r2


def test_independent_regime_marked_not_truly_related():
    records = comparison.run_comparison()
    for r in records:
        assert r["truly_related"] == (r["regime"] != "independent")


def test_summary_false_positive_denominator_matches_independent_count():
    records = comparison.run_comparison()
    summary = comparison.summarize(records)
    n_independent = sum(1 for r in records if not r["truly_related"])
    assert summary["false_positives_at_alpha_0.05"]["free_permutation"] <= n_independent
    assert summary["false_positives_at_alpha_0.05"]["toroidal_shift"] <= n_independent


def test_toroidal_never_produces_a_lower_pvalue_than_free_perm_on_average():
    """The whole mechanism's point is a MORE conservative null -- on
    average across the corpus, toroidal p-values should not be smaller."""
    records = comparison.run_comparison()
    free_mean = sum(r["free_permutation_p"] for r in records) / len(records)
    toroidal_mean = sum(r["toroidal_shift_p"] for r in records) / len(records)
    assert toroidal_mean >= free_mean
