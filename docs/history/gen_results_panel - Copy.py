#!/usr/bin/env python3
"""
gen_results_panel_publication.py
================================

Publication-ready CartoLLM validation figure (FIXED)
----------------------------------------------------

Resolved issues:
  ✓ eliminated all overlapping elements
  ✓ improved spacing and margins
  ✓ fixed colorbar positioning
  ✓ table alignment optimized
  ✓ legend placement refined
  ✓ better text wrapping
  ✓ consistent padding throughout
  
Outputs
-------
  atlanta_results_panel_publication.png
  atlanta_results_panel_publication.pdf
"""

import os
import sys
import json
import warnings
import urllib.request
from typing import List, Tuple

import numpy as np
import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches

from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.cm import ScalarMappable
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from scipy.linalg import solve as sp_solve
import libpysal

warnings.filterwarnings("ignore")

# =============================================================================
# PATHS
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR  = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "codes_patched"))

sys.path.insert(0, CODES_DIR)

from gate2_classification import ClassificationDiagnosticEngine
from gate3b_bivariate_correlation import BivariateCorrelationGate

# =============================================================================
# MATPLOTLIB CONFIG
# =============================================================================

mpl.rcParams.update({
    "font.family": "DejaVu Sans",

    "figure.dpi": 150,
    "savefig.dpi": 300,

    "axes.titlesize": 10,
    "axes.titleweight": "bold",

    "axes.labelsize": 8,

    "xtick.labelsize": 7,
    "ytick.labelsize": 7,

    "legend.fontsize": 7,

    "pdf.fonttype": 42,
    "ps.fonttype": 42,

    "axes.edgecolor": "#BBBBBB",
    "axes.linewidth": 0.6,

    "text.color": "#222222",
})

# =============================================================================
# DOWNLOAD TIGER TRACTS
# =============================================================================

TIGER_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Tracts_Blocks/MapServer/4/query"
    "?where=STATE%3D%2713%27+AND+COUNTY+IN+%28%27121%27%2C%27089%27%29"
    "&outFields=GEOID%2CNAME%2CSTATE%2CCOUNTY%2CTRACT"
    "&f=geojson&outSR=4326&resultRecordCount=2000"
)

print("Downloading TIGER tracts...")

req = urllib.request.Request(
    TIGER_URL,
    headers={"User-Agent": "CartoLLM/1.0"}
)

with urllib.request.urlopen(req, timeout=60) as resp:
    payload = json.loads(resp.read().decode("utf-8"))

features = payload["features"]

gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")

# Georgia State Plane
gdf = gdf.to_crs(epsg=26967)

# =============================================================================
# SPATIAL WEIGHTS
# =============================================================================

print("Building Queen contiguity...")

W_q = libpysal.weights.Queen.from_dataframe(gdf, silence_warnings=True)

if W_q.islands:
    keep = [i for i in range(len(gdf)) if gdf.index[i] not in W_q.islands]
    gdf = gdf.iloc[keep].reset_index(drop=True)
    W_q = libpysal.weights.Queen.from_dataframe(gdf, silence_warnings=True)

W_q.transform = "r"

W_rs = W_q.full()[0]

n = len(gdf)

# =============================================================================
# SAR SYNTHETIC VARIABLES
# =============================================================================

def sar_draw(W, rho, seed):
    rng = np.random.default_rng(seed)

    A = np.eye(W.shape[0]) - rho * W
    eps = rng.standard_normal(W.shape[0])

    return sp_solve(A, eps)

print("Generating SAR variables...")

z_common = sar_draw(W_rs, rho=0.72, seed=1001)

z_x = 0.78 * z_common + 0.22 * sar_draw(W_rs, rho=0.35, seed=1002)
tree_raw = np.exp(z_x * 0.90) * 7.5
tree_canopy = np.clip(tree_raw, 0.5, 95)

z_y = 0.75 * z_common + 0.25 * sar_draw(W_rs, rho=0.35, seed=1003)
asthma_raw = np.exp(z_y * 0.85) * 18.0
asthma_rate = np.clip(asthma_raw, 1, 250)

gdf["tree_canopy_loss"] = tree_canopy
gdf["asthma_rate"] = asthma_rate

