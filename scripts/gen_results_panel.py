#!/usr/bin/env python3
"""
gen_results_panel.py — CartoLLM · STDS 2026 poster results figure
===================================================================
Generates a publication-quality 4-panel results figure:

  A  Tree-canopy-loss choropleth  (Gate 2 validated, log+Jenks breaks)
  B  Asthma-hospitalisation-rate choropleth  (Gate 2 validated)
  C  Bivariate choropleth          (Gate 3b APPROVED)
  D  Validation-statistics panel   (Gate 2 + Gate 3b summary table)

Data
----
  Geometry : Census TIGER, Fulton (13121) + DeKalb (13089) Counties, GA
  Variables: Synthetic, SAR-generated on real tract topology to reflect
             plausible spatial structure (environmental-justice scenario).

Outputs
-------
  output/figures/atlanta_results_panel.png  (300 dpi, sRGB)
  output/figures/atlanta_results_panel.pdf  (vector)
"""

import os
import sys
import json
import warnings
import urllib.request
from typing import List, Optional, Tuple

import numpy as np
import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import matplotlib.ticker as ticker
from matplotlib.colors import BoundaryNorm, ListedColormap, Normalize
from matplotlib.cm import ScalarMappable
from scipy.linalg import solve as sp_solve
import libpysal

warnings.filterwarnings("ignore")

# ── Paths & arguments ─────────────────────────────────────────────────────────
import argparse

# Windows consoles default to cp1252, which cannot print the arrows/glyphs in
# this script's progress output. Force UTF-8 with graceful degradation.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
SNAPSHOT   = os.path.join(REPO_ROOT, "data", "atlanta_tracts_fulton_dekalb.geojson")

_parser = argparse.ArgumentParser(description="CartoLLM Atlanta results panel")
_parser.add_argument("--out", default=os.path.join(REPO_ROOT, "artifacts", "figures"),
                     help="Output directory for PNG/PDF (default: artifacts/figures)")
_parser.add_argument("--live", action="store_true",
                     help="Query TIGERweb instead of the pinned data/ snapshot")
_args = _parser.parse_args()

FIG_DIR = _args.out
os.makedirs(FIG_DIR, exist_ok=True)

from autocarto.execution.gates.gate2_classification import (
    ClassificationDiagnosticEngine,
    _dedupe_breaks,
)
from autocarto.execution.gates.gate3b_bivariate_correlation import BivariateCorrelationGate

# ── Matplotlib defaults ───────────────────────────────────────────────────────
mpl.rcParams.update({
    "font.family":      "DejaVu Sans",
    "font.size":        8.0,
    "axes.titlesize":   9.0,
    "axes.titleweight": "bold",
    "axes.labelsize":   7.5,
    "xtick.labelsize":  6.5,
    "ytick.labelsize":  6.5,
    "figure.dpi":       150,
    "savefig.dpi":      300,
    "pdf.fonttype":     42,   # embed fonts as Type 2 (Postscript)
    "ps.fonttype":      42,
})

# ── 1. Load Atlanta census tract geometry (pinned snapshot by default) ────────
TIGER_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Tracts_Blocks/MapServer/4/query"
    "?where=STATE%3D%2713%27+AND+COUNTY+IN+%28%27121%27%2C%27089%27%29"
    "&outFields=GEOID%2CNAME%2CSTATE%2CCOUNTY%2CTRACT"
    "&f=geojson&outSR=4326&resultRecordCount=2000"
)

