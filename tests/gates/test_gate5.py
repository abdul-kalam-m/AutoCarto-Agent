"""Gate 5 (color-vision accessibility) behavioral tests — Blueprint §3.4."""

from __future__ import annotations

import pytest

colorspacious = pytest.importorskip("colorspacious")

from autocarto.execution.gates.gate5_color_accessibility import ColorAccessibilityGate

YLORRD_SEQUENTIAL = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
RDYLGN_DIVERGING = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#91cf60", "#1a9850"]


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