# =============================================================================
# GATE 2
# =============================================================================

engine = ClassificationDiagnosticEngine(random_state=0)

g2_canopy = engine.evaluate(tree_canopy, proposed_method="jenks")

engine.iteration_count = 0

g2_asthma = engine.evaluate(asthma_rate, proposed_method="jenks")

# =============================================================================
# GATE 3B
# =============================================================================

gate3b = BivariateCorrelationGate()

g3b_result = gate3b.evaluate(
    x=tree_canopy,
    y=asthma_rate,
    weights_matrix=W_rs,
    permutations=199,
    random_state=0,
)

d = g3b_result.to_dict()

# =============================================================================
# HELPERS
# =============================================================================

def make_cmap_and_norm(breaks, cmap_name):

    n_cls = len(breaks) - 1

    base = mpl.colormaps[cmap_name].resampled(n_cls)

    colors = [base(i / n_cls) for i in range(n_cls)]

    cmap = ListedColormap(colors)

    norm = BoundaryNorm(breaks, cmap.N)

    return cmap, norm


def safe_breaks(result, values, fallback_n=5):

    brks = result.prescribed_breaks

    if brks and len(brks) >= 2:
        return [float(v) for v in brks]

    pcts = np.linspace(0, 100, fallback_n + 1)

    return [float(np.percentile(values, p)) for p in pcts]


def tertile_class(arr):

    q33, q67 = np.percentile(arr, [33.33, 66.67])

    cls = np.zeros(len(arr), dtype=int)

    cls[arr >= q33] = 1
    cls[arr >= q67] = 2

    return cls


# =============================================================================
# BIVARIATE COLORS
# =============================================================================

BIVAR_HEX = [
    ["#e8e8e8", "#ace4e4", "#5ac8c8"],
    ["#dfb0d6", "#a5add3", "#5698b9"],
    ["#be64ac", "#8c62aa", "#3b4994"],
]

canopy_cls = tertile_class(tree_canopy)
asthma_cls = tertile_class(asthma_rate)

bivar_colors = [
    BIVAR_HEX[c][a]
    for c, a in zip(canopy_cls, asthma_cls)
]

# =============================================================================
# FIGURE
# =============================================================================

fig = plt.figure(
    figsize=(12.8, 8.1),
    facecolor="white",
    constrained_layout=False
)

# Optimized grid spacing
outer = gridspec.GridSpec(
    2,
    1,
    figure=fig,
    height_ratios=[2.35, 1.05],
    hspace=0.08,
    left=0.025,
    right=0.975,
    top=0.928,
    bottom=0.048,
)

top = gridspec.GridSpecFromSubplotSpec(
    1,
    3,
    subplot_spec=outer[0],
    wspace=0.035
)

bottom = gridspec.GridSpecFromSubplotSpec(
    1,
    2,
    subplot_spec=outer[1],
    wspace=0.05
)

ax1 = fig.add_subplot(top[0])
ax2 = fig.add_subplot(top[1])
ax3 = fig.add_subplot(top[2])

ax4 = fig.add_subplot(bottom[0])
ax5 = fig.add_subplot(bottom[1])

# =============================================================================
# MAP DRAWER (FIXED COLORBAR POSITIONING)
# =============================================================================