if _args.live:
    print("Downloading Census TIGER tracts (--live) …")
    req = urllib.request.Request(TIGER_URL, headers={"User-Agent": "CartoLLM/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
else:
    # TD-7 fix: reproduce offline from the checksummed snapshot
    # (regenerate with scripts/snapshot_tiger.py; hash in data/MANIFEST.md).
    print(f"Loading pinned TIGER snapshot: {SNAPSHOT}")
    if not os.path.exists(SNAPSHOT):
        raise SystemExit(
            "Snapshot missing. Run `python scripts/snapshot_tiger.py` once "
            "(network required) or pass --live."
        )
    with open(SNAPSHOT, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

features = payload.get("features", [])
print(f"  → {len(features)} features received")

gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
print(f"  → GDF shape: {gdf.shape}, CRS: {gdf.crs}")

# Reproject to Georgia State Plane (EPSG:26967) for accurate neighbour detection
gdf = gdf.to_crs(epsg=26967)

# ── 2. Build Queen contiguity weights ────────────────────────────────────────
print("Building Queen contiguity weights …")
W_q = libpysal.weights.Queen.from_dataframe(gdf, silence_warnings=True)

# Drop islands (tracts with zero shared-boundary neighbours)
if W_q.islands:
    print(f"  Dropping {len(W_q.islands)} island tract(s)")
    keep = [i for i in range(len(gdf)) if gdf.index[i] not in W_q.islands]
    gdf = gdf.iloc[keep].reset_index(drop=True)
    W_q = libpysal.weights.Queen.from_dataframe(gdf, silence_warnings=True)

n = len(gdf)
print(f"  → {n} tracts after island removal")

# Row-standardise → dense array
W_q.transform = "r"
W_rs = W_q.full()[0]                  # (n, n) float64

row_sums = W_rs.sum(axis=1)
assert np.allclose(row_sums, 1.0, atol=1e-6), (
    f"Row standardisation failed: sums in [{row_sums.min():.4f}, {row_sums.max():.4f}]"
)
print(f"  → W_rs shape {W_rs.shape}, row sums ✓")

# ── 3. SAR-based synthetic variables ─────────────────────────────────────────
def sar_draw(W: np.ndarray, rho: float, seed: int) -> np.ndarray:
    """Draw one SAR(rho) realisation: y = (I − rho·W)⁻¹ · ε."""
    rng = np.random.default_rng(seed)
    A   = np.eye(W.shape[0]) - rho * W
    eps = rng.standard_normal(W.shape[0])
    return sp_solve(A, eps)

print("Generating SAR variables …")

# Common latent spatial factor shared by both variables (drives cross-correlation)
z_common = sar_draw(W_rs, rho=0.72, seed=1001)

# Tree canopy loss (% lost):  right-skewed lognormal  →  Gate 2 → heavy_right_skew
z_x          = 0.78 * z_common + 0.22 * sar_draw(W_rs, rho=0.35, seed=1002)
tree_raw      = np.exp(z_x * 0.90) * 7.5          # ≈ lognormal in [0.5, 95]%
tree_canopy   = np.clip(tree_raw, 0.5, 95.0)

# Asthma hospitalisation rate (per 10 000):  right-skewed → Gate 2 → heavy_right_skew
z_y          = 0.75 * z_common + 0.25 * sar_draw(W_rs, rho=0.35, seed=1003)
asthma_raw   = np.exp(z_y * 0.85) * 18.0          # ≈ lognormal in [1, 250]
asthma_rate  = np.clip(asthma_raw, 1.0, 250.0)

gdf["tree_canopy_loss"] = tree_canopy
gdf["asthma_rate"]      = asthma_rate

print(f"  tree_canopy_loss:  skew={float(np.mean(((tree_canopy-tree_canopy.mean())/tree_canopy.std())**3)):.2f}"
      f"  range=[{tree_canopy.min():.1f}, {tree_canopy.max():.1f}]")
print(f"  asthma_rate:       skew={float(np.mean(((asthma_rate-asthma_rate.mean())/asthma_rate.std())**3)):.2f}"
      f"  range=[{asthma_rate.min():.1f}, {asthma_rate.max():.1f}]")

# ── 4. Gate 2: Classification diagnostics ────────────────────────────────────
print("\n── Gate 2 ───────────────────────────────────────────────────────────────")

engine = ClassificationDiagnosticEngine(random_state=0)

# Simulate LLM proposing naïve Jenks (which Gate 2 will override)
g2_canopy = engine.evaluate(tree_canopy, proposed_method="jenks")
engine.iteration_count = 0            # reset for second variable
g2_asthma  = engine.evaluate(asthma_rate, proposed_method="jenks")

print(f"  tree_canopy_loss:")
print(f"    diagnosis        = {g2_canopy.diagnosis}")
print(f"    prescribed_method= {g2_canopy.prescribed_method}")
print(f"    prescribed_breaks= {[round(b, 2) for b in (g2_canopy.prescribed_breaks or [])]}")
print(f"  asthma_rate:")
print(f"    diagnosis        = {g2_asthma.diagnosis}")
print(f"    prescribed_method= {g2_asthma.prescribed_method}")
print(f"    prescribed_breaks= {[round(b, 2) for b in (g2_asthma.prescribed_breaks or [])]}")

# GVF verification — the poster's classification-fit statistic, regenerable.
# (Replaces the untraceable "0.894"; see Fable Review/02_...GUIDE.md §4.2-1.)
print("\n── GVF: prescribed vs naive-quintile ────────────────────────────────────")
for _name, _vals, _res in (("tree_canopy_loss", tree_canopy, g2_canopy),
                           ("asthma_rate", asthma_rate, g2_asthma)):
    _presc = _dedupe_breaks([float(b) for b in (_res.prescribed_breaks or [])])
    _naive = _dedupe_breaks([float(np.percentile(_vals, p)) for p in (0, 20, 40, 60, 80, 100)])
    _gvf_p = ClassificationDiagnosticEngine._compute_gvf(_vals, _presc) if len(_presc) > 1 else float("nan")
    _gvf_n = ClassificationDiagnosticEngine._compute_gvf(_vals, _naive)
    print(f"  {_name}: GVF naive={_gvf_n:.4f} → prescribed={_gvf_p:.4f}")

# ── 5. Gate 3b: Bivariate spatial cross-correlation ──────────────────────────
print("\n── Gate 3b ──────────────────────────────────────────────────────────────")

gate3b    = BivariateCorrelationGate()
g3b_result = gate3b.evaluate(
    x=tree_canopy,
    y=asthma_rate,
    weights_matrix=W_rs,
    permutations=199,
    random_state=0,
)
d = g3b_result.to_dict()
print(f"  I_xy   = {d['bivariate_morans_i']:+.4f}  (p = {d['bivariate_morans_p']:.4f})")
print(f"  ρ_sp   = {d['spearman_rho']:+.4f}  (p = {d['spearman_p']:.2e})")
print(f"  Decision → {d['decision']}")


# ══════════════════════════════════════════════════════════════════════════════
# 6. Render publication-quality results panel
# ══════════════════════════════════════════════════════════════════════════════

# ── Colour helpers ────────────────────────────────────────────────────────────

def _make_cmap_and_norm(
    breaks: List[float],
    base_cmap: str,
) -> Tuple[ListedColormap, BoundaryNorm]:
    """Build a discrete ListedColormap with one colour per class interval."""
    n_cls   = len(breaks) - 1
    base    = mpl.colormaps[base_cmap].resampled(n_cls)
    colors  = [base(i / n_cls) for i in range(n_cls)]
    cmap    = ListedColormap(colors, name=f"custom_{base_cmap}")
    norm    = BoundaryNorm(breaks, cmap.N)
    return cmap, norm

def _safe_breaks(result, values: np.ndarray, fallback_n: int = 5) -> List[float]:
    """Extract usable break points from a DiagnosticResult."""
    brks = result.prescribed_breaks
    if brks and len(brks) >= 2:
        return [float(b) for b in brks]
    # Fallback: quintile breaks
    pcts = np.linspace(0, 100, fallback_n + 1)
    return [float(np.percentile(values, p)) for p in pcts]

# ── Bivariate colour scheme (3×3, Joshua Stevens DkBlue2 variant) ─────────────
# Rows = tree_canopy class (0=low, 1=med, 2=high)
# Cols = asthma_rate class (0=low, 1=med, 2=high)
BIVAR_HEX = [
    ["#e8e8e8", "#ace4e4", "#5ac8c8"],   # canopy low
    ["#dfb0d6", "#a5add3", "#5698b9"],   # canopy medium
    ["#be64ac", "#8c62aa", "#3b4994"],   # canopy high
]

def _bivar_color(canopy_cls: int, asthma_cls: int) -> str:
    return BIVAR_HEX[canopy_cls][asthma_cls]

def _tertile_class(arr: np.ndarray) -> np.ndarray:
    q33, q67 = np.percentile(arr, [33.33, 66.67])
    cls = np.zeros(len(arr), dtype=int)
    cls[arr >= q33] = 1
    cls[arr >= q67] = 2
    return cls

canopy_cls  = _tertile_class(tree_canopy)
asthma_cls  = _tertile_class(asthma_rate)
bivar_colors = [_bivar_color(c, a) for c, a in zip(canopy_cls, asthma_cls)]

# ── Figure layout ─────────────────────────────────────────────────────────────
FIG_W, FIG_H = 11.0, 8.5
fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor="white")

outer = gridspec.GridSpec(
    2, 1,
    figure=fig,
    height_ratios=[2.6, 1.0],
    hspace=0.08,
    left=0.02, right=0.98,
    top=0.93, bottom=0.03,
)
top_row  = gridspec.GridSpecFromSubplotSpec(
    1, 3, subplot_spec=outer[0], wspace=0.06,
)
bot_row  = gridspec.GridSpecFromSubplotSpec(
    1, 2, subplot_spec=outer[1], wspace=0.06,
)

ax_c  = fig.add_subplot(top_row[0])   # Panel A: canopy loss
ax_a  = fig.add_subplot(top_row[1])   # Panel B: asthma rate
ax_bv = fig.add_subplot(top_row[2])   # Panel C: bivariate
ax_g2 = fig.add_subplot(bot_row[0])   # Panel D-left:  Gate 2 table
ax_g3 = fig.add_subplot(bot_row[1])   # Panel D-right: Gate 3b table

# ── Panel helper: draw one map ────────────────────────────────────────────────
def _draw_map(
    ax,
    gdf: gpd.GeoDataFrame,
    col: str,
    cmap,
    norm,
    title: str,
    panel_label: str,
    gate_badge: str,
    badge_ok: bool,
    unit: str,
    n_classes: int,
    breaks: List[float],
):
    # Reproject back to WGS-84 for plotting (lat/lon graticule)
    gdf_plot = gdf.to_crs(epsg=4326)
    gdf_plot.plot(
        column=col,
        ax=ax,
        cmap=cmap,
        norm=norm,
        linewidth=0.15,
        edgecolor="#ffffff",
        zorder=2,
    )
    # Thin county boundary overlay
    gdf_plot.dissolve(by="COUNTY").boundary.plot(
        ax=ax, linewidth=0.7, edgecolor="#555555", zorder=3
    )
    ax.set_axis_off()

    # Title
    ax.set_title(title, fontsize=9, fontweight="bold", pad=5)

    # Panel letter (A, B, C)
    ax.text(
        0.02, 0.98, panel_label,
        transform=ax.transAxes,
        fontsize=12, fontweight="bold",
        va="top", ha="left", color="#222222",
        bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.5),
    )

    # Gate badge
    badge_col  = "#27ae60" if badge_ok else "#e67e22"
    badge_icon = "✓" if badge_ok else "⚠"
    ax.text(
        0.50, 0.01, f"{badge_icon} {gate_badge}",
        transform=ax.transAxes,
        fontsize=7, fontweight="bold",
        va="bottom", ha="center", color=badge_col,
        bbox=dict(fc="white", ec=badge_col, linewidth=0.7,
                  alpha=0.88, pad=2, boxstyle="round,pad=0.3"),
    )

    # Vertical discrete colorbar
    sm  = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb  = fig.colorbar(
        sm, ax=ax,
        orientation="vertical",
        shrink=0.55, pad=0.015,
        aspect=18,
    )
    cb.ax.tick_params(labelsize=5.5)
    cb.set_label(unit, fontsize=6, labelpad=3)
    # Only show tick at class boundaries
    cb.set_ticks(breaks)
    cb.set_ticklabels([f"{b:.1f}" if b < 100 else f"{b:.0f}" for b in breaks])


# ── Panel A: Tree canopy loss ─────────────────────────────────────────────────
brks_c  = _safe_breaks(g2_canopy, tree_canopy)
# Ensure covers full data range
brks_c[0] = min(brks_c[0], float(tree_canopy.min()))
brks_c[-1] = max(brks_c[-1], float(tree_canopy.max()) + 0.01)
cmap_c, norm_c = _make_cmap_and_norm(brks_c, "YlOrBr")

g2c_method = (g2_canopy.prescribed_method or "jenks").replace("_", " ")
_draw_map(
    ax_c, gdf, "tree_canopy_loss",
    cmap_c, norm_c,
    title="Tree Canopy Loss (%)",
    panel_label="A",
    gate_badge=f"Gate 2 → {g2c_method}",
    badge_ok=True,
    unit="% loss",
    n_classes=len(brks_c) - 1,
    breaks=brks_c,
)

# ── Panel B: Asthma hospitalisation rate ─────────────────────────────────────
brks_a  = _safe_breaks(g2_asthma, asthma_rate)
brks_a[0] = min(brks_a[0], float(asthma_rate.min()))
brks_a[-1] = max(brks_a[-1], float(asthma_rate.max()) + 0.01)
cmap_a, norm_a = _make_cmap_and_norm(brks_a, "OrRd")

g2a_method = (g2_asthma.prescribed_method or "jenks").replace("_", " ")
_draw_map(
    ax_a, gdf, "asthma_rate",
    cmap_a, norm_a,
    title="Asthma Hospitalisation Rate (per 10 000)",
    panel_label="B",
    gate_badge=f"Gate 2 → {g2a_method}",
    badge_ok=True,
    unit="per 10 000",
    n_classes=len(brks_a) - 1,
    breaks=brks_a,
)

# ── Panel C: Bivariate choropleth ─────────────────────────────────────────────
gdf_plot_bv = gdf.to_crs(epsg=4326)
gdf_plot_bv.assign(bivar_col=bivar_colors).plot(
    ax=ax_bv,
    color=bivar_colors,
    linewidth=0.15,
    edgecolor="#ffffff",
    zorder=2,
)
gdf_plot_bv.dissolve(by="COUNTY").boundary.plot(
    ax=ax_bv, linewidth=0.7, edgecolor="#555555", zorder=3
)
ax_bv.set_axis_off()
ax_bv.set_title("Bivariate: Canopy Loss × Asthma Rate", fontsize=9, fontweight="bold", pad=5)
ax_bv.text(
    0.02, 0.98, "C",
    transform=ax_bv.transAxes,
    fontsize=12, fontweight="bold",
    va="top", ha="left", color="#222222",
    bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.5),
)

