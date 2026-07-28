"""Gate 5 (color-vision accessibility) behavioral tests — Blueprint §3.4."""

from __future__ import annotations

import pytest

colorspacious = pytest.importorskip("colorspacious")

from autocarto.execution.gates.gate5_color_accessibility import (
    COLORBLIND_SAFE_DIVERGING,
    COLORBLIND_SAFE_SEQUENTIAL,
    WEALTH_CODED_SAFE_SEQUENTIAL,
    ColorAccessibilityGate,
)

YLORRD_SEQUENTIAL = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
RDYLGN_DIVERGING = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#91cf60", "#1a9850"]
GREENS_SEQUENTIAL = ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"]


def test_colorbrewer_ylorrd_passes():
    res = ColorAccessibilityGate().evaluate(YLORRD_SEQUENTIAL)
    assert res.decision == "PASS"


def test_redgreen_diverging_ramp_rejected_under_deuteranomaly():
    # The classic RdYlGn ramp collapses at its yellow-green transition for
    # red-green colorblind viewers — this is the textbook accessibility
    # failure Gate 5 exists to catch.
    res = ColorAccessibilityGate().evaluate(RDYLGN_DIVERGING, diverging=True)
    assert res.decision == "REJECT"
    assert res.diagnostics["worst_cvd_type"] in {"deuteranomaly", "protanomaly"}
    assert res.diagnostics["worst_delta_e"] < 2.0
    assert res.prescription.method == "colorblind_safe_palette"
    # The embedded table only has 3/5/7-class diverging palettes; a 6-class
    # request gets the nearest available count, not an exact match.
    assert len(res.prescription.params["palette"]) in {5, 7}


def test_low_contrast_text_rejected():
    res = ColorAccessibilityGate().evaluate(
        YLORRD_SEQUENTIAL, text_color_hex="#cccccc", background_color_hex="#ffffff",
    )
    assert res.decision == "REJECT"
    assert res.diagnostics["text_contrast_ratio"] < 4.5


def test_black_on_white_passes_contrast():
    res = ColorAccessibilityGate().evaluate(
        YLORRD_SEQUENTIAL, text_color_hex="#000000", background_color_hex="#ffffff",
    )
    assert res.decision == "PASS"
    assert res.diagnostics["text_contrast_ratio"] > 4.5


def test_prescribed_replacement_palette_itself_passes():
    """The gate's own prescription must not be self-rejecting."""
    res = ColorAccessibilityGate().evaluate(RDYLGN_DIVERGING, diverging=True)
    replacement = res.prescription.params["palette"]
    res2 = ColorAccessibilityGate().evaluate(replacement, diverging=True)
    assert res2.decision == "PASS"


def test_every_safe_palette_table_entry_passes_its_own_gate():
    """Every embedded 'verified colorblind-safe' entry must independently
    pass this gate's own CVD simulation -- not just whichever entry a
    specific class-count lookup happens to resolve to.

    A real gap: test_prescribed_replacement_palette_itself_passes above only
    ever exercises a 6-class *diverging* request, which _nearest_safe_palette
    resolves to the n=5 entry (min()'s stable tie-break picks the
    first-seen of two equally-near keys {5, 7} for a distance-1 tie) --
    so the n=7 diverging entry was never actually exercised by any test,
    and turned out to be broken (see the PATCH comment on
    COLORBLIND_SAFE_SEQUENTIAL). This test checks every entry in every
    table directly, so a similar future regression can't hide the same way.
    """
    gate = ColorAccessibilityGate()
    for n, hexes in COLORBLIND_SAFE_SEQUENTIAL.items():
        res = gate.evaluate(hexes, diverging=False)
        assert res.decision == "PASS", f"COLORBLIND_SAFE_SEQUENTIAL[{n}] fails its own gate"
    for n, hexes in COLORBLIND_SAFE_DIVERGING.items():
        res = gate.evaluate(hexes, diverging=True)
        assert res.decision == "PASS", f"COLORBLIND_SAFE_DIVERGING[{n}] fails its own gate"
    for n, hexes in WEALTH_CODED_SAFE_SEQUENTIAL.items():
        res = gate.evaluate(hexes, diverging=False)
        assert res.decision == "PASS", f"WEALTH_CODED_SAFE_SEQUENTIAL[{n}] fails its own gate"


