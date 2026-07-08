#!/usr/bin/env python3
"""
gen_architecture_diagram.py — CartoLLM · STDS 2026 architecture figure

Renders the three-tier neuro-symbolic architecture showing the
zero-authority-leakage boundary between the stochastic LLM layer (Tier 1)
and the deterministic execution engine (Tier 2 / Tier 3).

Bug-fixes vs. original
----------------------
1. CRITICAL  – FancyBboxPatch rounding_size was multiplied by 50, forcing
               corner radii of 2.5–6.0 data units on boxes that are 0.9 units
               tall.  Every box was rendered as a deformed oval or invisible.
               Fixed: radius values are passed directly in data-unit space.
2. LAYOUT    – Gate column lacked a header label.
3. LAYOUT    – Authority-boundary line extended to full zone height; label
               repositioned to avoid overlap with gate boxes.
4. LAYOUT    – Sandbox inset widened and repositioned entirely within the
               DEE zone background; connector arrow added.
5. LAYOUT    – Cross-zone arrows repositioned to align with actual box
               mid-points (proposal arrow ↔ Code Generator; prescription
               arrow ↔ Policy Engine).
6. LAYOUT    – Data-Fabric → DEE schema arrow now spans the full gap between
               the two zone backgrounds for legibility.
7. STYLE     – PASS/REJECT micro-badges on each gate.
8. STYLE     – Gate label updated to reflect G3a / G3b split in the codebase.
9. CLEANUP   – plt.close(fig) added; tight_layout rect corrected.

Outputs
-------
  output/figures/architecture_boundary.png  (300 dpi, sRGB)
  output/figures/architecture_boundary.pdf  (vector, embedded fonts)
"""

from pathlib import Path
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

mpl.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42})

import argparse
_parser = argparse.ArgumentParser(description="CartoLLM architecture diagram")
_parser.add_argument(
    "--out",
    default=str(Path(__file__).resolve().parent.parent / "artifacts" / "figures"),
    help="Output directory (default: artifacts/figures)",
)
_args = _parser.parse_args()
OUT = Path(_args.out)
OUT.mkdir(parents=True, exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────
C_LLM_BG   = "#FFF3E6"   # amber tint  – stochastic LLM zone
C_LLM_BD   = "#C66A1E"
C_DEE_BG   = "#E7F2FF"   # blue tint   – deterministic DEE zone
C_DEE_BD   = "#2760A7"
C_DF_BG    = "#ECF7E8"   # green tint  – data fabric
C_DF_BD    = "#2F7C45"
C_GATE_OK  = "#2C8A5A"   # gate PASS
C_GATE_REJ = "#C94C4C"   # gate REJECT / PRESCRIBE
C_SB_BG    = "#F0F1FF"   # sandbox callout
C_SB_BD    = "#4E5CCE"
C_PROP     = "#B2601C"   # proposal arrow (T1 → T2)
C_MAND     = "#1F71A1"   # prescription arrow (T2 → T1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def rounded_rect(ax, xy, w, h, fc, ec, lw=1.0, r=0.10, zorder=2):
    """
    Draw a rounded rectangle.

    Parameters
    ----------
    r : float
        Corner rounding radius **in data units**.  Previously this was
        erroneously computed as ``radius * 50``, which made every box an oval.
    """
    patch = mpatches.FancyBboxPatch(
        xy, w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        clip_on=False,
        zorder=zorder,
    )
    ax.add_patch(patch)
    return patch


def arr(ax, x0, y0, x1, y1, color, lw=1.5, zorder=4):
    """Draw an annotate-based arrow between two data-coordinate points."""
    ax.annotate(
        "",
        xy=(x1, y1), xytext=(x0, y0),
        zorder=zorder,
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            linewidth=lw,
            shrinkA=3,
            shrinkB=3,
            mutation_scale=12,
        ),
    )