g3b_ok   = d["decision"] == "APPROVE"
g3b_icon = "✓" if g3b_ok else "⚠"
g3b_col  = "#27ae60" if g3b_ok else "#e67e22"
ax_bv.text(
    0.50, 0.01,
    f"{g3b_icon} Gate 3b {d['decision']}  "
    f"I_xy={d['bivariate_morans_i']:+.3f}  ρ={d['spearman_rho']:+.3f}",
    transform=ax_bv.transAxes,
    fontsize=6.5, fontweight="bold",
    va="bottom", ha="center", color=g3b_col,
    bbox=dict(fc="white", ec=g3b_col, linewidth=0.7,
              alpha=0.88, pad=2, boxstyle="round,pad=0.3"),
)

# ── Bivariate legend (3×3 colour matrix inset) ───────────────────────────────
LEGEND_SZ = 0.16   # fraction of axes
leg_ax = ax_bv.inset_axes([0.72, 0.04, LEGEND_SZ, LEGEND_SZ])
leg_ax.set_xlim(0, 3)
leg_ax.set_ylim(0, 3)
for ci in range(3):
    for ai in range(3):
        leg_ax.add_patch(mpatches.Rectangle(
            (ai, ci), 1, 1,
            fc=BIVAR_HEX[ci][ai], ec="white", lw=0.4,
        ))
