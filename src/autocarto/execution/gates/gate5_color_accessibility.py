"""Gate 5: Color-Vision Accessibility.

Approximately 1 in 12 men and 1 in 200 women have some form of color
vision deficiency (CVD), overwhelmingly red-green (deuteranomaly /
protanomaly). A palette that reads as an ordered sequence to the map's
author can collapse into visually indistinguishable classes for a
meaningful fraction of any audience — most catastrophically for the
classic red-yellow-green diverging ramp, whose middle transition is
exactly where deuteranomaly perception collapses (verified empirically:
see tests/gates/test_gate5.py).

Checks (Blueprint §3.4):
    (a) simulate deuteranomaly / protanomaly / tritanomaly (severity=100,
        i.e. the "-anopia" dichromat limit) via colorspacious; require
        minimum CIE CAM02-UCS delta-E between *adjacent* classes under
        every simulation
    (b) WCAG 2.1 contrast ratio >= 4.5:1 for legend/label text against its
        background (hand-rolled per the published W3C formula — this is
        not a color-science computation colorspacious performs)

On REJECT, prescribes a verified colorblind-safe palette (embedded
ColorBrewer subset) matched to the requested class count.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from autocarto.config import THRESHOLDS
from autocarto.contracts import GateResult, Prescription

try:
    import colorspacious as _cs
    HAS_COLORSPACIOUS = True
except ImportError:  # pragma: no cover - exercised only when dep missing
    HAS_COLORSPACIOUS = False

# colorspacious's CVD transform is parametrized by severity (0-100); 100
# is the complete dichromat limit that "deuteranopia/protanopia/tritanopia"
# refer to informally. -anomaly is the library's name for the parametrized
# family; -anopia is not a distinct cvd_type in colorspacious.
CVD_TYPES: Tuple[str, ...] = ("deuteranomaly", "protanomaly", "tritanomaly")
CVD_SEVERITY = 100

# Embedded ColorBrewer subset, verified colorblind-safe (public-domain
# palette *values*; ColorBrewer itself is (c) Cynthia Brewer / Mark Harrower,
# used here as plain numeric data, not redistributed content).
COLORBLIND_SAFE_SEQUENTIAL: Dict[int, List[str]] = {
    3: ["#fee8c8", "#fdbb84", "#e34a33"],
    4: ["#fef0d9", "#fdcc8a", "#fc8d59", "#d7301f"],
    5: ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"],
    6: ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026"],
    7: ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"],
}
COLORBLIND_SAFE_DIVERGING: Dict[int, List[str]] = {
    3: ["#998ec3", "#f7f7f7", "#f1a340"],
    5: ["#5e3c99", "#b2abd2", "#f7f7f7", "#fdb863", "#e66101"],
    7: ["#542788", "#998ec3", "#d8daeb", "#f7f7f7", "#fee0b6", "#f1a340", "#b35806"],
}


def _hex_to_rgb01(hex_color: str) -> List[float]:
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def _relative_luminance(rgb01) -> float:
    """WCAG 2.1 relative luminance (linearized sRGB, ITU-R BT.709 weights)."""
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb01)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _wcag_contrast_ratio(rgb1, rgb2) -> float:
    """WCAG 2.1 contrast ratio: (L_lighter + 0.05) / (L_darker + 0.05)."""
    l1, l2 = _relative_luminance(rgb1), _relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _simulate_cvd(rgb01: List[float], cvd_type: str, severity: int = CVD_SEVERITY) -> List[float]:
    sim = _cs.cspace_convert(
        rgb01, {"name": "sRGB1+CVD", "cvd_type": cvd_type, "severity": severity}, "sRGB1",
    )
    return list(np.clip(np.asarray(sim, dtype=float), 0.0, 1.0))


def _nearest_safe_palette(n: int, diverging: bool = False) -> List[str]:
    table = COLORBLIND_SAFE_DIVERGING if diverging else COLORBLIND_SAFE_SEQUENTIAL
    if n in table:
        return table[n]
    nearest = min(table.keys(), key=lambda k: abs(k - n))
    return table[nearest]


class ColorAccessibilityGate:
    """Gate 5: rejects palettes that collapse under CVD simulation or fail WCAG contrast."""

    def evaluate(
        self,
        palette_hex: List[str],
        text_color_hex: str = "#000000",
        background_color_hex: str = "#ffffff",
        diverging: bool = False,
    ) -> GateResult:
        if not HAS_COLORSPACIOUS:
            # Fail closed (Blueprint §10 failure modes): an accessibility
            # gate that silently no-ops when its dependency is missing is
            # worse than a loud, obvious refusal to render.
            raise RuntimeError(
                "Gate 5 requires the 'colorspacious' package for CVD "
                "simulation; it is not installed. Install it or do not "
                "route color-accessibility-sensitive maps through this "
                "gate — never bypass it silently."
            )

        rgbs = [_hex_to_rgb01(h) for h in palette_hex]
        n = len(rgbs)
        diagnostics: Dict[str, Any] = {"n_classes": n}

        worst_delta_e = float("inf")
        worst_pair: Optional[Tuple[int, int]] = None
        worst_cvd: Optional[str] = None
        per_cvd_min: Dict[str, float] = {}

        for cvd_type in CVD_TYPES:
            sim_rgbs = [_simulate_cvd(r, cvd_type) for r in rgbs]
            min_de_this_type = float("inf")
            for i in range(n - 1):
                de = float(_cs.deltaE(sim_rgbs[i], sim_rgbs[i + 1], input_space="sRGB1"))
                min_de_this_type = min(min_de_this_type, de)
                if de < worst_delta_e:
                    worst_delta_e, worst_pair, worst_cvd = de, (i, i + 1), cvd_type
            per_cvd_min[cvd_type] = round(min_de_this_type, 2)

        diagnostics["min_delta_e_by_cvd_type"] = per_cvd_min
        diagnostics["worst_delta_e"] = round(worst_delta_e, 2) if np.isfinite(worst_delta_e) else None
        diagnostics["worst_cvd_type"] = worst_cvd
        diagnostics["worst_adjacent_pair"] = list(worst_pair) if worst_pair else None

        contrast = _wcag_contrast_ratio(_hex_to_rgb01(text_color_hex), _hex_to_rgb01(background_color_hex))
        diagnostics["text_contrast_ratio"] = round(contrast, 2)

        cvd_fail = n >= 2 and worst_delta_e < THRESHOLDS.gate5.min_delta_e_adjacent_classes
        contrast_fail = contrast < THRESHOLDS.gate5.min_wcag_contrast_ratio

        if cvd_fail or contrast_fail:
            reasons = []
            if cvd_fail:
                reasons.append(
                    f"classes {worst_pair} are perceptually indistinguishable "
                    f"under {worst_cvd} simulation (deltaE={worst_delta_e:.2f} "
                    f"< {THRESHOLDS.gate5.min_delta_e_adjacent_classes})"
                )
            if contrast_fail:
                reasons.append(
                    f"text/background contrast {contrast:.2f}:1 is below WCAG "
                    f"AA {THRESHOLDS.gate5.min_wcag_contrast_ratio}:1"
                )
            reason_text = "; ".join(reasons)

            prescription_params: Dict[str, Any] = {}
            instruction_parts = []
            if cvd_fail:
                replacement = _nearest_safe_palette(n, diverging=diverging)
                prescription_params["palette"] = replacement
                prescription_params["n_classes"] = n
                instruction_parts.append(
                    f"Replace the palette with this verified colorblind-safe "
                    f"{n}-class palette: {replacement}."
                )
            if contrast_fail:
                prescription_params["text_color"] = "#000000"
                instruction_parts.append(
                    "Set label/legend text to #000000 on light backgrounds "
                    "(or #ffffff on dark) to restore WCAG AA contrast."
                )

            return GateResult(
                gate_id="G5",
                decision="REJECT",
                diagnostics=diagnostics,
                instruction=reason_text,
                prescription=Prescription(
                    method="colorblind_safe_palette",
                    instruction=" ".join(instruction_parts),
                    params=prescription_params,
                ),
            )

        return GateResult(gate_id="G5", decision="PASS", diagnostics=diagnostics)
