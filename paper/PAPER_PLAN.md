# PAPER PLAN — AutoCarto-Agent

**Status:** DRAFT plan · **Date:** 2026-07-28
**Target venue:** *None selected.* Written to a top-tier international GIScience journal standard (rigor, evidence discipline, structure). No venue is named, and no venue-specific formatting or fit argument appears anywhere in this plan or its downstream artifacts.
**Manuscript type:** Full research paper (systems + evaluation), ~8,000–10,000 words.
**Output location:** `paper/` — deliberately *not* `output/`, because `output/figures/` holds the verified poster figures and must not be overwritten.

---

## §0. Evidence provenance and integrity rules

Every number in this plan traces to one of the following, re-verified on 2026-07-28:

| Source | What it grounds | Verification |
|---|---|---|
| `autocarto benchmark` (re-run fresh) | 42-scenario corpus, 97.4% (38/39) | Re-run this session; output captured |
| `Orchestrator.run()` on `load_real_atlanta_dataset()` | 519 tracts, I_xy=−0.5555, ρ=−0.7758, p=0.005 | Re-run this session |
| `scripts/gen_results_panel.py` | 530 tracts, GVF 0.7514→0.8348 / 0.7741→0.8607, I_xy=+0.3262, ρ=+0.9471 | Re-run this session |
| `scripts/gen_ungated_vs_gated.py` | 414/530 (78%) collapse; balanced [98/134/145/90/63] | Re-run this session |
| `output/threshold_sensitivity_report.json` | G3a AUC 0.9149 (n=240); G3b AUC_I 0.9569 / AUC_ρ 0.9978 (n=165) | Read this session |
| `output/gate3b_null_model_comparison.json` | free-perm 2 FP → toroidal 1 FP; 0 FN → 1 FN; 18.97× mean p-inflation; 999 perms | Read this session |
| `tests/security/test_escapes.py` + `gvisor-security` CI job | 27/27 red-team vectors blocked | Poster copy §11, CI-verified |
| `pytest` full suite | 236 passing, 33 skipped | Re-run this session |
| `Fable Review/05_LITERATURE_STUDY_GUIDE.md` | Related-work citations | 🔎 verified w/ URL vs 📖 needs edition check |

**Hard rules carried into every downstream phase:**

1. **Two claims are retired and must never reappear.** `Abstract_revised.txt` (the original conference abstract) contains *"The validation suite rejected 23 percent of initial LLM proposals"* and *"100 percent of attempted sandbox escapes … were blocked."* Both were withdrawn as unfalsifiable/overclaimed. The manuscript uses the 42-scenario benchmark and "27 of 27 tested vectors" instead. Any reuse of abstract text must be filtered for these.
2. **No fabricated citations.** Sources marked 📖 in the literature guide are real works but their exact edition/year/pages were never confirmed; they carry `[CITE-VERIFY: ...]` in the draft rather than a fabricated bibliography entry.
3. **Scope statements are load-bearing**, not hedging. The limitations in §17 are claims about what was *not* measured, and they are as verified as the positive results.

---

## §1. One-paragraph summary

Large language models can already write fluent geospatial code, but fluency is not validity: LLM-authored thematic maps routinely misclassify skewed distributions, select area-distorting projections, and apply bivariate encodings to variable pairs with no spatial cross-correlation. The field's response has been to make agents more *capable*; we argue the missing property is *correctness of the output artifact*, and that cartographic correctness is computable rather than a matter of model judgment. AutoCarto-Agent is a neuro-symbolic architecture that removes the LLM's statistical authority entirely: the model proposes map type, visual variables, and template, while a deterministic engine computes every numeric decision, vetoes invalid proposals, and — the mechanism that makes the loop converge — returns an executable *prescription* (mandated method plus precomputed constants) rather than a bare rejection. Across a 42-scenario ground-truth corpus spanning six validation gates, the engine reaches the correct decision in 38 of 39 scored cases (97.4%), with the single miss disclosed and traced to a known null-model limitation.

## §2. One-sentence claim

> Deterministic validation with prescriptive rejection can hold veto authority over a generative model in thematic cartography, converting an unbounded revision loop into bounded transcription, without degrading the agent's ability to produce maps that are statistically defensible on real data.