# ════════════════════════════════════════════════════════════════════════════════
# FIGURE SETUP
# coordinate space: x ∈ [0, 18],  y ∈ [0, 10.5]
# ════════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(18, 10.5))
ax.set_xlim(0, 18)
ax.set_ylim(0, 10.5)
ax.axis("off")
fig.patch.set_facecolor("white")

# Zone x/y extents
ZONE_Y0, ZONE_Y1 = 0.75, 9.35

# ── Zone x boundaries (data units) ───────────────────────────────────────────
#   T1 BG:        0.30 – 4.60      (width 4.30)
#   Gate column:  4.80 – 7.95      (no background)
#   T2 BG:        8.05 – 13.10     (width 5.05)
#   T3 BG:        13.55 – 17.55    (width 4.00)
T1_BG_X0, T1_BG_W = 0.30, 4.30
T2_BG_X0, T2_BG_W = 8.05, 5.05
T3_BG_X0, T3_BG_W = 13.55, 4.00

ZONE_H = ZONE_Y1 - ZONE_Y0

# ════════════════════════════════════════════════════════════════════════════════
# ZONE BACKGROUNDS
# ════════════════════════════════════════════════════════════════════════════════
rounded_rect(ax, (T1_BG_X0, ZONE_Y0), T1_BG_W, ZONE_H,
             C_LLM_BG, C_LLM_BD, lw=2.2, r=0.28, zorder=1)
rounded_rect(ax, (T2_BG_X0, ZONE_Y0), T2_BG_W, ZONE_H,
             C_DEE_BG, C_DEE_BD, lw=2.2, r=0.28, zorder=1)
rounded_rect(ax, (T3_BG_X0, ZONE_Y0), T3_BG_W, ZONE_H,
             C_DF_BG,  C_DF_BD,  lw=2.2, r=0.28, zorder=1)

# Zone headers
ax.text(T1_BG_X0 + T1_BG_W / 2, 9.05,
        "TIER 1 — SEMANTIC ENGINE",
        fontsize=10, fontweight="bold", color=C_LLM_BD, ha="center", va="center")
ax.text(T2_BG_X0 + T2_BG_W / 2, 9.05,
        "TIER 2 — DETERMINISTIC EXECUTION ENGINE",
        fontsize=10, fontweight="bold", color=C_DEE_BD, ha="center", va="center")
ax.text(T3_BG_X0 + T3_BG_W / 2, 9.05,
        "TIER 3 — DATA FABRIC",
        fontsize=10, fontweight="bold", color=C_DF_BD, ha="center", va="center")

# Gate-column label (sits in the gap between T1 and T2)
ax.text(6.40, 9.05, "VALIDATION GATES",
        fontsize=9.0, fontweight="bold", color="#666666",
        ha="center", va="center", style="italic")

# ════════════════════════════════════════════════════════════════════════════════
# AUTHORITY BOUNDARY LINE
# ════════════════════════════════════════════════════════════════════════════════
ax.plot([4.72, 4.72], [ZONE_Y0 + 0.10, ZONE_Y1 - 0.35],
        color=C_LLM_BD, lw=2.0, ls="--", alpha=0.80, zorder=3)

ax.text(4.87, 8.70,
        "Authority Boundary\n"
        "LLM never receives\n"
        "raw data values",
        fontsize=7.0, color=C_LLM_BD,
        ha="left", va="top", fontweight="bold", linespacing=1.45)


# ════════════════════════════════════════════════════════════════════════════════
# TIER 1 — LLM PIPELINE  (4 boxes, top → bottom)
# ════════════════════════════════════════════════════════════════════════════════
T1_X0, T1_W, T1_H = 0.52, 3.76, 0.90
T1_CX = T1_X0 + T1_W / 2

t1_centers = [7.95, 6.65, 5.35, 4.05]   # y-centres of each box
t1_labels  = [
    "Intent Parser",
    "Visual Variable Selector",
    "Template / Style Selector",
    "Declarative Code Generator",
]