leg_ax.set_xticks([0, 1, 2, 3])
leg_ax.set_xticklabels(["", "Lo", "Med", "Hi"], fontsize=4.5)
leg_ax.set_yticks([0, 1, 2, 3])
leg_ax.set_yticklabels(["", "Lo", "Med", "Hi"], fontsize=4.5)
leg_ax.set_xlabel("Asthma →", fontsize=4.5, labelpad=1)
leg_ax.set_ylabel("Canopy →", fontsize=4.5, labelpad=1)
leg_ax.tick_params(length=0)
leg_ax.set_aspect("equal")
for sp in leg_ax.spines.values():
    sp.set_linewidth(0.4)


# ── Panel D-left: Gate 2 summary table ───────────────────────────────────────
ax_g2.set_axis_off()

# Section header
ax_g2.text(
    0.5, 0.96,
    "Gate 2 — Classification Diagnostic Engine",
    transform=ax_g2.transAxes,
    fontsize=8.5, fontweight="bold", ha="center", va="top",
    color="#1a1a2e",
)
ax_g2.plot([0.05, 0.95], [0.90, 0.90], color="#cccccc", lw=0.8,
           transform=ax_g2.transAxes)

# Column headers
cols_g2 = ["Variable", "Diagnosis", "Prescribed Method", "Status"]
xs = [0.02, 0.28, 0.56, 0.90]
header_y = 0.83
for x, c in zip(xs, cols_g2):
    ax_g2.text(
        x, header_y, c,
        transform=ax_g2.transAxes,
        fontsize=7, fontweight="bold", va="top", ha="left", color="#444444",
    )
