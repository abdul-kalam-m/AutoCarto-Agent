#!/usr/bin/env python3
"""gen_ungated_vs_gated.py — CartoLLM figure F-NEW-1 ("the beautiful wrong map").

The single highest-leverage poster/talk visual (Fable Review/
02_CONFERENCE_PRESENTATION_GUIDE.md §5.2): the SAME Atlanta variable rendered
two ways.

  LEFT  (ungated)  — a naive LLM default: equal-interval class breaks + a
                     rainbow (jet) ramp. On a right-skewed variable equal
                     interval collapses most tracts into one class, so the map
                     is a flat wash; the jet ramp is not colour-vision safe.
  RIGHT (gated)    — the AutoCarto-Agent output: Gate 2 diagnoses the skew and
                     prescribes a log-transform + Jenks classification with
                     balanced classes on a colour-blind-safe sequential ramp.

Every number on the figure is COMPUTED from the real pipeline (Gate 2 on the
pinned 530-tract snapshot), not asserted.

Honesty notes carried onto the figure:
  * Gate 2 (classification) is implemented and computed here.
  * Gate 5 (colour) is specified, not yet automated — the unsafe/safe ramps are
    shown to illustrate the failure it targets, and labelled as such.
  * GVF is deliberately NOT the headline: equal-interval actually scores a
    slightly HIGHER GVF here while producing a worse map, because it isolates a
    few outliers into their own classes. The honest failure metric is class
    balance / legibility, which is what the figure shows.

Usage:
    python scripts/gen_ungated_vs_gated.py [--out DIR] [--live]
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import FancyBboxPatch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)

from _atlanta_case import build_atlanta_case
from autocarto.execution.gates.gate2_classification import (
    ClassificationDiagnosticEngine,
    _dedupe_breaks,
)

_parser = argparse.ArgumentParser(description="CartoLLM ungated-vs-gated figure")
_parser.add_argument("--out", default=os.path.join(REPO_ROOT, "output", "figures"))
_parser.add_argument("--live", action="store_true",
                     help="Query TIGERweb instead of the pinned snapshot")
_args = _parser.parse_args()
os.makedirs(_args.out, exist_ok=True)

mpl.rcParams.update({
    "font.family": "DejaVu Sans",
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "savefig.dpi": 300,
})

# ── Palette ───────────────────────────────────────────────────────────────────
C_BAD = "#c0392b"      # ungated / violation red
C_GOOD = "#1e8449"     # gated / pass green
C_INK = "#1a1a2e"
C_MUTE = "#666666"

# ── 1. Data + classifications (all computed) ──────────────────────────────────
print("Building Atlanta case (530 tracts, seeded SAR variable) …")
case = build_atlanta_case(live=_args.live)
gdf = case.gdf.to_crs(epsg=4326)
v = case.tree_canopy
n = case.n

# Naive equal-interval, 5 classes.
lo, hi = float(v.min()), float(v.max())
naive_breaks = [lo + (hi - lo) * k / 5 for k in range(6)]

# Gate 2 prescription (diagnosis-driven).
engine = ClassificationDiagnosticEngine(random_state=0)
res = engine.evaluate(v, proposed_method="jenks")
gated_breaks = _dedupe_breaks([float(b) for b in res.prescribed_breaks])

def _class_counts(values, breaks):
    cls = np.digitize(values, breaks[1:-1])
    return [int((cls == k).sum()) for k in range(len(breaks) - 1)]

naive_counts = _class_counts(v, naive_breaks)
gated_counts = _class_counts(v, gated_breaks)
naive_top_share = 100.0 * max(naive_counts) / n
gvf_naive = ClassificationDiagnosticEngine._compute_gvf(v, naive_breaks)
gvf_gated = ClassificationDiagnosticEngine._compute_gvf(v, gated_breaks)

print(f"  naive equal-interval counts : {naive_counts}  (top class {naive_top_share:.0f}%)")
print(f"  gated log+Jenks counts      : {gated_counts}")
print(f"  GVF naive={gvf_naive:.3f}  gated={gvf_gated:.3f}  (GVF is NOT the headline; see docstring)")

# ── 2. Figure scaffold ────────────────────────────────────────────────────────
fig = plt.figure(figsize=(13.5, 9.0), facecolor="white")
gs = fig.add_gridspec(
    2, 2, height_ratios=[3.0, 1.0],
    left=0.05, right=0.985, top=0.855, bottom=0.145, hspace=0.42, wspace=0.03,
)
ax_l = fig.add_subplot(gs[0, 0])
ax_r = fig.add_subplot(gs[0, 1])
ax_h = fig.add_subplot(gs[1, :])


def _discrete(cmap_name, n_cls, breaks):
    base = mpl.colormaps[cmap_name].resampled(n_cls)
    cmap = ListedColormap([base(i / max(n_cls - 1, 1)) for i in range(n_cls)])
    return cmap, BoundaryNorm(breaks, cmap.N)


def _draw_map(ax, breaks, cmap_name):
    cmap, norm = _discrete(cmap_name, len(breaks) - 1, breaks)
    gdf.plot(column=v, ax=ax, cmap=cmap, norm=norm,
             linewidth=0.12, edgecolor="#ffffff", zorder=2)
    gdf.dissolve(by="COUNTY").boundary.plot(
        ax=ax, linewidth=0.6, edgecolor="#555555", zorder=3)
    ax.set_axis_off()


def _callout(ax, x, y, text, accent, mark):
    """A coloured violation/pass badge inside a map axes (axes fraction coords)."""
    ax.text(
        x, y, f"{mark}  {text}", transform=ax.transAxes,
        fontsize=8.0, va="top", ha="left", color=C_INK, wrap=True,
        bbox=dict(boxstyle="round,pad=0.45", fc="white", ec=accent, lw=1.2, alpha=0.94),
        zorder=6,
    )


# Column headers (placed in figure space to avoid colliding with the tall map axes).
fig.text(0.28, 0.885, "UNGATED", ha="center", va="bottom",
         fontsize=15, fontweight="bold", color=C_BAD)
fig.text(0.28, 0.868, "naïve LLM output", ha="center", va="bottom",
         fontsize=9.5, color=C_MUTE, style="italic")
fig.text(0.755, 0.885, "GATED", ha="center", va="bottom",
         fontsize=15, fontweight="bold", color=C_GOOD)
fig.text(0.755, 0.868, "AutoCarto-Agent output", ha="center", va="bottom",
         fontsize=9.5, color=C_MUTE, style="italic")

# ── 3. Left (ungated) ─────────────────────────────────────────────────────────
_draw_map(ax_l, naive_breaks, "jet")
_callout(ax_l, 0.005, 0.185,
         f"Equal-interval breaks: {max(naive_counts)}/{n} tracts "
         f"({naive_top_share:.0f}%) collapse into one class —\nspatial variation is hidden."
         "   [Gate 2]", C_BAD, "✗")
_callout(ax_l, 0.005, 0.065,
         "Rainbow (jet) ramp: non-monotonic lightness,\nunreadable under red–green CVD."
         "   [Gate 5, specified]", C_BAD, "✗")

# ── 4. Right (gated) ──────────────────────────────────────────────────────────
_draw_map(ax_r, gated_breaks, "YlOrBr")
_callout(ax_r, 0.005, 0.185,
         "Gate 2 → log-transform + Jenks: "
         f"{len(gated_counts)} balanced classes\n[{'/'.join(map(str, gated_counts))}] — "
         "spatial structure revealed.   [Gate 2 ✓]", C_GOOD, "✓")
_callout(ax_r, 0.005, 0.065,
         "ColorBrewer YlOrBr sequential —\nperceptually ordered, colour-blind safe."
         "   [Gate 5, specified]", C_GOOD, "✓")

# ── 5. Histogram strip: WHY the breaks matter ────────────────────────────────
ax_h.hist(v, bins=44, color="#b8c4d0", edgecolor="white", linewidth=0.4, zorder=1)
for b in naive_breaks[1:-1]:
    ax_h.axvline(b, color=C_BAD, ls=(0, (4, 3)), lw=1.4, zorder=3)
for b in gated_breaks[1:-1]:
    ax_h.axvline(b, color=C_GOOD, ls="-", lw=1.6, zorder=4)
ax_h.set_xlim(0, hi * 1.01)
ax_h.set_xlabel("Tree-canopy loss (%)", fontsize=9)
ax_h.set_ylabel("tracts", fontsize=9)
ax_h.tick_params(labelsize=8)
for sp in ("top", "right"):
    ax_h.spines[sp].set_visible(False)

# legend + explanatory line
from matplotlib.lines import Line2D
ax_h.set_title(
    "Why the breaks matter: equal-interval spacing wastes classes on the sparse tail; "
    "Gate 2 places breaks where the tracts actually are",
    fontsize=9, color=C_MUTE, style="italic", pad=6,
)
ax_h.legend(
    handles=[
        Line2D([0], [0], color=C_BAD, ls=(0, (4, 3)), lw=1.6, label="equal-interval breaks (evenly spaced → upper classes empty)"),
        Line2D([0], [0], color=C_GOOD, ls="-", lw=1.8, label="Gate 2 log+Jenks breaks (placed where the data lie)"),
    ],
    loc="upper right", fontsize=8.2, frameon=False,
)

# ── 6. Title + footnote ───────────────────────────────────────────────────────
fig.text(0.5, 0.975, "Same data, same tracts — why deterministic validation matters",
         ha="center", va="top", fontsize=16, fontweight="bold", color=C_INK)
fig.text(0.5, 0.935,
         "Atlanta metro · 530 Fulton + DeKalb census tracts · real TIGER geometry · tree-canopy-loss (seeded SAR variable)",
         ha="center", va="top", fontsize=9.5, color=C_MUTE)
fig.text(0.5, 0.040,
         "Gate 2 (classification) is implemented and computed on this figure. Gate 5 (colour) is specified in the roadmap — "
         "ramps shown to illustrate the failure it targets.",
         ha="center", va="bottom", fontsize=7.4, color="#8a8a8a")
fig.text(0.5, 0.020,
         "GVF is deliberately not the score here: equal-interval attains a comparable GVF "
         f"({gvf_naive:.2f} vs {gvf_gated:.2f}) yet hides the pattern, so class balance is the honest metric.",
         ha="center", va="bottom", fontsize=7.4, color="#8a8a8a")

# ── 7. Save ───────────────────────────────────────────────────────────────────
png = os.path.join(_args.out, "ungated_vs_gated.png")
pdf = os.path.join(_args.out, "ungated_vs_gated.pdf")
fig.savefig(png, dpi=300, facecolor="white")
fig.savefig(pdf, facecolor="white")
plt.close(fig)
print(f"✓ PNG → {png}")
print(f"✓ PDF → {pdf}")