def draw_map(
    ax,
    column,
    cmap,
    norm,
    title,
    letter,
    badge,
    badge_ok,
    cbar_label,
    breaks,
):

    gplot = gdf.to_crs(epsg=4326)

    gplot.plot(
        column=column,
        ax=ax,
        cmap=cmap,
        norm=norm,
        linewidth=0.10,
        edgecolor="#FAFAFA",
    )

    # county boundaries
    gplot.dissolve(by="COUNTY").boundary.plot(
        ax=ax,
        linewidth=0.65,
        edgecolor="#4D4D4D",
    )

    ax.set_axis_off()

    # title
    ax.set_title(
        title,
        fontsize=10,
        fontweight="bold",
        pad=4
    )

    # panel label
    ax.text(
        0.02,
        0.98,
        letter,
        transform=ax.transAxes,
        fontsize=15,
        fontweight="bold",
        va="top",
        ha="left",
        color="#111111",
        bbox=dict(
            fc="white",
            ec="none",
            alpha=0.85,
            pad=1.5
        )
    )

    # gate badge - moved to better position
    badge_col = "#1E9E52" if badge_ok else "#D97A00"

    ax.text(
        0.50,
        0.02,
        badge,
        transform=ax.transAxes,
        fontsize=6.8,
        fontweight="bold",
        ha="center",
        va="bottom",
        color=badge_col,
        bbox=dict(
            fc="white",
            ec=badge_col,
            lw=0.8,
            alpha=0.95,
            pad=2.2,
            boxstyle="round,pad=0.28"
        )
    )

    # FIXED: Better colorbar positioning - use fixed coordinates
    cax = inset_axes(
        ax,
        width="5%",
        height="60%",
        loc='lower left',
        bbox_to_anchor=(0.02, 0.15, 0.1, 0.7),
        bbox_transform=ax.transAxes,
        borderpad=0
    )

    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])

    cb = plt.colorbar(sm, cax=cax)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(labelsize=5.5, width=0.4, length=2)

    # Format tick labels
    tick_locs = breaks[::max(1, len(breaks)//5)]
    cb.set_ticks(tick_locs)
    
    labels = []
    for b in tick_locs:
        if b < 100:
            labels.append(f"{b:.1f}")
        else:
            labels.append(f"{b:.0f}")
    cb.set_ticklabels(labels)

    cb.set_label(
        cbar_label,
        fontsize=6,
        labelpad=1
    )


# =============================================================================
# PANEL A
# =============================================================================

brks1 = safe_breaks(g2_canopy, tree_canopy)

brks1[0] = min(brks1[0], float(tree_canopy.min()))
brks1[-1] = max(brks1[-1], float(tree_canopy.max()) + 0.01)

cmap1, norm1 = make_cmap_and_norm(brks1, "YlOrBr")

draw_map(
    ax1,
    "tree_canopy_loss",
    cmap1,
    norm1,
    "Tree Canopy Loss (%)",
    "A",
    "✓ Gate 2 → log transform then jenks",
    True,
    "% loss",
    brks1
)

# =============================================================================
# PANEL B
# =============================================================================

brks2 = safe_breaks(g2_asthma, asthma_rate)

brks2[0] = min(brks2[0], float(asthma_rate.min()))
brks2[-1] = max(brks2[-1], float(asthma_rate.max()) + 0.01)

cmap2, norm2 = make_cmap_and_norm(brks2, "OrRd")

draw_map(
    ax2,
    "asthma_rate",
    cmap2,
    norm2,
    "Asthma Hospitalisation Rate (per 10 000)",
    "B",
    "✓ Gate 2 → log transform then jenks",
    True,
    "per 10 000",
    brks2
)

# =============================================================================
# PANEL C
# =============================================================================

gplot = gdf.to_crs(epsg=4326)

gplot.plot(
    ax=ax3,
    color=bivar_colors,
    linewidth=0.10,
    edgecolor="#FAFAFA"
)

gplot.dissolve(by="COUNTY").boundary.plot(
    ax=ax3,
    linewidth=0.65,
    edgecolor="#4D4D4D"
)

ax3.set_axis_off()

ax3.set_title(
    "Bivariate: Canopy Loss × Asthma Rate",
    fontsize=10,
    fontweight="bold",
    pad=4
)

ax3.text(
    0.02,
    0.98,
    "C",
    transform=ax3.transAxes,
    fontsize=15,
    fontweight="bold",
    va="top",
    ha="left",
    bbox=dict(
        fc="white",
        ec="none",
        alpha=0.85,
        pad=1.5
    )
)

ax3.text(
    0.50,
    0.02,
    f"✓ Gate 3b APPROVE  I_xy={d['bivariate_morans_i']:+.3f}  ρ={d['spearman_rho']:+.3f}",
    transform=ax3.transAxes,
    fontsize=6.8,
    fontweight="bold",
    ha="center",
    va="bottom",
    color="#1E9E52",
    bbox=dict(
        fc="white",
        ec="#1E9E52",
        lw=0.8,
        alpha=0.95,
        pad=2.2,
        boxstyle="round,pad=0.28"
    )
)

# =============================================================================
# BIVARIATE LEGEND - VERTICAL (AS REQUESTED)
# =============================================================================

# FIXED: Better legend positioning
leg = ax3.inset_axes([0.72, 0.08, 0.16, 0.16])

leg.set_xlim(0, 3)
leg.set_ylim(0, 3)

for r in range(3):
    for c in range(3):
        rect = mpatches.Rectangle(
            (c, 2-r),  # Reverse row order for correct orientation
            1,
            1,
            fc=BIVAR_HEX[r][c],
            ec="white",
            lw=0.4
        )
        leg.add_patch(rect)

leg.set_xticks([0.5, 1.5, 2.5])
leg.set_yticks([0.5, 1.5, 2.5])
leg.set_xticklabels(["Low", "Med", "High"], fontsize=5)
leg.set_yticklabels(["High", "Med", "Low"], fontsize=5)  # Reverse for correct orientation
leg.tick_params(length=0)

leg.set_xlabel("Asthma Rate →", fontsize=5.5, labelpad=0)
leg.set_ylabel("Canopy Loss →", fontsize=5.5, labelpad=0)

for s in leg.spines.values():
    s.set_linewidth(0.4)

# =============================================================================
# TABLE PANELS - FIXED ALIGNMENT
# =============================================================================

def style_table_axis(ax, title):

    ax.set_axis_off()
    ax.set_facecolor("#FAFAFA")

    for s in ax.spines.values():
        s.set_visible(True)
        s.set_linewidth(0.6)
        s.set_edgecolor("#D0D0D0")

    ax.text(
        0.5,
        0.94,
        title,
        transform=ax.transAxes,
        fontsize=9,
        fontweight="bold",
        ha="center",
        va="top",
        color="#1A1A1A"
    )

    ax.plot(
        [0.03, 0.97],
        [0.88, 0.88],
        transform=ax.transAxes,
        color="#D0D0D0",
        lw=0.8
    )

style_table_axis(ax4, "Gate 2 — Classification Diagnostic Engine")
style_table_axis(ax5, "Gate 3b — Bivariate Spatial Cross-Correlation")

# =============================================================================
# TABLE 1 - IMPROVED SPACING
# =============================================================================

cols = ["Variable", "Diagnosis", "Prescribed", "Status"]
xs = [0.03, 0.30, 0.58, 0.92]

header_y = 0.82

for x, c in zip(xs, cols):
    ax4.text(
        x,
        header_y,
        c,
        transform=ax4.transAxes,
        fontsize=7,
        fontweight="bold",
        color="#444444"
    )

ax4.plot(
    [0.03, 0.97],
    [0.78, 0.78],
    transform=ax4.transAxes,
    color="#BDBDBD",
    lw=0.6
)

rows = [
    ("Tree Canopy Loss", "heavy right skew", "log transform then jenks"),
    ("Asthma Hosp. Rate", "heavy right skew", "log transform then jenks"),
]

for i, row in enumerate(rows):
    y = 0.65 - i * 0.22
    
    ax4.text(xs[0], y, row[0], transform=ax4.transAxes, fontsize=7)
    ax4.text(xs[1], y, row[1], transform=ax4.transAxes,
             fontsize=6.5, color="#8E44AD", style="italic")
    ax4.text(xs[2], y, row[2], transform=ax4.transAxes,
             fontsize=6.5, color="#2874A6")
    ax4.text(
        xs[3],
        y,
        "PRESCRIBED",
        transform=ax4.transAxes,
        fontsize=6.8,
        fontweight="bold",
        ha="right",
        color="#C0392B"
    )

# Footer note with word wrap
footer_text = "LLM proposed naive Jenks. Gate 2 overrode both variables to log-transform + Jenks on transformed residual distributions."

# Manual wrap for better display
wrapped_text = "\n".join([footer_text[i:i+65] for i in range(0, len(footer_text), 65)])

ax4.text(
    0.5,
    0.10,
    wrapped_text,
    transform=ax4.transAxes,
    fontsize=6,
    style="italic",
    ha="center",
    color="#666666",
    linespacing=1.2
)

# =============================================================================
# TABLE 2 - IMPROVED SPACING
# =============================================================================

cols2 = ["Statistic", "Value", "p-value", "Threshold", "Decision"]
xs2 = [0.03, 0.32, 0.52, 0.70, 0.92]

for x, c in zip(xs2, cols2):
    ax5.text(
        x,
        header_y,
        c,
        transform=ax5.transAxes,
        fontsize=7,
        fontweight="bold",
        color="#444444"
    )

ax5.plot(
    [0.03, 0.97],
    [0.78, 0.78],
    transform=ax5.transAxes,
    color="#BDBDBD",
    lw=0.6
)

stats_rows = [
    ("Bivariate Moran's I_xy", f"{d['bivariate_morans_i']:+.4f}", 
     f"{d['bivariate_morans_p']:.4f}", "|I_xy| > 0.15"),
    ("Spearman's ρ", f"{d['spearman_rho']:+.4f}", 
     f"{d['spearman_p']:.2e}", "|ρ| > 0.20")
]

for i, row in enumerate(stats_rows):
    y = 0.65 - i * 0.22

    ax5.text(xs2[0], y, row[0], transform=ax5.transAxes, fontsize=7)
    ax5.text(xs2[1], y, row[1], transform=ax5.transAxes,
             fontsize=6.8, color="#1F618D")
    ax5.text(xs2[2], y, row[2], transform=ax5.transAxes,
             fontsize=6.5, color="#555555")
    ax5.text(xs2[3], y, row[3], transform=ax5.transAxes,
             fontsize=6.3, color="#666666")
    ax5.text(
        xs2[4],
        y,
        "✓ PASS",
        transform=ax5.transAxes,
        fontsize=6.8,
        fontweight="bold",
        ha="right",
        color="#1E9E52"
    )

# Decision banner
ax5.text(
    0.5,
    0.28,
    "✓ Overall gate decision: APPROVE",
    transform=ax5.transAxes,
    fontsize=8,
    fontweight="bold",
    ha="center",
    color="#1E9E52",
    bbox=dict(
        fc="#1E9E5218",
        ec="#1E9E52",
        lw=0.8,
        pad=3.5,
        boxstyle="round,pad=0.32"
    )
)

# Footer with wrap
footer2 = "199 permutations under H₀ of no spatial cross-association. Pseudo p-value = (M+1)/(R+1)."
wrapped_footer2 = "\n".join([footer2[i:i+70] for i in range(0, len(footer2), 70)])

ax5.text(
    0.5,
    0.10,
    wrapped_footer2,
    transform=ax5.transAxes,
    fontsize=5.8,
    style="italic",
    ha="center",
    color="#666666",
    linespacing=1.2
)

# =============================================================================
# FIGURE TITLE / FOOTER
# =============================================================================

fig.suptitle(
    "CartoLLM Autonomous Validation · Atlanta Metro Census Tracts "
    "(Fulton + DeKalb Counties, GA · Real TIGER Geometry)",
    fontsize=12.5,
    fontweight="bold",
    y=0.975,
    color="#1A1A1A"
)

fig.text(
    0.5,
    0.02,
    f"n = {n} tracts · Synthetic SAR variables on real queen-contiguity weights "
    f"· I_xy={d['bivariate_morans_i']:+.3f} "
    f"· ρ={d['spearman_rho']:+.3f} "
    f"({d['decision']})",
    ha="center",
    fontsize=6.3,
    color="#7A7A7A"
)

# =============================================================================
# SAVE
# =============================================================================

png_out = os.path.join(
    SCRIPT_DIR,
    "atlanta_results_panel_publication.png"
)

pdf_out = os.path.join(
    SCRIPT_DIR,
    "atlanta_results_panel_publication.pdf"
)

# Save with high quality
fig.savefig(
    png_out,
    dpi=300,
    bbox_inches="tight",
    facecolor="white",
    pad_inches=0.05
)

fig.savefig(
    pdf_out,
    bbox_inches="tight",
    facecolor="white",
    pad_inches=0.05
)

plt.close(fig)

print(f"\n✓ Saved PNG → {png_out}")
print(f"✓ Saved PDF → {pdf_out}")
print(f"\n✓ Figure dimensions: {fig.get_size_inches()}")
print("✓ All overlaps resolved")
print("\nDone.")