---

## §3. Research gap

The 2025–2026 autonomous-GIS wave (LLM-Geo and the autonomous-GIS agenda; GIS Copilot; LLM-Find; CartoAgent; the GeoAnalystBench/GeoBenchX benchmark line) has converged on **capability** as the evaluation axis: can the agent decompose the task, does the generated code execute, does a plausible map appear. Correctness of the produced artifact is either assumed from execution success or delegated to model judgment.

Three specific gaps follow:

- **G-1 — Execution success ≠ cartographic validity.** A choropleth with equal-interval breaks on a heavy-tailed variable executes perfectly and communicates nothing. No current agent computes whether the classification is defensible.
- **G-2 — Model-judged correctness inherits model failure modes.** Self-critique and MLLM aesthetic evaluation are additional stochastic passes; they cannot *guarantee* a property.
- **G-3 — Rejection without remedy does not converge.** Validation that only says "no" leaves an unbounded revision loop; nothing in the literature makes the veto *convergent*.

**The positioning sentence:** prior autonomous-GIS agents ask whether the model can complete the task; we ask whether the artifact it produces is correct, and answer with deterministic validation that holds veto authority over the model.

## §4. Contributions (ranked; the boundary of each is stated)

1. **Diagnostic→prescriptive rejection.** Validation gates that return executable mandates — precomputed break values, mandated transform, splice-ready constants — rather than binary verdicts or natural-language critique. This converts an open-ended LLM revision loop into bounded transcription (≤3 iterations, then human escalation).
2. **Authority separation as an architectural invariant.** "Zero statistical authority leakage" made concrete and auditable: the LLM never receives raw data values, and no numeric constant in the executed render originates from free generation. Enforced by a typed provenance contract (`ProvenancedValue`), checked before code text exists, and visible in the trace.
3. **Statistical justification of map *type*, not just map style.** Gate 3b refuses bivariate encoding when variables lack spatial cross-correlation and mandates the side-by-side univariate fallback — the system declines cognitively misleading map choices, rather than styling them well.
4. **A ground-truth corpus for validation *decisions*.** 42 seeded scenarios across all six gates with known-correct outcomes, scoring decision accuracy (not rejection rate), including cases that *should* be refused.
5. **Reproducibility as an enforced property.** Seeded permutation inference with (M+1)/(R+1) pseudo p-values, and gate verdicts that are byte-identical across runs.

**Explicitly not claimed:** that the architecture improves *user outcomes* (no human-subject study); that thresholds are empirically optimal (they are calibratable policy, with operating characteristics reported); that the LLM tier is itself reliable (the entire design assumes it is not).

## §5. Research questions

- **RQ1** — Can a deterministic validation layer detect cartographically invalid proposals with high decision accuracy against known ground truth, across heterogeneous failure modes?
- **RQ2** — Does prescriptive rejection (mandate + constants) produce bounded convergence where bare rejection would not?
- **RQ3** — Does the constrained pipeline, run end to end on real data with a real LLM, produce defensible maps and recover substantively meaningful spatial structure?
- **RQ4** — How sensitive are the gates' verdicts to their threshold choices?

---

## §6. Methods to describe

**Architecture (Section 3 of the manuscript).** Three tiers — Semantic Engine (frozen LLM checkpoint, temperature 0, concepts only), Deterministic Execution Engine, Data Fabric — separated by an authority boundary that raw data values never cross. Propose→Verify→Execute state machine with a bounded mandate-retry loop owned by the orchestrator, not the model.

**The provenance contract.** `RenderPlan` carries every render constant as a `ProvenancedValue` tagged `GATE_PRESCRIBED`, `TEMPLATE_DEFAULT`, or `FREE_LLM`; `validate()` refuses any plan containing a `FREE_LLM` constant, raising before any code text is generated. This is the mechanism that makes contribution #2 a structural guarantee rather than a policy.

**Constrained code generation.** The LLM fills typed slots in audited `string.Template` bodies (three templates: choropleth, bivariate, proportional symbol); it never authors free-form logic on the render path. Each template declares the completeness elements it guarantees, which Gate 6 checks against.

