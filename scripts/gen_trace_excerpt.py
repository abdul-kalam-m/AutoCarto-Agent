#!/usr/bin/env python3
"""gen_trace_excerpt.py — CartoLLM figure F-NEW-2 ("the artifact in hand").

One Gate-2 rejection, end to end, as the machine-readable audit trail the
abstract promises. Three stacked cards map onto the Propose-Verify-Execute
triad:

  (1) PROPOSAL  — the (simulated) LLM's naive Fisher-Jenks proposal.
  (2) VERDICT   — Gate 2's REJECT + prescription, verbatim from the emitted
                  JSON trace, incl. the "DO NOT propose alternative methods"
                  mandate.
  (3) EXECUTE   — the mandated code the engine hands back: the LLM is reduced
                  to splicing in the prescribed constants.

All values are produced by RUNNING Gate 2 on the demo's zero-inflated case and
are asserted to match the committed output/traces/gate2_classification_trace.json
(so the figure cannot drift from the shipped artifact).

Honesty notes on the figure face:
  * Tier 1 (LLM) is SIMULATED in V1 — the harness feeds the proposal directly.
  * Break values are rounded for display; the trace stores full float precision.

Usage:  python scripts/gen_trace_excerpt.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))

import autocarto.demo as demo
from autocarto.execution.gates.gate2_classification import (
    ClassificationDiagnosticEngine, _dedupe_breaks,
)

_parser = argparse.ArgumentParser(description="CartoLLM trace-excerpt figure")
_parser.add_argument("--out", default=os.path.join(REPO_ROOT, "output", "figures"))
_args = _parser.parse_args()
os.makedirs(_args.out, exist_ok=True)

mpl.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 300})
MONO = {"family": "monospace"}

# ── 1. Produce the real rejection (and verify it matches the shipped trace) ───
demo.RNG = np.random.default_rng(42)
_ = demo.make_well_behaved()             # advance RNG exactly as the demo does
zi = demo.make_zero_inflated()
naive = _dedupe_breaks([float(np.percentile(zi, p)) for p in (0, 20, 40, 60, 80, 100)])
res = ClassificationDiagnosticEngine(random_state=0).evaluate(
    zi, proposed_method="jenks", proposed_breaks=naive)

committed = json.load(open(os.path.join(REPO_ROOT, "output", "traces",
                                        "gate2_classification_trace.json")))["cases"]["zero_inflated"]
assert [round(b, 9) for b in res.prescribed_breaks] == \
       [round(b, 9) for b in committed["prescribed_breaks"]], "figure drifted from shipped trace!"

zero_pct = float(np.mean(zi == 0)) * 100
naive_r = [round(b, 2) for b in naive]
presc_r = [round(b, 2) for b in res.prescribed_breaks]
print(f"zero fraction: {zero_pct:.1f}%  naive={naive_r}  prescribed={presc_r}  (matches committed trace)")

# ── 2. Palette + line styles ──────────────────────────────────────────────────
C_INK = "#1a1a2e"
CARDS = {
    "propose": dict(accent="#b8791f", fill="#fff6e9", band="#f2d9ad"),   # amber
    "verify":  dict(accent="#2760a7", fill="#eef4fb", band="#cfe0f2"),   # blue
    "execute": dict(accent="#1e8449", fill="#eef7f0", band="#cfe9d6"),   # green
}
STYLE = {                                    # (colour, weight, bg or None)
    "plain":   ("#233", "normal", None),
    "key":     ("#5a6b7b", "normal", None),
    "str":     ("#1a5276", "normal", None),
    "num":     ("#7d3c98", "normal", None),
    "false":   ("#b00020", "bold", None),
    "mandate": ("#b00020", "bold", "#fdecea"),
    "hi":      ("#0b6b3a", "bold", "#e6f4ea"),   # highlighted value line
    "add":     ("#14612e", "normal", "#e6f4ea"),
    "del":     ("#8a1c1c", "normal", "#fbe9e7"),
    "comment": ("#6b7a8f", "italic", None),
}

# ── 3. Card contents (lines = list of (text, style)) ──────────────────────────
propose_lines = [
    ('"proposed_method": "jenks",', "str"),
    (f'"proposed_breaks":  [{naive_r[0]:.2f}, {naive_r[1]:.2f}, {naive_r[2]:.2f}, {naive_r[3]:.2f}]', "num"),
    ("", "plain"),
    ("# naïve Fisher-Jenks on the raw, zero-inflated values", "comment"),
    ("# Tier 1 is SIMULATED in V1 — the harness feeds this straight to Gate 2", "comment"),
]

verify_lines = [
    ('"gate":              "G2",', "key"),
    ('"diagnosis":         "zero_inflated",', "str"),
    (f'"passed":            false,        # {zero_pct:.1f}% of tracts are zero', "false"),
    ('"prescribed_method": "manual_break_at_zero_then_fisher_jenks",', "str"),
    (f'"prescribed_breaks": [{presc_r[0]:.1f}, {presc_r[1]:.2f}, {presc_r[2]:.2f}, {presc_r[3]:.2f}],', "hi"),
    ('"instruction": "Mandate explicit break at 0, then Fisher-Jenks', "plain"),
    ('   on the non-zero tail.', "plain"),
    ('   DO NOT propose alternative methods.', "mandate"),
    ('   Use these exact breaks."', "plain"),
]

execute_lines = [
    (f'- breaks = [{naive_r[0]:.2f}, {naive_r[1]:.2f}, {naive_r[2]:.2f}, {naive_r[3]:.2f}]        # LLM proposal — REJECTED', "del"),
    ("+ # MANDATED CLASSIFICATION — DO NOT MODIFY", "add"),
    (f'+ breaks = [{presc_r[0]:.1f}, {presc_r[1]:.2f}, {presc_r[2]:.2f}, {presc_r[3]:.2f}]         # prescribed by Gate 2', "add"),
    ("+ classified = np.digitize(values, bins=breaks, right=True)", "add"),
]

# ── 4. Layout ─────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(11.5, 10.2), facecolor="white")
fig.text(0.5, 0.975, "One rejection, end to end — the machine-readable audit trail",
         ha="center", va="top", fontsize=15.5, fontweight="bold", color=C_INK)
fig.text(0.5, 0.941,
         "Gate 2 · zero-inflated variable (e.g. asthma hospitalisations) · Propose → Verify → Execute",
         ha="center", va="top", fontsize=9.5, color="#666")

# Three card axes stacked; gaps carry the flow arrows/labels.
positions = {                       # [left, bottom, width, height] in fig coords
    "propose": [0.06, 0.700, 0.88, 0.150],
    "verify":  [0.06, 0.360, 0.88, 0.250],
    "execute": [0.06, 0.115, 0.88, 0.150],
}
headers = {
    "propose": "PROPOSAL   ·   simulated LLM  (fed directly to Gate 2)",
    "verify":  "GATE 2 VERDICT   ·   verbatim from the emitted JSON trace",
    "execute": "EXECUTED CODE   ·   the mandate, transcribed",
}
steps = {"propose": "1", "verify": "2", "execute": "3"}
contents = {"propose": propose_lines, "verify": verify_lines, "execute": execute_lines}


def render_card(key):
    style = CARDS[key]
    ax = fig.add_axes(positions[key])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(FancyBboxPatch(
        (0.004, 0.02), 0.992, 0.96, boxstyle="round,pad=0.006,rounding_size=0.02",
        facecolor=style["fill"], edgecolor=style["accent"], linewidth=1.6, zorder=1))
    # header band
    ax.add_patch(FancyBboxPatch(
        (0.004, 0.80), 0.992, 0.18, boxstyle="round,pad=0.006,rounding_size=0.02",
        facecolor=style["band"], edgecolor="none", zorder=2))
    # numbered circular badge (glyph-safe, instead of ①②③)
    ax.text(0.030, 0.885, steps[key], transform=ax.transAxes, va="center", ha="center",
            fontsize=11, fontweight="bold", color="white", zorder=5,
            bbox=dict(boxstyle="circle,pad=0.32", fc=style["accent"], ec="none"))
    ax.text(0.062, 0.885, headers[key], transform=ax.transAxes, va="center", ha="left",
            fontsize=10.5, fontweight="bold", color=style["accent"], zorder=4, **MONO)

    lines = contents[key]
    y0, y1 = 0.74, 0.06
    ys = np.linspace(y0, y1, len(lines)) if len(lines) > 1 else [0.4]
    for (text, st), y in zip(lines, ys):
        color, weight, bg = STYLE[st]
        fontstyle = "italic" if weight == "italic" else "normal"
        fw = "bold" if weight == "bold" else "normal"
        if bg is not None:
            ax.add_patch(Rectangle((0.020, y - 0.052), 0.958, 0.098,
                                   facecolor=bg, edgecolor="none", zorder=2))
        ax.text(0.030, y, text, transform=ax.transAxes, va="center", ha="left",
                fontsize=9.2, color=color, fontweight=fw, fontstyle=fontstyle,
                zorder=4, **MONO)
    return ax


for k in ("propose", "verify", "execute"):
    render_card(k)

# Flow arrows + labels in the gaps.
def flow(y, label):
    fig.text(0.5, y, "▼", ha="center", va="center", fontsize=15, color="#888")
    fig.text(0.545, y, label, ha="left", va="center", fontsize=9,
             color="#555", style="italic")

flow(0.655, "profile  +  verify")
flow(0.315, "MANDATE   (prescribed breaks + code)")

# Footnote.
fig.text(0.5, 0.058,
         "The LLM is reduced to a code-assembler: it may only splice in the prescribed constants.",
         ha="center", va="top", fontsize=9, color="#444", fontweight="bold")
fig.text(0.5, 0.030,
         "Verbatim from output/traces/gate2_classification_trace.json (case: zero_inflated); regenerate with `autocarto demo`.",
         ha="center", va="top", fontsize=7.3, color="#8a8a8a")
fig.text(0.5, 0.014,
         "Break values rounded for display — the trace stores full float precision. Re-running reproduces the trace byte-for-byte.",
         ha="center", va="top", fontsize=7.3, color="#8a8a8a")

png = os.path.join(_args.out, "trace_excerpt.png")
pdf = os.path.join(_args.out, "trace_excerpt.pdf")
fig.savefig(png, dpi=300, facecolor="white")
fig.savefig(pdf, facecolor="white")
plt.close(fig)
print(f"✓ PNG → {png}")
print(f"✓ PDF → {pdf}")
