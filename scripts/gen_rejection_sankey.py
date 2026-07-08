#!/usr/bin/env python3
"""gen_rejection_sankey.py — CartoLLM figure F-NEW-3 (rejection-flow Sankey).

Where naive proposals go: the deterministic gates route each verdict, and every
rejection to a specific mandated remedy. Driven ENTIRELY by the mini-benchmark
(autocarto.benchmark.build_report) — no fabricated flows — and asserted to sum
to the real scenario count, so the diagram cannot drift from the data.

Honest framing carried onto the figure:
  * The corpus is an ADVERSARIAL stress set (pathological by design), so the
    high rejection share is expected; it is not a natural rejection rate.
  * These are FIRST-PASS verdicts, not the full iterate-to-convergence loop.
  * Of the 6 Gate-3b approvals, 1 is a known false-approval (two independent
    spatially-autocorrelated fields correlating by chance — the documented
    free-permutation null-model limitation, research task R-2).

Usage:  python scripts/gen_rejection_sankey.py [--out DIR]
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, PathPatch
from matplotlib.path import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from autocarto.benchmark import build_report

_parser = argparse.ArgumentParser(description="CartoLLM rejection-flow Sankey")
_parser.add_argument("--out", default=os.path.join(REPO_ROOT, "output", "figures"))
_args = _parser.parse_args()
os.makedirs(_args.out, exist_ok=True)
mpl.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 300})

# ── 1. Aggregate real flows from the benchmark ────────────────────────────────
S = build_report()["scenarios"]
N = len(S)

g2_pass = sum(s["gate"] == "G2" and s["outcome"] == "PASS" for s in S)
g2_rej_by_method = Counter(
    s["prescribed_method"] for s in S if s["gate"] == "G2" and s["outcome"] == "REJECT")
g3b_accept = sum(s["gate"] == "G3b" and s["outcome"] in ("APPROVE", "WARN") for s in S)
g3b_rej = sum(s["gate"] == "G3b" and s["outcome"] == "REJECT" for s in S)
n_g2 = sum(s["gate"] == "G2" for s in S)
n_g3b = sum(s["gate"] == "G3b" for s in S)
g2_rej = sum(g2_rej_by_method.values())
# The known false-approval among G3b approvals (documented limitation).
g3b_false_approve = sum(
    s["gate"] == "G3b" and s["regime"] == "independent" and s["outcome"] != "REJECT" for s in S)

assert n_g2 + n_g3b == N
assert g2_pass + g2_rej == n_g2
assert g3b_accept + g3b_rej == n_g3b
print(f"N={N}  G2 pass/reject={g2_pass}/{g2_rej}  G3b accept/reject={g3b_accept}/{g3b_rej}"
      f"  (false-approvals={g3b_false_approve})")

# Nice labels for the four G2 prescriptions.
METHOD_LABEL = {
    "manual_break_at_zero_then_fisher_jenks": "break at 0 + Fisher-Jenks",
    "log_transform_then_jenks": "log-transform + Jenks",
    "arcsinh_transform_then_jenks": "arcsinh + Jenks",
    "unique_values": "unique-value classes",
}

# ── 2. Node + flow model ──────────────────────────────────────────────────────
C_ACCEPT = "#1e8449"
C_REJECT = "#c0392b"
C_NEUT = "#5b6b7a"
C_GATE = "#2760a7"
C_INK = "#1a1a2e"

# nodes: id -> dict(col, value, label, color, sublabel)
nodes: dict[str, dict] = {}
def add_node(nid, col, value, label, color, sub=""):
    nodes[nid] = dict(col=col, value=value, label=label, color=color, sub=sub,
                      used_out=0.0, used_in=0.0)

add_node("prop", 0, N, "naïve\nproposals", C_NEUT, sub=f"{N}")
add_node("g2", 1, n_g2, "Gate 2\nclassification", C_GATE, sub=f"{n_g2}")
add_node("g3b", 1, n_g3b, "Gate 3b\nbivariate", C_GATE, sub=f"{n_g3b}")
add_node("g2_acc", 2, g2_pass, "PASS", C_ACCEPT, sub=f"{g2_pass}")
add_node("g2_rej", 2, g2_rej, "REJECT", C_REJECT, sub=f"{g2_rej}")
add_node("g3b_acc", 2, g3b_accept, "APPROVE", C_ACCEPT, sub=f"{g3b_accept}")
add_node("g3b_rej", 2, g3b_rej, "REJECT", C_REJECT, sub=f"{g3b_rej}")
add_node("ships", 3, g2_pass, "map ships as proposed", C_ACCEPT, sub=f"{g2_pass}")
# four prescription remedy nodes, in a fixed order
_presc_order = ["manual_break_at_zero_then_fisher_jenks", "log_transform_then_jenks",
                "arcsinh_transform_then_jenks", "unique_values"]
for m in _presc_order:
    add_node(f"rx_{m}", 3, g2_rej_by_method[m], METHOD_LABEL[m], C_REJECT,
             sub=f"{g2_rej_by_method[m]}")
add_node("bivar", 3, g3b_accept, "bivariate map unlocked", C_ACCEPT, sub=f"{g3b_accept}")
add_node("uni", 3, g3b_rej, "mandate side-by-side univariate", C_REJECT, sub=f"{g3b_rej}")

# flows: (src, tgt, value, verdict-colour)
flows = [
    ("prop", "g2", n_g2, C_NEUT), ("prop", "g3b", n_g3b, C_NEUT),
    ("g2", "g2_acc", g2_pass, C_ACCEPT), ("g2", "g2_rej", g2_rej, C_REJECT),
    ("g3b", "g3b_acc", g3b_accept, C_ACCEPT), ("g3b", "g3b_rej", g3b_rej, C_REJECT),
    ("g2_acc", "ships", g2_pass, C_ACCEPT),
]
for m in _presc_order:
    flows.append(("g2_rej", f"rx_{m}", g2_rej_by_method[m], C_REJECT))
flows.append(("g3b_acc", "bivar", g3b_accept, C_ACCEPT))
flows.append(("g3b_rej", "uni", g3b_rej, C_REJECT))

# vertical order of nodes within each column (top -> bottom)
col_order = {
    0: ["prop"],
    1: ["g2", "g3b"],
    2: ["g2_acc", "g2_rej", "g3b_acc", "g3b_rej"],
    3: ["ships", "rx_manual_break_at_zero_then_fisher_jenks", "rx_log_transform_then_jenks",
        "rx_arcsinh_transform_then_jenks", "rx_unique_values", "bivar", "uni"],
}

# ── 3. Layout ─────────────────────────────────────────────────────────────────
UNIT = 0.030          # vertical height per scenario
GAP = 0.020           # gap between stacked nodes
NODE_W = 0.020
COL_X = {0: 0.115, 1: 0.35, 2: 0.575, 3: 0.775}
MID = 0.46

for col, ids in col_order.items():
    total = sum(nodes[i]["value"] for i in ids) * UNIT + (len(ids) - 1) * GAP
    top = MID + total / 2.0
    for i in ids:
        h = nodes[i]["value"] * UNIT
        nodes[i]["top"] = top
        nodes[i]["bottom"] = top - h
        top = top - h - GAP

fig = plt.figure(figsize=(14.5, 8.8), facecolor="white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")


def ribbon(x0, yt0, yb0, x1, yt1, yb1, color):
    cx = (x0 + x1) / 2.0
    verts = [(x0, yt0), (cx, yt0), (cx, yt1), (x1, yt1),
             (x1, yb1), (cx, yb1), (cx, yb0), (x0, yb0), (x0, yt0)]
    codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), facecolor=color, edgecolor="none",
                           alpha=0.42, zorder=1))


# draw flows (ordered so attach points stack top->bottom cleanly)
order_index = {nid: (nodes[nid]["col"], col_order[nodes[nid]["col"]].index(nid))
               for nid in nodes}
flows.sort(key=lambda f: (order_index[f[0]], order_index[f[1]]))
for src, tgt, val, color in flows:
    s, t = nodes[src], nodes[tgt]
    h = val * UNIT
    sy_t = s["top"] - s["used_out"]; sy_b = sy_t - h; s["used_out"] += h
    ty_t = t["top"] - t["used_in"]; ty_b = ty_t - h; t["used_in"] += h
    ribbon(COL_X[s["col"]] + NODE_W, sy_t, sy_b, COL_X[t["col"]], ty_t, ty_b, color)

# draw nodes + labels
for nid, nd in nodes.items():
    x = COL_X[nd["col"]]
    ax.add_patch(Rectangle((x, nd["bottom"]), NODE_W, nd["top"] - nd["bottom"],
                           facecolor=nd["color"], edgecolor="white", linewidth=0.6, zorder=3))
    ymid = (nd["top"] + nd["bottom"]) / 2.0
    if nd["col"] <= 2:                       # labels to the LEFT of the node
        ax.text(x - 0.008, ymid, nd["label"], ha="right", va="center",
                fontsize=9.5 if nd["col"] < 2 else 10.5,
                fontweight="bold", color=nd["color"], zorder=4)
        ax.text(x + NODE_W / 2, nd["top"] + 0.012, nd["sub"], ha="center", va="bottom",
                fontsize=8.5, color=nd["color"], fontweight="bold", zorder=4)
    else:                                    # remedy labels to the RIGHT
        ax.text(x + NODE_W + 0.008, ymid, f"{nd['label']}  ·  {nd['sub']}",
                ha="left", va="center", fontsize=9.2, color=nd["color"],
                fontweight="bold", zorder=4)

# column headers
for col, title in {0: "PROPOSAL", 1: "GATE", 2: "VERDICT", 3: "MANDATED OUTCOME"}.items():
    ax.text(COL_X[col] + NODE_W / 2, 0.895, title, ha="center", va="bottom",
            fontsize=10.5, fontweight="bold", color="#33404d", zorder=4)

# title + honest framing
fig.text(0.5, 0.975, "Where naïve proposals go — every rejection routed to a deterministic remedy",
         ha="center", va="top", fontsize=15.5, fontweight="bold", color=C_INK)
fig.text(0.5, 0.945,
         f"Mini-benchmark · {N} seeded naïve proposals · adversarial stress corpus (pathological by design)",
         ha="center", va="top", fontsize=9.5, color="#666")

fig.text(0.5, 0.052,
         "Driven by autocarto.benchmark.build_report() — no fabricated flows; counts sum to the real scenarios. "
         "The corpus is deliberately adversarial, so the rejection share is high by design, not a natural rate.",
         ha="center", va="top", fontsize=7.6, color="#8a8a8a")
fig.text(0.5, 0.034,
         "First-pass verdicts (not the full iterate-to-convergence loop). Of the 6 Gate-3b approvals, "
         f"{g3b_false_approve} is a known false-approval — two independent autocorrelated fields correlating by chance",
         ha="center", va="top", fontsize=7.6, color="#8a8a8a")
fig.text(0.5, 0.018,
         "(the documented free-permutation null-model limitation, research task R-2).",
         ha="center", va="top", fontsize=7.6, color="#8a8a8a")

png = os.path.join(_args.out, "rejection_sankey.png")
pdf = os.path.join(_args.out, "rejection_sankey.pdf")
fig.savefig(png, dpi=300, facecolor="white")
fig.savefig(pdf, facecolor="white")
plt.close(fig)
print(f"✓ PNG → {png}")
print(f"✓ PDF → {pdf}")