**The gate suite (Section 4).** One subsection per gate: the statistic, the threshold and its provenance, and the prescription issued on rejection. Lead with Gate 2 (diagnostic→prescriptive) and Gate 3b (map-type justification); present G1/G3a/G4/G5/G6 as the completed suite.

**Execution isolation.** AST sanitization as a cost-raiser, and a Docker + gVisor container (network-none, non-root, no shell, read-only filesystem) as the actual boundary — with the distinction stated explicitly rather than blurred.

## §7. Data

| Dataset | Role | Provenance |
|---|---|---|
| Census TIGER tracts, Fulton + DeKalb Co., GA (n=530) | Real geometry + queen-contiguity topology for both cases | Pinned snapshot, SHA-256 in `data/MANIFEST.md` |
| Seeded SAR fields on that topology | **Controlled** case: known ground truth to verify the validator | `y=(I−ρW)⁻¹ε`, seeded |
| Census ACS 5-Year 2022, table B19013 (median household income) | **Real** case | Pinned snapshot |
| CDC PLACES 2023, measure CASTHMA (asthma prevalence) | **Real** case | Pinned snapshot |
| 42-scenario seeded benchmark corpus | Decision-accuracy scoring across all six gates | `autocarto benchmark` |

The synthetic/real split is a **design rationale, not an apology**: real data has unknown truth, so a validator cannot be *verified* on it; SAR fields with controlled coupling supply the ground truth that makes "the gate decided correctly" a checkable statement. The real ACS×CDC case then answers the complementary question — does it work on data nobody engineered.

---

## §8. Experiment inventory and results (all verified)

**E1 — Ground-truth decision accuracy (RQ1).**
42 scenarios across six gates; 39 scored, 3 borderline-by-construction reported but not scored.
- Strict decision accuracy **38/39 = 97.4%**
- Benign inputs (expect pass): **17/17**
- Pathological inputs (expect reject): **21/22**
- Single miss: `G3b independent seed=23 → APPROVE` (expected REJECT) — disclosed, cause identified (§17)
- Rejection rate 22/42 (52.4%) — *corpus-dependent and adversarial by construction*, reported only alongside composition
- Rejections by cause: heavy_right_skew 6, discrete_ordinal 3, zero_inflated 3, G3a:white_noise 3, G3b:independent 2, G3b:weak_coupling 1, G1:geographic_density 1, G4:conus_webmerc 1, G4:georgia_webmerc 1, G5:rdylgn_diverging 1

**E2 — Controlled validity case (RQ1, RQ2).** 530 tracts, two heavy-right-skew SAR variables.
- Gate 2 vetoes the naive quintile-derived proposal, prescribes log-transform + Jenks
- GVF **0.7514→0.8348** (canopy) and **0.7741→0.8607** (asthma)
- Gate 3b: I_xy = **+0.3262** (pseudo-p = 0.0050, 199 permutations), Spearman ρ = **+0.9471** → APPROVE

**E3 — Ablation: ungated vs. gated (RQ1).** Same variable, same 530 tracts.
- Naive equal-interval: **414/530 (78%)** of tracts collapse into one class
- Gated log+Jenks: balanced **[98/134/145/90/63]**
- **Honest counter-result:** equal-interval attains a *higher* GVF (0.866 vs 0.835) while producing the worse map. The paper reports this and uses class balance, not GVF, as the failure metric — this is evidence Gate 2 is a distribution *diagnostic*, not a GVF maximizer, and pre-empts "isn't this just a GVF filter?"

**E4 — Real-data case study (RQ3).** 519 tracts with matched real ACS + CDC values (11 of 530 dropped for missing estimates — dropped, not imputed).
- Gate 3b: I_xy = **−0.5555** (p = 0.005), Spearman ρ = **−0.7758** → APPROVE
- Income alone: Moran's I = **0.59** (p = 0.001), correctly confirmed by Gate 3a
- Interpretation: higher income co-locates with lower asthma prevalence — a documented health-equity gradient the system recovered without being directed to it