ax_g2.plot([0.02, 0.98], [header_y - 0.05, header_y - 0.05], color="#aaaaaa", lw=0.6,
           transform=ax_g2.transAxes)

# Short display labels for the method column — matches the phrasing used in
# Fable Review/06_POSTER_COPY.md Block A ("log-transform + Jenks"), and fixes
# a text collision: the full "log transform then jenks" (24 chars) ran into
# the right-aligned "PRESCRIBED" status label at this column width.
METHOD_DISPLAY = {
    "log_transform_then_jenks": "log-transform + Jenks",
    "manual_break_at_zero_then_fisher_jenks": "break-at-0 + Jenks",
    "arcsinh_transform_then_jenks": "arcsinh + Jenks",
    "unique_values": "unique values",
    "head_tail_breaks": "head-tail breaks",
    "jenks": "jenks",
}

def _method_label(method_key: str) -> str:
    return METHOD_DISPLAY.get(method_key, method_key.replace("_", " "))

# Data rows
rows_g2 = [
    (
        "Tree Canopy Loss",
        g2_canopy.diagnosis.replace("_", " "),
        _method_label(g2_canopy.prescribed_method or "jenks"),
        g2_canopy,
    ),
    (
        "Asthma Hosp. Rate",
        g2_asthma.diagnosis.replace("_", " "),
        _method_label(g2_asthma.prescribed_method or "jenks"),
        g2_asthma,
    ),
]