for yc, label in zip(t1_centers, t1_labels):
    rounded_rect(ax, (T1_X0, yc - T1_H / 2), T1_W, T1_H,
                 "white", C_LLM_BD, lw=1.3, r=0.10, zorder=3)
    ax.text(T1_CX, yc, label,
            fontsize=8.5, ha="center", va="center", zorder=5)

# Vertical flow connectors within T1
for y0, y1 in zip(t1_centers[:-1], t1_centers[1:]):
    arr(ax, T1_CX, y0 - T1_H / 2,
            T1_CX, y1 + T1_H / 2,
        C_LLM_BD, lw=1.2)


# ════════════════════════════════════════════════════════════════════════════════
# VALIDATION GATES (6 gates, evenly spaced)
# ════════════════════════════════════════════════════════════════════════════════
GATE_CX   = 5.18     # circle centre x
GATE_R    = 0.24     # circle radius
GATE_LX   = 5.56     # label-box left edge
GATE_LW   = 2.12     # label-box width
GATE_LH   = 0.52     # label-box height

gate_data = [
    ("G1",  "CRS Integrity",                  C_GATE_OK),
    ("G2",  "Classification Diagnostic",      C_GATE_REJ),
    ("G3",  "Spatial Autocorrelation (G3a/b)", C_GATE_OK),
    ("G4",  "Projection Distortion",          C_GATE_REJ),
    ("G5",  "Colour Accessibility",           C_GATE_OK),
    ("G6",  "Map Completeness",               C_GATE_OK),
]

gate_ys = np.linspace(8.00, 1.90, len(gate_data))

# Dotted spine linking gate circles
ax.plot([GATE_CX, GATE_CX],
        [gate_ys[-1] - GATE_R - 0.05, gate_ys[0] + GATE_R + 0.05],
        color="#C8C8C8", lw=1.2, ls=":", zorder=1)

for (gid, glabel, gcol), gy in zip(gate_data, gate_ys):
    # Circle
    circ = plt.Circle((GATE_CX, gy), GATE_R,
                       facecolor="white", edgecolor=gcol,
                       linewidth=2.0, zorder=5)
    ax.add_patch(circ)
    ax.text(GATE_CX, gy, gid,
            fontsize=6.5, ha="center", va="center",
            fontweight="bold", color=gcol, zorder=6)

    # Label box
    rounded_rect(ax, (GATE_LX, gy - GATE_LH / 2), GATE_LW, GATE_LH,
                 "white", gcol, lw=0.9, r=0.06, zorder=4)
    ax.text(GATE_LX + GATE_LW / 2, gy, glabel,
            fontsize=6.6, ha="center", va="center", zorder=5)

    # PASS / REJECT micro-badge (right of label box)
    badge_txt = "PASS" if gcol == C_GATE_OK else "REJECT"
    ax.text(GATE_LX + GATE_LW + 0.07, gy, badge_txt,
            fontsize=5.5, ha="left", va="center",
            color="white", fontweight="bold",
            bbox=dict(fc=gcol, ec="none", pad=1.5,
                      boxstyle="round,pad=0.25"),
            zorder=5)


# ════════════════════════════════════════════════════════════════════════════════
# TIER 2 — DETERMINISTIC EXECUTION ENGINE  (5 boxes)
# ════════════════════════════════════════════════════════════════════════════════
T2_X0, T2_W, T2_H = 8.22, 4.10, 0.90
T2_CX = T2_X0 + T2_W / 2

t2_centers = [7.95, 6.70, 5.45, 4.18, 2.90]
t2_labels  = [
    "Policy Engine",
    "Deterministic Validators (G1–G6)",
    "Code Rewriter",
    "Sandbox Executor",
    "Render & Export Engine",
]

for yc, label in zip(t2_centers, t2_labels):
    rounded_rect(ax, (T2_X0, yc - T2_H / 2), T2_W, T2_H,
                 "white", C_DEE_BD, lw=1.3, r=0.10, zorder=3)
    ax.text(T2_CX, yc, label,
            fontsize=8.3, ha="center", va="center", zorder=5)

