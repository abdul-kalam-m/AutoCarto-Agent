"""Extended benchmark corpus tests — Blueprint P4-T2/T3/T4.

Covers the four gates (G1, G3a, G4, G5) added to autocarto.benchmark
alongside the pre-existing G2/G3b corpus, plus the two negative-control
scenarios (G3a white_noise, G3b independent) where REJECT is permanently
the correct answer -- there is no proposal fix for "this variable
genuinely has no spatial structure."
"""

from __future__ import annotations

import pytest

from autocarto.benchmark import (
    HAS_COLORSPACIOUS,
    HAS_GEOPANDAS,
    build_report,
    run_gate1_scenarios,
    run_gate3a_scenarios,
    run_gate4_scenarios,
    run_gate5_scenarios,
)


def test_all_six_gates_present_in_corpus():
    report = build_report()
    gates_seen = {s["gate"] for s in report["scenarios"]}
    expected = {"G2", "G3a", "G3b", "G4"}
    if HAS_GEOPANDAS:
        expected.add("G1")
    if HAS_COLORSPACIOUS:
        expected.add("G5")
    assert expected <= gates_seen


def test_corpus_total_reconciles_across_all_gates():
    report = build_report()
    corpus = report["corpus"]
    total = sum(corpus[f"gate{g}_scenarios"] for g in ("1", "2", "3a", "3b", "4", "5"))
    assert total == corpus["total"] == len(report["scenarios"])


@pytest.mark.skipif(not HAS_GEOPANDAS, reason="geopandas not installed")
def test_gate1_geographic_density_correctly_rejected():
    results = run_gate1_scenarios()
    r = next(r for r in results if r["regime"] == "geographic_density")
    assert r["outcome"] == "REJECT"
    assert r["correct"] is True


def test_gate3a_white_noise_is_a_genuine_negative_control():
    """No proposal fix exists for 'this variable has no spatial structure'
    -- REJECT must hold across every seed, not just on average."""
    results = run_gate3a_scenarios()
    noise_results = [r for r in results if r["regime"] == "white_noise"]
    assert len(noise_results) == 3
    assert all(r["outcome"] == "REJECT" for r in noise_results)
    assert all(r["correct"] for r in noise_results)


def test_gate3a_dispersed_and_clustered_both_pass():
    results = run_gate3a_scenarios()
    for regime in ("sar_clustered", "sar_dispersed"):
        regime_results = [r for r in results if r["regime"] == regime]
        assert all(r["outcome"] == "PASS" for r in regime_results), regime
        assert all(r["correct"] for r in regime_results), regime


def test_gate4_web_mercator_rejected_at_both_scales():
    results = run_gate4_scenarios()
    for regime in ("conus_webmerc", "georgia_webmerc"):
        r = next(r for r in results if r["regime"] == regime)
        assert r["outcome"] == "REJECT"
        assert r["correct"] is True


def test_gate4_albers_passes_at_both_scales():
    results = run_gate4_scenarios()
    for regime in ("conus_albers", "georgia_albers"):
        r = next(r for r in results if r["regime"] == regime)
        assert r["outcome"] == "PASS"
        assert r["correct"] is True


@pytest.mark.skipif(not HAS_COLORSPACIOUS, reason="colorspacious not installed")
def test_gate5_diverging_palette_rejected_sequential_passes():
    results = run_gate5_scenarios()
    rdylgn = next(r for r in results if r["regime"] == "rdylgn_diverging")
    ylorrd = next(r for r in results if r["regime"] == "colorbrewer_sequential")
    assert rdylgn["outcome"] == "REJECT" and rdylgn["correct"]
    assert ylorrd["outcome"] == "PASS" and ylorrd["correct"]


def test_g3b_independent_remains_the_documented_free_permutation_miss():
    """This is the one known, disclosed miss in the whole corpus (existed
    before P4-T2) -- assert it stays exactly that, not silently 0 or >1."""
    report = build_report()
    misses = report["summary"]["notable_misses"]
    assert len(misses) == 1
    assert misses[0]["gate"] == "G3b"
    assert misses[0]["regime"] == "independent"


def test_strict_decision_accuracy_is_high_across_the_expanded_corpus():
    report = build_report()
    assert report["summary"]["strict_decision_accuracy"] >= 0.95