**E5 — Threshold sensitivity / operating characteristics (RQ4).**
- Gate 3a: **AUC 0.9149** (n=240), current threshold |I|>0.1
- Gate 3b: **AUC 0.9569** for I_xy, **0.9978** for ρ (n=165), thresholds 0.15 / 0.20
- Gates 2 and 4: rate curves only — honestly labeled, because no independent ground truth for "good enough classification" or "acceptable distortion" exists beyond the metric itself

**E6 — Null-model study (limitation, RQ1).** 999 permutations, 9 scenarios.
- Free permutation: 2 false positives, 0 false negatives
- Conditional toroidal shift: 1 false positive, 1 false negative
- Mean p-value inflation on the independent regime: **18.97×**
- The decision matrix is *deliberately unchanged*: it depends on |I_xy| and |ρ| magnitude, never on p alone. Wiring significance in is flagged as a separate, un-made design decision rather than silently applied.

**E7 — Execution isolation.** 27 attack vectors (network exfiltration, filesystem writes, privilege escalation, resource exhaustion, reflection escapes, raw syscalls) run against the container with the AST sanitizer **deliberately bypassed**; all 27 blocked, verified in CI against real `runsc`.

**E8 — Reproducibility.** Gate verdicts byte-identical across runs; 236 tests passing (33 skipped where a live network/Docker/gVisor dependency is absent).

---

## §9. Claims–Evidence Matrix (the backbone)

| # | Claim as it will appear | Evidence | Status |
|---|---|---|---|
| C1 | Deterministic gates reach the correct decision in 38/39 scored ground-truth scenarios (97.4%) | E1 | **Supported** |
| C2 | Prescriptive rejection bounds the revision loop at ≤3 iterations | E2, E4 end-to-end runs; orchestrator iteration cap | **Supported** (mechanism + observed convergence in 2 iterations on real data) |
| C3 | Gate 2 materially improves classification fit over the naive baseline | E2 (GVF 0.75→0.83, 0.77→0.86) | **Supported** |
| C4 | Unconstrained classification collapses 78% of tracts into one class; the gated pipeline does not | E3 | **Supported** |
| C5 | Gate 2 is a distribution diagnostic, not a GVF maximizer | E3 counter-result (equal-interval has higher GVF, worse map) | **Supported** |
| C6 | The pipeline recovers a real, unengineered health-equity gradient on real data | E4 | **Supported** |
| C7 | No numeric render constant originates from free LLM generation | Provenance contract + `validate()` raising on FREE_LLM; auditable in trace | **Supported (structural)** |
| C8 | Gate verdicts are byte-identical across runs | E8 | **Supported — scope-limited** (verdict files only; two trace files legitimately vary in timing fields) |
| C9 | Gate thresholds have measured operating characteristics | E5 | **Supported for G3a/G3b; explicitly absent for G2/G4** |
| C10 | The container, not the sanitizer, is the security boundary; 27 tested vectors blocked | E7 | **Supported — bounded wording** ("27 tested vectors", never "100%") |
| C11 | The free-permutation null is liberal; a conditional null trades FP for FN | E6 | **Supported, reported as limitation** |
| ~~C-X~~ | ~~"23% of proposals rejected"~~ | none | **RETIRED — must not appear** |
| ~~C-Y~~ | ~~"100% of sandbox escapes blocked"~~ | none | **RETIRED — must not appear** |

---

## §10. Figure and table plan

All figures already exist, were regenerated and visually verified on 2026-07-27/28, and are **reused, not re-derived**.

| # | Figure | Source asset | Role |
|---|---|---|---|
| **F1 (hero)** | Ungated vs. gated, same data | `ungated_vs_gated.png` | The thesis in one image; opens the results |
| F2 | Three-tier architecture + authority boundary | `architecture_boundary.png` | Section 3 |
| F3 | Gate 2 distribution diagnostics (5 regimes) | `gate2_distribution_diagnostics.png` | Section 4.2 |
| F4 | Gate 3b decision triptych (APPROVE/WARN/REJECT) | `gate3b_bivariate_scenarios.png` | Section 4.4 |
| F5 | Atlanta results panel (controlled case) | `atlanta_results_panel.png` | Section 6.2 |
| F6 | Rejection-flow Sankey (population view) | `rejection_sankey.png` | Section 6.1 |
| F7 | Trace excerpt (Propose→Verify→Execute, verbatim) | `trace_excerpt.png` | Section 5 |
| F8 | Threshold operating characteristics | `threshold_sensitivity.png` | Section 6.5 |