xs_status = 0.97  # was xs[3]=0.90: gives the method column more clearance

for row_i, (varname, diag, method, res) in enumerate(rows_g2):
    ry  = header_y - 0.22 - row_i * 0.22
    status_ok = (res.prescribed_method is not None)
    status_txt = "PRESCRIBED" if status_ok else "PASS"
    status_col = "#c0392b" if status_ok else "#27ae60"

    ax_g2.text(xs[0], ry, varname,      transform=ax_g2.transAxes,
               fontsize=7, va="top", ha="left")
    ax_g2.text(xs[1], ry, diag,         transform=ax_g2.transAxes,
               fontsize=6.5, va="top", ha="left", color="#8e44ad",
               fontstyle="italic")
    ax_g2.text(xs[2], ry, method,       transform=ax_g2.transAxes,
               fontsize=6.5, va="top", ha="left", color="#2471a3")
    ax_g2.text(xs_status, ry, status_txt, transform=ax_g2.transAxes,
               fontsize=7, fontweight="bold", va="top", ha="right",
               color=status_col)

ax_g2.plot([0.02, 0.98], [header_y - 0.58, header_y - 0.58], color="#aaaaaa", lw=0.6,
           transform=ax_g2.transAxes)

# Explanatory footnote
note = (
    "LLM proposed: jenks (naïve).  "
    "Gate 2 overrides both → log-transform first, then Jenks on residuals."
)
ax_g2.text(
    0.5, 0.06, note,
    transform=ax_g2.transAxes,
    fontsize=6, va="bottom", ha="center",
    color="#555555", style="italic",
    wrap=True,
)

ax_g2.set_facecolor("#f8f9fa")
for sp in ax_g2.spines.values():
    sp.set_visible(True)
    sp.set_linewidth(0.5)
    sp.set_edgecolor("#cccccc")


# ── Panel D-right: Gate 3b summary table ─────────────────────────────────────
ax_g3.set_axis_off()

ax_g3.text(
    0.5, 0.96,
    "Gate 3b — Bivariate Spatial Cross-Correlation",
    transform=ax_g3.transAxes,
    fontsize=8.5, fontweight="bold", ha="center", va="top",
    color="#1a1a2e",
)
ax_g3.plot([0.05, 0.95], [0.90, 0.90], color="#cccccc", lw=0.8,
           transform=ax_g3.transAxes)

cols_g3 = ["Statistic", "Value", "p-value", "Threshold", "Decision"]
xs3 = [0.02, 0.32, 0.50, 0.66, 0.93]
for x, c in zip(xs3, cols_g3):
    ax_g3.text(
        x, header_y, c,
        transform=ax_g3.transAxes,
        fontsize=7, fontweight="bold", va="top", ha="left", color="#444444",
    )
ax_g3.plot([0.02, 0.98], [header_y - 0.05, header_y - 0.05], color="#aaaaaa", lw=0.6,
           transform=ax_g3.transAxes)

