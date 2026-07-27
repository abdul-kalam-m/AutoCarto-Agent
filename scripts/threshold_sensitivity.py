#!/usr/bin/env python3
"""threshold_sensitivity.py — TD-8: converting arbitrary constants into a
researched calibration.

Sweeps the four numeric decision thresholds most likely to draw reviewer
scrutiny: Gate 2's GVF floor (0.6), Gate 3a's |I| floor (0.10), Gate 3b's
APPROVE/WARN cutoffs (|I_xy|>0.15 & |rho|>0.20 / |I_xy|>0.08 & |rho|>0.10),
and Gate 4's areal-exaggeration ceiling (20%).

Two different kinds of "sensitivity" are honestly kept separate, because
they answer different questions:

  - Gate 3a and Gate 3b have an INDEPENDENT ground truth: the SAR
    generating process's own rho / mixing-weight parameter is known by
    construction, so these get real ROC-style TPR/FPR curves and an AUC —
    "does the threshold correctly separate structured from unstructured
    data."
  - Gate 2 and Gate 4 do NOT have an independent "correct answer" beyond
    the threshold itself — there is no ground truth for "is 0.6 GVF good
    enough" or "is 20% areal exaggeration acceptable" other than
    convention. These instead get honestly-labeled RATE curves: what
    fraction of correctly-prescribed classifications would still pass at
    each candidate threshold (G2), and what fraction of a representative
    CRS/AOI sample would be rejected at each candidate ceiling (G4).
    Reporting these as if they were accuracy curves would fabricate a
    ground truth that does not exist.

Every internal statistic is computed via the actual gate modules' own
functions (SpatialStructureGate._morans_i, BivariateCorrelationGate.
_bivariate_morans_i, gate4's _sample_areal_scales, and
ClassificationDiagnosticEngine.evaluate itself for G2) — not
reimplementations — so the sweep can never silently drift from what the
shipped gates actually compute.

Run:  python scripts/threshold_sensitivity.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO_ROOT / "src"))

from autocarto.demo import make_grid_polygons, spatial_autoregressive
from autocarto.execution.gates.gate2_classification import ClassificationDiagnosticEngine
from autocarto.execution.gates.gate3a_spatial_autocorrelation import SpatialStructureGate
from autocarto.execution.gates.gate3b_bivariate_correlation import BivariateCorrelationGate
from autocarto.execution.gates.gate4_projection_distortion import _sample_areal_scales
from autocarto.config import THRESHOLDS

GRID_N = 16
CONUS_BOUNDS = (-125.0, 24.5, -66.9, 49.4)
GA_BOUNDS = (-85.6, 30.4, -80.8, 35.0)
EQUATOR_BOUNDS = (-10.0, -10.0, 10.0, 10.0)
ALASKA_BOUNDS = (-170.0, 55.0, -130.0, 72.0)


# ══════════════════════════════════════════════════════════════════════════
# Gate 3a — TRUE ROC (ground truth: SAR rho used to generate the field)
# ══════════════════════════════════════════════════════════════════════════

def sweep_gate3a(seeds_per_rho: int = 20) -> List[Dict[str, Any]]:
    _, W, _ = make_grid_polygons(GRID_N, GRID_N)
    N = W.shape[0]
    W_sum = float(W.sum())
    rho_values = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    records = []
    seed_counter = 5000
    for rho in rho_values:
        for _ in range(seeds_per_rho):
            x = spatial_autoregressive(W, rho=rho, seed=seed_counter)
            seed_counter += 1
            z = x - float(x.mean())
            zz = float(z @ z)
            if zz < 1e-12:
                continue
            I = SpatialStructureGate._morans_i(z, W, N, W_sum)
            records.append({
                "rho_gen": rho, "morans_i": float(I),
                # |rho_gen| >= 0.15 is the "meaningfully structured" cutoff for
                # ground truth -- below that, the SAR field is empirically
                # indistinguishable from noise regardless of what Gate 3a says.
                "has_structure": rho >= 0.15,
            })
    return records


# ══════════════════════════════════════════════════════════════════════════
# Gate 3b — TRUE ROC (ground truth: SAR coupling mixing weight)
# ══════════════════════════════════════════════════════════════════════════

def sweep_gate3b(seeds_per_mix: int = 15) -> List[Dict[str, Any]]:
    _, W, _ = make_grid_polygons(GRID_N, GRID_N)
    N = W.shape[0]
    W_sum = float(W.sum())
    mix_values = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    records = []
    seed_counter = 6000

    def zscore(v):
        return (v - v.mean()) / v.std()

    for mix in mix_values:
        for _ in range(seeds_per_mix):
            common = spatial_autoregressive(W, rho=0.75, seed=seed_counter)
            x_indep = spatial_autoregressive(W, rho=0.75, seed=seed_counter + 1)
            y_indep = spatial_autoregressive(W, rho=0.75, seed=seed_counter + 2)
            seed_counter += 3
            x = mix * common + (1 - mix) * x_indep
            y = mix * common + (1 - mix) * y_indep
            x_std, y_std = zscore(x), zscore(y)
            I_xy = BivariateCorrelationGate._bivariate_morans_i(x_std, y_std, W, N, W_sum)
            from scipy.stats import spearmanr
            rho_sp, _ = spearmanr(x, y)
            records.append({
                "mix": mix, "bivariate_morans_i": float(I_xy), "spearman_rho": float(rho_sp),
                # mix >= 0.5 means the shared component dominates -- ground
                # truth for "these variables are genuinely coupled."
                "should_approve": mix >= 0.5,
            })
    return records


# ══════════════════════════════════════════════════════════════════════════
# ROC / threshold-sweep helper (shared by G3a and G3b)
# ══════════════════════════════════════════════════════════════════════════

def roc_sweep(records: List[Dict[str, Any]], score_key: str, truth_key: str,
              thresholds: List[float]) -> List[Dict[str, Any]]:
    out = []
    n = len(records)
    for t in thresholds:
        tp = sum(1 for r in records if abs(r[score_key]) >= t and r[truth_key])
        fn = sum(1 for r in records if abs(r[score_key]) < t and r[truth_key])
        fp = sum(1 for r in records if abs(r[score_key]) >= t and not r[truth_key])
        tn = sum(1 for r in records if abs(r[score_key]) < t and not r[truth_key])
        tpr = tp / (tp + fn) if (tp + fn) else float("nan")
        fpr = fp / (fp + tn) if (fp + tn) else float("nan")
        out.append({
            "threshold": t, "tpr": tpr, "fpr": fpr,
            "accuracy": (tp + tn) / n if n else float("nan"),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        })
    return out


def auc_from_roc(roc: List[Dict[str, Any]]) -> float:
    """Trapezoidal-rule AUC from (fpr, tpr) pairs.

    Sorted by (fpr, tpr) ascending, NOT fpr alone: many thresholds commonly
    tie on fpr (e.g. every threshold above the highest negative score gives
    fpr=0 while tpr keeps climbing as it crosses positive scores). Sorting
    by fpr alone leaves ties in their original threshold-sweep order, which
    is descending-threshold = descending-tpr -- the wrong direction, so the
    trapezoidal rule silently integrates the *lower* edge of the tied
    segment instead of the upper one and undercounts the AUC. Caught by
    tests/test_threshold_sensitivity.py::test_roc_sweep_perfect_separator
    (a 3-threshold case where this returned 0.5 instead of the true 1.0).
    """
    pts = sorted(((r["fpr"], r["tpr"]) for r in roc if r["fpr"] == r["fpr"]), key=lambda p: (p[0], p[1]))
    if len(pts) < 2:
        return float("nan")
    area = 0.0
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        area += (x1 - x0) * (y0 + y1) / 2.0
    return float(area)


# ══════════════════════════════════════════════════════════════════════════
# Gate 2 — rate curve (no independent ground truth beyond the threshold)
# ══════════════════════════════════════════════════════════════════════════

def sweep_gate2(n_per_regime: int = 40) -> List[Dict[str, Any]]:
    """For each known regime, run the REAL two-call orchestrator pattern
    (naive proposal -> prescription -> transcribed re-evaluation) and
    record the GVF the correctly-prescribed classification actually
    achieves. This is the gate's real code path, not a reimplementation.
    """
    rng_master = np.random.default_rng(9000)
    regimes = {
        "well_behaved": lambda rng: rng.normal(50, 12, 243).clip(0, 100),
        "zero_inflated": lambda rng: _zero_inflated(rng),
        "heavy_right_skew": lambda rng: rng.lognormal(10, 1.2, 243),
        "discrete_ordinal": lambda rng: rng.choice([1, 2, 3, 4, 5], size=243, p=[.3, .3, .2, .15, .05]).astype(float),
        "negative_right_skew": lambda rng: rng.chisquare(df=2, size=243) - 0.8,
    }
    records = []
    for regime_name, gen in regimes.items():
        for _ in range(n_per_regime):
            seed = int(rng_master.integers(0, 2**31))
            values = gen(np.random.default_rng(seed))

            engine1 = ClassificationDiagnosticEngine(random_state=0)
            naive = engine1.evaluate(values, proposed_method="jenks")
            if naive.passed:
                gvf = naive.gvf
            else:
                engine2 = ClassificationDiagnosticEngine(random_state=0)
                mandated = engine2.evaluate(
                    values, proposed_method=naive.prescribed_method,
                    proposed_breaks=naive.prescribed_breaks,
                )
                gvf = mandated.gvf
            records.append({"regime": regime_name, "gvf": float(gvf)})
    return records


def _zero_inflated(rng) -> np.ndarray:
    zeros = np.zeros(121)
    tail = rng.pareto(2.0, 122) * 5 + 1
    arr = np.concatenate([zeros, tail])
    rng.shuffle(arr)
    return arr


def rate_curve_gate2(records: List[Dict[str, Any]], thresholds: List[float]) -> Dict[str, List[Dict[str, Any]]]:
    """Per-regime: fraction of correctly-prescribed classifications that
    would still PASS at each candidate GVF threshold."""
    by_regime: Dict[str, List[float]] = {}
    for r in records:
        by_regime.setdefault(r["regime"], []).append(r["gvf"])

    out = {}
    for regime, gvfs in by_regime.items():
        arr = np.array(gvfs)
        curve = [{"threshold": t, "pass_rate": float((arr >= t).mean())} for t in thresholds]
        out[regime] = curve
    return out


# ══════════════════════════════════════════════════════════════════════════
# Gate 4 — rate curve (deterministic physics; no ground truth needed, but
# no "correct" ceiling exists independent of policy choice either)
# ══════════════════════════════════════════════════════════════════════════

def sweep_gate4() -> List[Dict[str, Any]]:
    candidates = [
        ("web_mercator_equator", 3857, EQUATOR_BOUNDS),
        ("web_mercator_georgia", 3857, GA_BOUNDS),
        ("web_mercator_conus", 3857, CONUS_BOUNDS),
        ("web_mercator_alaska", 3857, ALASKA_BOUNDS),
        ("albers_conus", 5070, CONUS_BOUNDS),
        ("albers_georgia", 5070, GA_BOUNDS),
        ("equal_earth_global", 8857, (-179.0, -60.0, 179.0, 75.0)),
    ]
    records = []
    for name, epsg, bounds in candidates:
        scales = _sample_areal_scales(epsg, bounds, resolution=10)
        if len(scales) == 0:
            continue
        max_exag = float(np.abs(scales - 1.0).max())
        records.append({"scenario": name, "epsg": epsg, "max_areal_exaggeration": max_exag})
    return records


def rate_curve_gate4(records: List[Dict[str, Any]], thresholds: List[float]) -> List[Dict[str, Any]]:
    """Fraction of the representative CRS/AOI sample rejected at each
    candidate areal-exaggeration ceiling."""
    exags = np.array([r["max_areal_exaggeration"] for r in records])
    return [{"threshold": t, "rejection_rate": float((exags > t).mean())} for t in thresholds]


# ══════════════════════════════════════════════════════════════════════════
# Report + figure
# ══════════════════════════════════════════════════════════════════════════

def build_report() -> Dict[str, Any]:
    g3a_records = sweep_gate3a()
    g3a_thresholds = [round(t, 3) for t in np.arange(0.0, 0.51, 0.02)]
    g3a_roc = roc_sweep(g3a_records, "morans_i", "has_structure", g3a_thresholds)
    g3a_auc = auc_from_roc(g3a_roc)

    g3b_records = sweep_gate3b()
    g3b_thresholds = [round(t, 3) for t in np.arange(0.0, 0.61, 0.02)]
    g3b_roc_ixy = roc_sweep(g3b_records, "bivariate_morans_i", "should_approve", g3b_thresholds)
    g3b_roc_rho = roc_sweep(g3b_records, "spearman_rho", "should_approve", g3b_thresholds)
    g3b_auc_ixy = auc_from_roc(g3b_roc_ixy)
    g3b_auc_rho = auc_from_roc(g3b_roc_rho)

    g2_records = sweep_gate2()
    g2_thresholds = [round(t, 2) for t in np.arange(0.3, 0.96, 0.05)]
    g2_rates = rate_curve_gate2(g2_records, g2_thresholds)

    g4_records = sweep_gate4()
    g4_thresholds = [round(t, 2) for t in np.arange(0.02, 0.81, 0.02)]
    g4_rates = rate_curve_gate4(g4_records, g4_thresholds)

    return {
        "sweep": "autocarto-threshold-sensitivity",
        "version": 1,
        "gate3a": {
            "kind": "roc", "current_threshold": THRESHOLDS.gate3a.reject_below_abs_i,
            "auc": g3a_auc, "n_samples": len(g3a_records), "roc": g3a_roc,
            "note": "Ground truth = SAR generation rho >= 0.15. Real ROC.",
        },
        "gate3b": {
            "kind": "roc",
            "current_threshold_ixy": THRESHOLDS.gate3b.approve_i_threshold,
            "current_threshold_rho": THRESHOLDS.gate3b.approve_rho_threshold,
            "auc_ixy": g3b_auc_ixy, "auc_rho": g3b_auc_rho, "n_samples": len(g3b_records),
            "roc_ixy": g3b_roc_ixy, "roc_rho": g3b_roc_rho,
            "note": "Ground truth = SAR coupling mixing weight >= 0.5. Real ROC.",
        },
        "gate2": {
            "kind": "rate_curve", "current_threshold": THRESHOLDS.gate2.gvf_threshold,
            "n_samples": len(g2_records), "pass_rate_by_regime": g2_rates,
            "note": (
                "No independent ground truth exists for 'good enough "
                "classification' beyond GVF itself -- this shows what "
                "fraction of CORRECTLY-PRESCRIBED classifications survive "
                "each candidate threshold, per regime, not an accuracy curve."
            ),
        },
        "gate4": {
            "kind": "rate_curve", "current_threshold": THRESHOLDS.gate4.max_areal_exaggeration,
            "scenarios": g4_records, "rejection_rate_curve": g4_rates,
            "note": (
                "No independent ground truth exists for 'acceptable "
                "distortion' beyond policy choice -- this shows rejection "
                "rate across a representative CRS/AOI sample at each "
                "candidate ceiling, not an accuracy curve."
            ),
        },
    }


def render_figure(report: Dict[str, Any], out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # G3a ROC
    ax = axes[0, 0]
    roc = report["gate3a"]["roc"]
    ax.plot([r["fpr"] for r in roc], [r["tpr"] for r in roc], "-o", ms=3, color="#2760a7")
    ax.plot([0, 1], [0, 1], "--", color="0.7", lw=1)
    cur = report["gate3a"]["current_threshold"]
    cur_pt = min(roc, key=lambda r: abs(r["threshold"] - cur))
    ax.plot(cur_pt["fpr"], cur_pt["tpr"], "*", ms=18, color="#c0392b",
            label=f"current |I| > {cur} (AUC={report['gate3a']['auc']:.3f})")
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
    ax.set_title("Gate 3a: |I| threshold ROC (ground truth = SAR rho)")
    ax.legend(fontsize=8); ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)

    # G3b ROC (I_xy)
    ax = axes[0, 1]
    roc = report["gate3b"]["roc_ixy"]
    ax.plot([r["fpr"] for r in roc], [r["tpr"] for r in roc], "-o", ms=3, color="#2f7c45")
    ax.plot([0, 1], [0, 1], "--", color="0.7", lw=1)
    cur = report["gate3b"]["current_threshold_ixy"]
    cur_pt = min(roc, key=lambda r: abs(r["threshold"] - cur))
    ax.plot(cur_pt["fpr"], cur_pt["tpr"], "*", ms=18, color="#c0392b",
            label=f"current |I_xy| > {cur} (AUC={report['gate3b']['auc_ixy']:.3f})")
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
    ax.set_title("Gate 3b: |I_xy| threshold ROC (ground truth = SAR coupling)")
    ax.legend(fontsize=8); ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)

    # G2 rate curves per regime
    ax = axes[1, 0]
    for regime, curve in report["gate2"]["pass_rate_by_regime"].items():
        ax.plot([c["threshold"] for c in curve], [c["pass_rate"] for c in curve],
                "-", label=regime, lw=1.5)
    ax.axvline(report["gate2"]["current_threshold"], ls="--", color="0.3", lw=1,
              label=f"current = {report['gate2']['current_threshold']}")
    ax.set_xlabel("Candidate GVF threshold"); ax.set_ylabel("Fraction still PASSing")
    ax.set_title("Gate 2: pass-rate of correctly-prescribed fits (not accuracy)")
    ax.legend(fontsize=7, loc="lower left")

    # G4 rejection rate curve
    ax = axes[1, 1]
    curve = report["gate4"]["rejection_rate_curve"]
    x_max = max(c["threshold"] for c in curve)  # sweep range only -- do not let
                                                  # an extreme scenario value (e.g.
                                                  # Alaska/Web Mercator at 947%)
                                                  # stretch the axis and squash
                                                  # everything else into a sliver
    ax.plot([c["threshold"] for c in curve], [c["rejection_rate"] for c in curve],
            "-", color="#8e44ad")
    ax.axvline(report["gate4"]["current_threshold"], ls="--", color="0.3", lw=1,
              label=f"current = {report['gate4']['current_threshold']:.0%}")
    off_scale = []
    for s in report["gate4"]["scenarios"]:
        v = s["max_areal_exaggeration"]
        if v <= x_max:
            ax.axvline(v, ls=":", color="0.8", lw=0.8, zorder=0)
        else:
            off_scale.append(f"{s['scenario']}={v:.0%}")
    ax.set_xlim(0, x_max)
    ax.set_xlabel("Candidate areal-exaggeration ceiling"); ax.set_ylabel("Rejection rate across sample")
    title = "Gate 4: rejection rate vs. ceiling (7-scenario CRS/AOI sample)"
    ax.set_title(title)
    if off_scale:
        ax.text(0.98, 0.98, "off-scale: " + ", ".join(off_scale), transform=ax.transAxes,
                ha="right", va="top", fontsize=6.5, color="0.4")
    ax.legend(fontsize=8, loc="center right")

    fig.suptitle("AutoCarto-Agent — Threshold Sensitivity (TD-8)", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path.with_suffix(".png"), dpi=200, facecolor="white")
    fig.savefig(out_path.with_suffix(".pdf"), facecolor="white")
    plt.close(fig)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Threshold sensitivity sweep (TD-8)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output")
    args = parser.parse_args(argv)

    print("Running Gate 3a sweep (SAR rho ground truth)...")
    print("Running Gate 3b sweep (SAR coupling ground truth)...")
    print("Running Gate 2 sweep (per-regime achieved GVF)...")
    print("Running Gate 4 sweep (representative CRS/AOI sample)...")
    report = build_report()

    (args.out / "threshold_sensitivity_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8",
    )
    fig_path = args.out / "figures" / "threshold_sensitivity"
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    render_figure(report, fig_path)

    print(f"\nGate 3a AUC: {report['gate3a']['auc']:.3f} (current |I|>{report['gate3a']['current_threshold']})")
    print(f"Gate 3b AUC (I_xy): {report['gate3b']['auc_ixy']:.3f}  AUC (rho): {report['gate3b']['auc_rho']:.3f}")
    print(f"Gate 2 pass-rate at current threshold ({report['gate2']['current_threshold']}):")
    for regime, curve in report["gate2"]["pass_rate_by_regime"].items():
        at_cur = min(curve, key=lambda c: abs(c["threshold"] - report["gate2"]["current_threshold"]))
        print(f"  {regime}: {at_cur['pass_rate']:.1%}")
    print(f"Gate 4 scenarios (current ceiling {report['gate4']['current_threshold']:.0%}):")
    for s in report["gate4"]["scenarios"]:
        verdict = "REJECT" if s["max_areal_exaggeration"] > report["gate4"]["current_threshold"] else "PASS"
        print(f"  {s['scenario']}: {s['max_areal_exaggeration']:.1%} -> {verdict}")
    print(f"\n-> {args.out / 'threshold_sensitivity_report.json'}")
    print(f"-> {fig_path.with_suffix('.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
