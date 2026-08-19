# Claim Support Map — every quantitative claim traced to evidence

Regenerate-command column lets a reviewer (or the author, before submission) reproduce each number independently.

| § | Claim as written | Value | Evidence | Regenerate |
|---|---|---|---|---|
| Abstract, 6.1 | Decision accuracy on ground-truth corpus | 38/39 = 97.4% | 42-scenario benchmark, 3 borderline unscored | `autocarto benchmark` |
| 6.1 | Benign inputs correct | 17/17 | same | same |
| 6.1 | Pathological inputs correct | 21/22 | same | same |
| 6.1 | Rejection rate (corpus-dependent) | 22/42 = 52.4% | same | same |
| 6.1 | Rejections by cause | 10 categories itemised | same | same |
| 6.2 | Controlled case size | 530 tracts | TIGER Fulton+DeKalb, pinned | `scripts/gen_results_panel.py` |
| 6.2, Abstract | GVF improvement, variable 1 | 0.7514 → 0.8348 | same | same |
| 6.2, Abstract | GVF improvement, variable 2 | 0.7741 → 0.8607 | same | same |
| 6.2 | Bivariate Moran's I_xy (controlled) | +0.3262, p = 0.0050, 199 perms | same | same |
| 6.2 | Spearman ρ (controlled) | +0.9471 | same | same |
| 6.3, Abstract | Unconstrained class collapse | 414/530 = 78% | ablation | `scripts/gen_ungated_vs_gated.py` |
| 6.3, Abstract | Gated class balance | [98/134/145/90/63] | same | same |
| 6.3 | **Counter-result**: rejected scheme has higher GVF | 0.866 vs 0.835 | same | same |
| 6.4, Abstract | Real-data case size | 519 of 530 (11 dropped, not imputed) | ACS + CDC join | `load_real_atlanta_dataset()` |
| 6.4, Abstract | Real bivariate I_xy | −0.5555 (reported −0.56), p = 0.005 | orchestrator run | `Orchestrator.run(...)` |
| 6.4, Abstract | Real Spearman ρ | −0.7758 (reported −0.78) | same | same |
| 6.4 | Income univariate clustering | Moran's I = 0.59, p = 0.001 | same | same |
| 6.5 | Gate 3a ROC AUC | 0.9149 (n = 240) | threshold sweep | `output/threshold_sensitivity_report.json` |
| 6.5 | Gate 3b ROC AUC, I_xy | 0.9569 (n = 165) | same | same |
| 6.5 | Gate 3b ROC AUC, ρ | 0.9978 (n = 165) | same | same |
| 6.6, Abstract | Mean p-value inflation, independent regime | 18.97× | null-model study, 999 perms | `output/gate3b_null_model_comparison.json` |
| 6.6 | Free permutation FP / FN | 2 / 0 | same | same |
| 6.6 | Toroidal shift FP / FN | 1 / 1 | same | same |
| 6.7 | Red-team vectors blocked | 27 / 27 tested | sanitizer disabled, real gVisor in CI | `pytest tests/security/test_escapes.py` |
| 5 | Test suite | 236 passing, 33 skipped | full suite | `pytest` |
| 5 | Byte-identical **gate verdicts** | scope-limited to 2 of 4 trace files | determinism check | run twice, diff the two verdict files by name |

## Claims deliberately NOT made (retired or unmeasured)

| Retired/absent claim | Why | Where it came from |
|---|---|---|
| "23% of proposals rejected" | Never reproducible; no corpus supported it | `Abstract_revised.txt` (conference abstract) — **filtered out** |
| "100% of sandbox escapes blocked" | Unfalsifiable universal; replaced by "27 of 27 tested" | `Abstract_revised.txt` — **filtered out** |
| Test coverage percentage | No coverage tool ever run | — |
| "Core validation < 3 s" | Omitted from the paper: adds little in print and the measurement scope (internal timer vs. total command latency, 3.5–6 s) invites a stopwatch objection | Poster/demo material |
| Any human-preference or comprehension result | No human-subject study conducted | — |
| Threshold optimality for G2 / G4 | No independent ground truth exists | — |

## Verification status

All quantitative claims above were re-run or re-read on **2026-07-28 / 2026-08-11**. No number in the manuscript is carried from memory or from an earlier document without re-verification, with one exception noted in `COVERAGE_GAPS.md` (Figure 6's corpus vintage).