for y0, y1 in zip(t2_centers[:-1], t2_centers[1:]):
    arr(ax, T2_CX, y0 - T2_H / 2,
            T2_CX, y1 + T2_H / 2,
        C_DEE_BD, lw=1.2)


# ════════════════════════════════════════════════════════════════════════════════
# SANDBOX INSET  (attached to Sandbox Executor, inside T2 zone)
# ════════════════════════════════════════════════════════════════════════════════
SB_X0, SB_W = T2_X0 + T2_W + 0.18, 0.95
SB_Y0, SB_H = 3.48, 2.05            # spans Sandbox Executor y-range
SB_CX = SB_X0 + SB_W / 2

rounded_rect(ax, (SB_X0, SB_Y0), SB_W, SB_H,
             C_SB_BG, C_SB_BD, lw=1.4, r=0.08, zorder=3)

ax.text(SB_CX, SB_Y0 + SB_H - 0.20,
        "Sandbox",
        fontsize=7.0, color=C_SB_BD,
        ha="center", va="center", fontweight="bold", zorder=5)

# divider under title
ax.plot([SB_X0 + 0.07, SB_X0 + SB_W - 0.07],
        [SB_Y0 + SB_H - 0.38, SB_Y0 + SB_H - 0.38],
        color=C_SB_BD, lw=0.6, alpha=0.6, zorder=4)

sb_lines = ["No network", "Read-only FS", "Whitelist ✓", "30 s timeout"]
for i, t in enumerate(sb_lines):
    ax.text(SB_CX, SB_Y0 + SB_H - 0.62 - i * 0.38,
            t, fontsize=6.1, ha="center", va="center",
            color=C_SB_BD, zorder=5)

# Short connector: right edge of Sandbox Executor → left edge of sandbox inset
arr(ax, T2_X0 + T2_W, t2_centers[3],    # right of Sandbox Executor box
        SB_X0,         SB_Y0 + SB_H / 2, # left of sandbox inset
    C_SB_BD, lw=0.9, zorder=4)


# ════════════════════════════════════════════════════════════════════════════════
# TIER 3 — DATA FABRIC  (5 boxes)
# ════════════════════════════════════════════════════════════════════════════════
T3_X0, T3_W, T3_H = 13.72, 3.42, 0.82
T3_CX = T3_X0 + T3_W / 2

t3_centers = [7.90, 6.72, 5.54, 4.36, 3.18]
t3_labels  = [
    "STAC Indexer",
    "Qdrant Vector DB",
    "Spatial Filter (bbox)",
    "Semantic Ranker",
    "Metadata Gate",
]

for yc, label in zip(t3_centers, t3_labels):
    rounded_rect(ax, (T3_X0, yc - T3_H / 2), T3_W, T3_H,
                 "white", C_DF_BD, lw=1.1, r=0.09, zorder=3)
    ax.text(T3_CX, yc, label,
            fontsize=7.8, ha="center", va="center", zorder=5)

for y0, y1 in zip(t3_centers[:-1], t3_centers[1:]):
    arr(ax, T3_CX, y0 - T3_H / 2,
            T3_CX, y1 + T3_H / 2,
        C_DF_BD, lw=1.1)


# ════════════════════════════════════════════════════════════════════════════════
# CROSS-ZONE ARROWS
# ════════════════════════════════════════════════════════════════════════════════

# ── 1. Proposal: T1 Code Generator  →  T2 Policy Engine ─────────────────────
PROP_Y = t1_centers[-1]    # 4.05 = Code Generator centre
arr(ax, T1_X0 + T1_W, PROP_Y,   # right edge of Code Generator
        T2_X0,          PROP_Y,  # left edge of T2 zone
    C_PROP, lw=2.0)
ax.text((T1_X0 + T1_W + T2_X0) / 2, PROP_Y + 0.28,
        "Declarative proposals only",
        fontsize=6.5, color=C_PROP, ha="center", va="bottom")