# ── Semantic/connotative palette-family convention check ────────────────────
# A real user's finding: a median-household-income choropleth used YlOrRd
# (yellow-orange-red), which Western cartographic convention commonly reads
# as danger/heat/loss -- an odd signal for "high income." Distinct in kind
# from the CVD/contrast checks above (see module docstring): a style
# convention, not a perceptual defect, so it is deliberately scoped to only
# ever fire when variable_names is explicitly passed (existing callers that
# never pass it get exactly their old behavior -- see the tests above, all
# unchanged and still passing).

def test_wealth_coded_variable_in_red_ramp_is_rejected():
    res = ColorAccessibilityGate().evaluate(
        YLORRD_SEQUENTIAL, diverging=False, variable_names=["median_household_income"],
    )
    assert res.decision == "REJECT"
    check = res.diagnostics["semantic_convention_check"]
    assert check["flagged"] is True
    assert check["wealth_coded_variables"] == ["median_household_income"]
    assert check["dominant_hue_family"] in ("red", "orange")
    assert "not a perceptual defect" in res.instruction
    assert res.prescription.params["palette"] in WEALTH_CODED_SAFE_SEQUENTIAL.values()


def test_wealth_coded_variable_in_green_ramp_passes():
    res = ColorAccessibilityGate().evaluate(
        GREENS_SEQUENTIAL, diverging=False, variable_names=["median_household_income"],
    )
    assert res.decision == "PASS"
    assert res.diagnostics["semantic_convention_check"]["flagged"] is False


def test_non_wealth_variable_in_red_ramp_not_flagged_by_convention_check():
    """A red ramp for a rate/risk variable (asthma prevalence) is a normal,
    unremarkable coding -- the convention check must not false-positive on
    every red palette, only ones applied to a wealth-coded variable name."""
    res = ColorAccessibilityGate().evaluate(
        YLORRD_SEQUENTIAL, diverging=False, variable_names=["asthma_prevalence"],
    )
    assert res.diagnostics["semantic_convention_check"]["flagged"] is False
    assert res.diagnostics["semantic_convention_check"]["wealth_coded_variables"] == []
    assert res.decision == "PASS"


def test_convention_check_skipped_for_diverging_palettes():
    """A diverging ramp's red end codes one pole of a two-sided distribution,
    not 'the bad end of an ordered scale' -- not obviously miscoded the way
    a sequential ramp's red end is, so this check is scoped to sequential
    (diverging=False) only."""
    res = ColorAccessibilityGate().evaluate(
        RDYLGN_DIVERGING, diverging=True, variable_names=["median_household_income"],
    )
    assert res.diagnostics["semantic_convention_check"]["flagged"] is False
    assert res.diagnostics["semantic_convention_check"]["dominant_hue_family"] is None


def test_convention_check_absent_variable_names_is_backward_compatible():
    """Every pre-existing call site that never passes variable_names (the
    default) must see exactly the old behavior -- no new REJECTs appear out
    of nowhere for callers that opted into nothing."""
    res = ColorAccessibilityGate().evaluate(YLORRD_SEQUENTIAL, diverging=False)
    assert res.decision == "PASS"
    assert res.diagnostics["semantic_convention_check"]["flagged"] is False
    assert res.diagnostics["semantic_convention_check"]["wealth_coded_variables"] == []


def test_prescribed_wealth_replacement_itself_passes_both_checks():
    """The wealth-coded prescription must be self-consistent under re-
    evaluation: not just CVD-safe (already covered generically above by
    test_every_safe_palette_table_entry_passes_its_own_gate), but also no
    longer flagged by the convention check that triggered the REJECT."""
    res = ColorAccessibilityGate().evaluate(
        YLORRD_SEQUENTIAL, diverging=False, variable_names=["median_household_income"],
    )
    replacement = res.prescription.params["palette"]
    res2 = ColorAccessibilityGate().evaluate(
        replacement, diverging=False, variable_names=["median_household_income"],
    )
    assert res2.decision == "PASS"