I_val  = d["bivariate_morans_i"]
I_p    = d["bivariate_morans_p"]
rho_v  = d["spearman_rho"]
rho_p  = d["spearman_p"]

def _pass_fail(ok: bool) -> Tuple[str, str]:
    return ("✓  PASS", "#27ae60") if ok else ("✗  FAIL", "#c0392b")

i_ok   = abs(I_val) > 0.15
rho_ok = abs(rho_v) > 0.20

rows_g3 = [
    ("Bivariate Moran's I_xy",  f"{I_val:+.4f}",  f"{I_p:.4f}",   "|I_xy| > 0.15", i_ok),
    ("Spearman's ρ",            f"{rho_v:+.4f}",  f"{rho_p:.2e}", "|ρ|   > 0.20",  rho_ok),
]
for row_i, (stat, val, pv, thr, ok) in enumerate(rows_g3):
    ry = header_y - 0.22 - row_i * 0.22
    txt, col = _pass_fail(ok)
    ax_g3.text(xs3[0], ry, stat, transform=ax_g3.transAxes,
               fontsize=7, va="top", ha="left")
    ax_g3.text(xs3[1], ry, val,  transform=ax_g3.transAxes,
               fontsize=7, va="top", ha="left", color="#1a5276")
    ax_g3.text(xs3[2], ry, pv,   transform=ax_g3.transAxes,
               fontsize=6.5, va="top", ha="left", color="#555555")
    ax_g3.text(xs3[3], ry, thr,  transform=ax_g3.transAxes,
               fontsize=6.5, va="top", ha="left", color="#666666")
    ax_g3.text(xs3[4], ry, txt,  transform=ax_g3.transAxes,
               fontsize=7, fontweight="bold", va="top", ha="right", color=col)

ax_g3.plot([0.02, 0.98], [header_y - 0.58, header_y - 0.58], color="#aaaaaa", lw=0.6,
           transform=ax_g3.transAxes)

# Overall decision banner
dec       = d["decision"]
dec_ok    = dec == "APPROVE"
dec_color = "#27ae60" if dec_ok else ("#e67e22" if dec == "WARN" else "#c0392b")
dec_icon  = "✓" if dec_ok else ("⚠" if dec == "WARN" else "✗")
ax_g3.text(
    0.5, 0.24,
    f"{dec_icon}  Overall gate decision:  {dec}",
    transform=ax_g3.transAxes,
    fontsize=8.5, fontweight="bold", ha="center", va="center",
    color=dec_color,
    bbox=dict(fc=dec_color + "22", ec=dec_color, lw=1.0,
              pad=4, boxstyle="round,pad=0.4"),
)

note3 = (
    "199 permutations under H₀: no spatial cross-association. "
    "Pseudo p-value = (M+1)/(R+1).  Bivariate choropleth unlocked."
)
ax_g3.text(
    0.5, 0.06, note3,
    transform=ax_g3.transAxes,
    fontsize=6, va="bottom", ha="center",
    color="#555555", style="italic",
)

ax_g3.set_facecolor("#f8f9fa")
for sp in ax_g3.spines.values():
    sp.set_visible(True)
    sp.set_linewidth(0.5)
    sp.set_edgecolor("#cccccc")


# ── Figure title & footer ─────────────────────────────────────────────────────
fig.text(
    0.5, 0.965,
    "CartoLLM Autonomous Validation  ·  Atlanta Metro Census Tracts"
    "  (Fulton + DeKalb Counties, GA  ·  Real TIGER geometry)",
    ha="center", va="bottom",
    fontsize=10, fontweight="bold", color="#1a1a2e",
)
fig.text(
    0.5, 0.005,
    f"n = {n} tracts  ·  Synthetic SAR variables on real queen-contiguity weights"
    f"  ·  I_xy={I_val:+.3f}  ρ={rho_v:+.3f}  ({dec})",
    ha="center", va="bottom",
    fontsize=6, color="#888888",
)


# ── Save ──────────────────────────────────────────────────────────────────────
png_out = os.path.join(FIG_DIR, "atlanta_results_panel.png")
pdf_out = os.path.join(FIG_DIR, "atlanta_results_panel.pdf")

fig.savefig(png_out, dpi=300, bbox_inches="tight", facecolor="white")
fig.savefig(pdf_out,           bbox_inches="tight", facecolor="white")

print(f"\n✓  PNG → {png_out}")
print(f"✓  PDF → {pdf_out}")
plt.close(fig)
print("Done.")