# ── 2. Prescription: T2  →  T1  (mandatory corrective instructions) ──────────
MAND_Y = t2_centers[0]    # 7.95 = Policy Engine centre
arr(ax, T2_X0,          MAND_Y,  # left edge of Policy Engine
        T1_X0 + T1_W,   MAND_Y,  # right edge of T1 zone
    C_MAND, lw=2.5)
ax.text((T1_X0 + T1_W + T2_X0) / 2, MAND_Y + 0.28,
        "Mandatory corrective prescriptions",
        fontsize=6.5, color=C_MAND,
        ha="center", va="bottom", fontweight="bold")

# ── 3. Schema: T3 Spatial Filter  →  T2 Validators (schema / IDs only) ──────
SCHEMA_Y = 5.45    # Code Rewriter / Validators level
arr(ax, T3_X0,           SCHEMA_Y,  # left edge of T3 boxes
        T2_X0 + T2_W,    SCHEMA_Y,  # right edge of T2 boxes
    C_DF_BD, lw=1.5)
ax.text((T2_X0 + T2_W + T3_X0) / 2, SCHEMA_Y + 0.22,
        "Schema & IDs only",
        fontsize=6.5, color=C_DF_BD, ha="center", va="bottom")


# ════════════════════════════════════════════════════════════════════════════════
# PROHIBITED PATHWAY INDICATOR
# (no direct Data Fabric → LLM raw-data channel)
# ════════════════════════════════════════════════════════════════════════════════
ax.plot([4.72, T3_BG_X0],
        [1.08, 1.08],
        color="#D8D8D8", lw=1.2, ls=":", zorder=2)
ax.text((4.72 + T3_BG_X0) / 2, 1.08,
        "✕  No direct Data Fabric → LLM pathway  (zero authority leakage)",
        fontsize=7.2, color=C_GATE_REJ,
        ha="center", va="center", fontweight="bold", zorder=4)


# ════════════════════════════════════════════════════════════════════════════════
# METRIC CALLOUT  (hero stats)
# ════════════════════════════════════════════════════════════════════════════════
CL_X0, CL_Y0, CL_W, CL_H = T2_BG_X0, 8.55, T2_BG_W - 0.10, 0.55
rounded_rect(ax, (CL_X0, CL_Y0), CL_W, CL_H,
             "#FFF6F6", C_GATE_REJ, lw=1.1, r=0.06, zorder=3)
ax.text(CL_X0 + CL_W / 2, CL_Y0 + CL_H / 2,
        "23 % initial proposal rejection rate   ·   100 % sandbox escape prevention",
        fontsize=7.5, ha="center", va="center",
        color=C_GATE_REJ, fontweight="bold", zorder=5)


# ════════════════════════════════════════════════════════════════════════════════
# TITLE & FOOTER
# ════════════════════════════════════════════════════════════════════════════════
fig.text(0.50, 0.977,
         "AutoCarto-Agent: Zero-Authority-Leakage Architecture",
         ha="center", va="top",
         fontsize=14, fontweight="bold", color="#111111")

fig.text(0.50, 0.015,
         "Amber zone: stochastic LLM reasoning  ·  "
         "Blue zone: deterministic enforcement  ·  "
         "Green zone: data infrastructure",
         ha="center", va="bottom", fontsize=8, color="#666666")


# ════════════════════════════════════════════════════════════════════════════════
# SAVE
# ════════════════════════════════════════════════════════════════════════════════
fig.tight_layout(rect=[0.0, 0.03, 1.0, 0.965])

for ext in ("png", "pdf"):
    out_path = OUT / f"architecture_boundary.{ext}"
    save_kw  = dict(bbox_inches="tight", facecolor="white")
    if ext == "png":
        save_kw["dpi"] = 300
    fig.savefig(out_path, **save_kw)
    print(f"Saved: {out_path}")

plt.close(fig)
print("Done.")