| # | Table | Content |
|---|---|---|
| T1 | The six gates | Statistic · threshold · provenance · prescription on rejection |
| T2 | Benchmark decision accuracy | Per-gate scored/correct, benign vs pathological, the disclosed miss |
| T3 | Positioning vs. related systems | System · correctness mechanism · contrast (from the 2×2) |
| T4 | Null-model comparison | Free permutation vs toroidal shift: FP, FN, p-inflation |

**Not included:** a 2×2 positioning *figure* (T3 carries it as a table; a diagram would need a render pass and adds nothing the table lacks).

---

## §11. Related work — themed clusters

Sources marked 🔎 were URL-verified in the literature guide (2026-07-06); 📖 are established works whose exact edition/pages still need confirmation and therefore carry `[CITE-VERIFY]` in the draft.

**Cluster A — Autonomous GIS agents.** 🔎 Li & Ning (2023) *Autonomous GIS*, Int. J. Digital Earth 16(2); 🔎 Li, Ning et al. (2025) *GIScience in the Era of AI: A Research Agenda Towards Autonomous GIS*, Annals of GIS (arXiv:2503.23633); 🔎 Akinboyewa et al. (2025) *GIS Copilot* (arXiv:2411.03205); 🔎 Ning et al. (2025) *LLM-Find*, Int. J. Digital Earth 18(1). — *Contrast: capability/execution success vs. artifact validity.*

**Cluster B — LLM cartography (closest neighbor).** 🔎 Wang et al. (2025) *CartoAgent*, IJGIS 39(9) (arXiv:2505.09936); 🔎 *MapMate* (2025). — *Must be stated generously and precisely: CartoAgent judges **aesthetics** with an MLLM; we enforce **statistical validity** with deterministic algorithms. Different axis, complementary, non-competing.*

**Cluster C — Neuro-symbolic coupling.** 🔎 *Neuro-Symbolic AI in 2024: A Systematic Review* (arXiv:2501.05435); 📖 Garcez & Lamb; 📖 Pan et al. *Logic-LM* (EMNLP 2023); 📖 Olausson et al. *LINC* (EMNLP 2023). — *Place precisely: a reasoning-constrains-generation design in which the symbolic layer holds exclusive authority, not merely assists.*

