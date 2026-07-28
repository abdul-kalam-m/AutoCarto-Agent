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
    (c) [optional, only when variable_names is passed] a wealth-coded
        variable (income, salary, ...) rendered in a warm/red sequential
        ramp -- a *cartographic convention* flag (Western practice reads
        red as danger/heat/loss), not a perceptual-defect finding like (a)
        and (b). Always reported under its own diagnostic key
        ("semantic_convention_check") so it is never mistaken for one.

On REJECT, prescribes a verified colorblind-safe palette (embedded
ColorBrewer subset) matched to the requested class count -- from
WEALTH_CODED_SAFE_SEQUENTIAL instead of COLORBLIND_SAFE_SEQUENTIAL when a
wealth-coded variable triggered the REJECT, so the replacement satisfies
both constraints at once rather than reopening whichever one it doesn't
address.
"""

from __future__ import annotations

import colorsys
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
#
# PATCH (found 2026-07-27 while building the wealth-coded table below):
# the original 6- and 7-class sequential entries and the 7-class diverging
# entry did NOT themselves pass this gate's own CVD simulation -- i.e. Gate
# 5 could reject a 6/7-class palette and prescribe a "fix" that would fail
# the same check on resubmission, forcing a false non-convergence.
# test_prescribed_replacement_palette_itself_passes existed but only
# exercised a 6-class *diverging* request, which resolves to the n=5 entry
# via _nearest_safe_palette's stable-tie-break in min() (|5-6| == |7-6|, 5
# comes first) -- it never happened to reach the broken n=7 diverging entry.
# 6-class sequential is now a verified ColorBrewer "Reds" sampling; 7-class
# sequential has no verified single-hue ColorBrewer option at this
# delta-E>=10 threshold (single-hue ramps run out of perceptual room under
# CVD simulation above ~5 classes) and is simply omitted, same as this
# table already omits 4/6-class diverging -- _nearest_safe_palette degrades
# to the nearest available count rather than guessing. See
# test_every_safe_palette_table_entry_passes_its_own_gate.
COLORBLIND_SAFE_SEQUENTIAL: Dict[int, List[str]] = {
    3: ["#fee8c8", "#fdbb84", "#e34a33"],
    4: ["#fef0d9", "#fdcc8a", "#fc8d59", "#d7301f"],
    5: ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"],
    6: ["#fff5f0", "#fdcab5", "#fc8a6a", "#f14432", "#bc141a", "#67000d"],
}
COLORBLIND_SAFE_DIVERGING: Dict[int, List[str]] = {
    3: ["#998ec3", "#f7f7f7", "#f1a340"],
    5: ["#5e3c99", "#b2abd2", "#f7f7f7", "#fdb863", "#e66101"],
    7: ["#7f3b08", "#d0730f", "#fdc57f", "#f6f6f7", "#bfbbda", "#70589f", "#2d004b"],
}

# Verified colorblind-safe (same CVD simulation as above) sequential
# palettes in wealth/growth-coded hue families (green/blue/purple), for
# prescribing in place of a warm/red ramp on a wealth-coded variable -- see
# _is_wealth_coded / _dominant_hue_family below. Not one continuous colormap
# resampled per class count: single-hue green/blue/purple ramps that pass
# delta-E>=10 exist at 3-5 classes (ColorBrewer "Greens") but not 6-7, so
# those two entries use a different verified source (BuPu, then viridis
# trimmed to avoid its near-black/near-yellow extremes) -- not literally
# "green," but verified CVD-safe and nowhere near red/orange either.
WEALTH_CODED_SAFE_SEQUENTIAL: Dict[int, List[str]] = {
    3: ["#e5f5e0", "#a1d99b", "#31a354"],
    4: ["#edf8e9", "#bae4b3", "#74c476", "#238b45"],
    5: ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"],
    6: ["#f7fcfd", "#ccddec", "#9ab4d6", "#8c74b5", "#852d90", "#4d004b"],
    7: ["#471365", "#414487", "#2f6c8e", "#21908d", "#2fb47c", "#7ad151", "#dfe318"],
}

# Keyword heuristic for "this variable's plain-language meaning is 'more is
# generally positive'" -- deliberately small and conservative (see
# _is_wealth_coded) to keep false positives rare rather than exhaustive.
WEALTH_CODED_KEYWORDS = frozenset({
    "income", "wealth", "salary", "earnings", "revenue", "worth",
    "savings", "prosperity",
})


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


def _nearest_wealth_safe_palette(n: int) -> List[str]:
    if n in WEALTH_CODED_SAFE_SEQUENTIAL:
        return WEALTH_CODED_SAFE_SEQUENTIAL[n]
    nearest = min(WEALTH_CODED_SAFE_SEQUENTIAL.keys(), key=lambda k: abs(k - n))
    return WEALTH_CODED_SAFE_SEQUENTIAL[nearest]


def _is_wealth_coded(variable_name: str) -> bool:
    """Heuristic on the variable *name*, not its meaning -- see the
    WEALTH_CODED_KEYWORDS comment above for the honesty caveat this implies
    (e.g. 'revenue_at_risk' would still match on 'revenue')."""
    tokens = set(variable_name.lower().replace("-", "_").split("_"))
    return bool(tokens & WEALTH_CODED_KEYWORDS)


def _dominant_hue_family(palette_hex: List[str]) -> Optional[str]:
    """Hue family of a sequential ramp's most-saturated swatch. The pale,
    near-white low-value end of a sequential ramp has low-saturation,
    near-meaningless hue, so the most saturated swatch (typically the
    highest class) is the more reliable signal of what the ramp *reads as*
    at a glance."""
    if not palette_hex:
        return None
    best = max(palette_hex, key=lambda h: colorsys.rgb_to_hsv(*_hex_to_rgb01(h))[1])
    h, s, _v = colorsys.rgb_to_hsv(*_hex_to_rgb01(best))
    if s < 0.15:
        return None  # effectively grayscale -- no strong hue signal either way
    deg = h * 360
    if deg < 20 or deg >= 335:
        return "red"
    if deg < 50:
        return "orange"
    if deg < 70:
        return "yellow"
    if deg < 170:
        return "green"
    if deg < 200:
        return "cyan"
    if deg < 260:
        return "blue"
    if deg < 320:
        return "purple"
    return "pink"


class ColorAccessibilityGate:
    """Gate 5: rejects palettes that collapse under CVD simulation, fail WCAG
    contrast, or (when variable_names is given) code a wealth-like variable
    in a warm/red sequential ramp -- see class docstring above for how the
    third check differs in kind from the first two."""

    def evaluate(
        self,
        palette_hex: List[str],
        text_color_hex: str = "#000000",
        background_color_hex: str = "#ffffff",
        diverging: bool = False,
        variable_names: Optional[List[str]] = None,
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

        # ── Semantic/connotative convention check -- separate in kind from ──
        # the two checks above (see module + class docstrings): a style
        # convention, not a perceptual-defect finding. Only meaningful for a
        # single-hue sequential ramp -- a diverging ramp's red end codes "one
        # pole of a two-sided distribution," not "the bad end of an ordered
        # scale," so red is not obviously miscoded there the way it is for a
        # plain sequential choropleth.
        wealth_coded_vars = [v for v in (variable_names or []) if _is_wealth_coded(v)]
        hue_family = _dominant_hue_family(palette_hex) if not diverging else None
        convention_fail = bool(wealth_coded_vars) and hue_family in ("red", "orange")
        diagnostics["semantic_convention_check"] = {
            "wealth_coded_variables": wealth_coded_vars,
            "dominant_hue_family": hue_family,
            "flagged": convention_fail,
        }

        if cvd_fail or contrast_fail or convention_fail:
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
            if convention_fail:
                reasons.append(
                    f"cartographic convention, not a perceptual defect: "
                    f"{wealth_coded_vars[0]!r} reads as a wealth/prosperity "
                    f"variable but is rendered in a {hue_family}-hued ramp, "
                    f"which Western cartographic convention commonly reads "
                    f"as danger/heat/loss"
                )
            reason_text = "; ".join(reasons)

            prescription_params: Dict[str, Any] = {}
            instruction_parts = []
            if cvd_fail or convention_fail:
                # A wealth-coded replacement satisfies both constraints at
                # once (it is itself CVD-verified, see WEALTH_CODED_SAFE_SEQUENTIAL)
                # rather than fixing one check only to reopen the other on
                # the next mandate iteration.
                if wealth_coded_vars:
                    replacement = _nearest_wealth_safe_palette(n)
                else:
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