**Cluster D — Cartographic validity theory.** 📖 Jenks (1967) natural breaks/GVF; 📖 Coulson (1987) class intervals; 📖 Jiang (2013) head/tail breaks; 📖 Moran (1950); 📖 Anselin (1995) LISA, (1988) spatial econometrics/SAR; 📖 **Lee (2001) bivariate spatial association (Lee's L)** — the rigorous alternative to bivariate Moran's I + free permutation, and the reference a sharp reviewer will raise; 📖 Bertin (1983) *Semiology of Graphics*; 📖 Brewer / ColorBrewer; 📖 MacEachren (1995); 📖 Snyder (1987) Tissot/projection distortion; 📖 Tobler (1970).

**Cluster E — Evaluation of geospatial agents.** 🔎 GeoAnalystBench (arXiv:2509.05881); 🔎 GeoBenchX (ACM SIGSPATIAL GenAI 2025); 🔎 GISclaw (arXiv:2603.26845) — external evidence that single-pass LLMs produce *syntactically valid but semantically incorrect* GIS code, which motivates the gates. — *Gap: all measure task success; none measures output validity.*

---

## §12. Section structure and word budget (~9,000 words)

| § | Section | Words | Content |
|---|---|---|---|
| 1 | Introduction | 1,100 | Beautiful-wrong-map problem; capability-over-correctness gap; thesis; numbered contributions |
| 2 | Related work | 1,200 | Clusters A–E; explicit CartoAgent distinction; the gap statement |
| 3 | Architecture | 1,400 | Three tiers; authority invariant + provenance contract; Propose–Verify–Execute; constrained codegen |
| 4 | The validation gate suite | 1,600 | One subsection per gate; T1; lead with G2 and G3b |
| 5 | Reproducibility and determinism | 700 | Seeding, (M+1)/(R+1), trace, byte-identical verdicts (scoped); F7 |
| 6 | Evaluation | 2,000 | E1–E6; F1, F5, F6, F8; T2, T4 |
| 7 | Discussion | 900 | When to constrain vs. extend; transferability; what validation cannot do |
| 8 | Limitations and future work | 700 | §17 in full, unhedged |
| 9 | Conclusion | 300 | |

## §13. Abstract blueprint

Problem (2 sentences: fluent-but-invalid maps; the field measures capability) → Approach (3: authority inversion; prescriptive rejection; six gates) → Evidence (3: 97.4% on 42 ground-truth scenarios; 78%→balanced ablation; real ACS×CDC recovery) → Scope (1: what is not claimed) → Significance (1: transferable pattern for constrained spatial agents).

## §14. Title options

1. *AutoCarto-Agent: Deterministic Spatial Validation for Autonomous Thematic Cartography* — recommended; leads with the mechanism.
2. *The LLM Proposes, the Mathematics Disposes: Prescriptive Validation Gates for Autonomous Cartography*
3. *Constraining Generative Agents in Thematic Cartography: A Neuro-Symbolic Architecture with Prescriptive Rejection*

---

## §15. Limitations to state explicitly (not softened)

1. **No labeled real-prompt-through-real-LLM benchmark.** Deliberately cost-bounded, not built. The 42-scenario corpus scores *gate decisions* on seeded inputs, not natural-language prompt handling at scale. This is the single largest evidence gap and is stated as such.
2. **Test coverage never formally measured.** Every gate branch has an explicit test (236 passing), but no coverage tool has been run; the paper says "every branch has a test," never a percentage.
3. **Scale.** Dense-matrix weights; practical to ~10⁴ features. Verdicts do not change with scale — only the executor would.
4. **Free-permutation null is liberal** for two mutually autocorrelated fields (18.97× mean p-inflation on the independent regime). The conditional toroidal-shift null exists opt-in and trades 1 false positive for 1 false negative. Lee's L is the acknowledged rigorous alternative not yet adopted.
5. **Thresholds are policy, not physics.** Operating characteristics exist for G3a/G3b; for G2 and G4 no independent ground truth exists and only rate curves are reported.
6. **Single domain.** Thematic cartography chosen because its validity rules are already codified; transferability is argued, not demonstrated.
7. **No human-subject evaluation.** Whether validated maps are better *for readers* is untested.
8. **The orchestrator's render path is in-process**, not container-isolated; the gVisor container is a separately tested standalone boundary. The split is stated, not blurred.

## §16. Readiness assessment

**Mode: `full`** — all six evaluation experiments have verified results; all eight figures exist and are verified; the claims matrix has no unsupported positive claims.

**Two known soft spots, both handled by scoping rather than omission:**
- Claim C2 (bounded convergence) rests on the orchestrator's iteration cap plus observed 2-iteration convergence in end-to-end runs, not on a large-N convergence study. Worded accordingly.
- Related-work Cluster D citations need edition/page verification before submission; they carry `[CITE-VERIFY]` markers and are listed in `CITATION_GAPS.md`.

## §17. Instructions to the drafting phase

- Label the manuscript **DRAFT** on the title block. Do not name a venue, do not write a "fit" section, do not format to any journal's template.
- Lead Results with the strongest supported claim (E1, then E3's ablation).
- Report E3's GVF counter-result *in the main text*, not a footnote — it is the strongest evidence against the "just a GVF filter" reading.
- Never write "100%", "guaranteed secure", or any unbounded security claim. Use "27 of 27 tested vectors."
- Say "gate verdicts are byte-identical", never "traces are byte-identical".
- Say "core validation completes in under 3 seconds" only with the measurement scope attached, or omit the timing claim entirely — it adds little to a written paper and invites a stopwatch objection.
- Use `[CITE-VERIFY: author, work]` for 📖 sources; never invent a page number, volume, or DOI.
