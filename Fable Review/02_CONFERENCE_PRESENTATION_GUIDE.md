# AutoCarto-Agent — STDS Conference Presentation Guide

**For:** STDS Spatiotemporal Conference (stds.stcenter.net) · poster presentation, with lightning-talk and full-talk variants
**Prepared:** 2026-07-06 · **Companion:** [01_OPERATING_MANUAL.md](01_OPERATING_MANUAL.md) (cited as *Manual §n*)

Everything in this guide is grounded in the repository and in measurements taken during this review. Where a number on the current poster is wrong, the corrected, verified value is given — with the script that proves it.

---

## 1. The story

### 1.1 The narrative arc (use this shape everywhere — poster walkthrough, talk, hallway)

1. **Hook — the beautiful wrong map.** LLMs write GeoPandas fluently. The maps compile, render, and look professional. They are also, routinely, statistically invalid: quantile breaks on zero-inflated disease counts (an empty class and a lie about "hot spots"), Web-Mercator for county area comparisons (Georgia inflated), red-green ramps unreadable to 8% of male viewers, bivariate encodings for variable pairs with no spatial cross-correlation (a map of pure noise that *looks* like a pattern).
2. **The failed instinct.** The field's reflex is better prompting or fine-tuning. But a stochastic system cannot *guarantee* anything, and temperature 0 is not determinism (§7 Q6). Cartographic validity is not a style preference — it is checkable mathematics.
3. **The inversion (your contribution).** Don't make the LLM a better statistician. **Remove its statistical authority entirely.** The LLM proposes concepts and assembles code; a deterministic engine computes the statistics, vetoes invalid proposals, and — the key move — *prescribes the exact remedy*: the mandated method, the precomputed break values, the code snippet. Rejection without prescription would loop forever; rejection **with** prescription converges in ≤3 iterations because the LLM's remaining job is transcription.
4. **Proof it behaves.** On 530 real Atlanta census tracts (TIGER geometry), the engine caught naive classification proposals on two skewed variables, prescribed log+Jenks (GVF 0.751→0.835 and 0.774→0.861 — corrected numbers, §6.2), verified bivariate spatial cross-correlation (I_xy=+0.326, pseudo-p=0.005 on 199 permutations; ρ=+0.947), and only then unlocked the bivariate encoding. Every decision is in a machine-readable trace; re-running the pipeline reproduces the statistical trace **byte-identically**.
5. **The claim.** A reference architecture for constrained agentic GIS: LLMs belong in autonomous cartography *when and only when* every numerical decision is subject to deterministic validation — and the validated core of that architecture is implemented, tested, and reproducible today.

### 1.2 One-liners (pick one, use it consistently)

- **"The LLM proposes; the mathematics disposes."** (recommended — memorable, precise)
- "We didn't make the LLM a cartographer. We made it powerless to be a bad one."
- "Propose. Verify. Execute. In that order, with no exceptions."

### 1.3 The 30-second elevator pitch

> "Everyone is wiring LLMs into GIS pipelines. The problem is that LLMs produce maps that are fluent and wrong — bad class breaks on skewed data, area-distorting projections, bivariate maps of uncorrelated variables. AutoCarto-Agent inverts the trust relationship: the LLM only proposes; a deterministic engine of validation gates recomputes every numerical decision, and when it rejects a proposal it doesn't just say no — it prescribes the exact fix, precomputed breaks and all, so the LLM is reduced to a code assembler. On 530 Atlanta tracts the system vetoed naive classifications, mandated a log-Jenks scheme, verified spatial cross-correlation at p=0.005, and only then allowed a bivariate map. Every run emits a reproducible JSON trace — the statistical content is byte-identical across runs."

### 1.4 The three-minute poster walkthrough (script)

Stand left of the poster; walk the visitor left → center → bottom.

> **[Left column]** "Quick context: large language models can already write mapping code. What they can't do is be trusted with the statistics. Here are the failure modes we kept seeing —" *(point to the 'Why constrain the LLM?' column, name two: skewed classification, projection distortion)*.
>
> **[Tier diagram, top]** "Our answer is architectural, not prompt engineering. Three tiers. On the left, the LLM — it reasons about *concepts*: what map type, which visual variables, which template. This dashed line is the important part —" *(trace the orange boundary)* "— raw data values never cross it, and no numeric decision made on the left survives unverified. The middle tier is a deterministic execution engine with algorithmic validation gates: coordinate systems, classification validity, spatial autocorrelation, projection distortion, color-vision accessibility, completeness."
>
> **[G2 box]** "The interesting gate is this one. It's not pass/fail. It profiles the distribution — skewness, zero-inflation, normality — and when it rejects, it returns a *prescription*: the mandated method and the exact break points, precomputed. The LLM doesn't get to negotiate; it gets to transcribe. That's what makes the loop converge instead of thrashing." *(If they lean in: the arcsinh story, §5.2.)*
>
> **[Results, bottom]** "Concrete case: 530 census tracts, Fulton and DeKalb counties, real TIGER geometry — the two variables are synthetic spatial-autoregressive fields, which is deliberate: we know the ground-truth spatial structure, so we can verify the gates decide *correctly*. Both variables are heavily right-skewed; Gate 2 rejected the naive proposal and prescribed log-Jenks — goodness-of-variance fit rises from about 0.75 to 0.84. Gate 3b then checks whether a bivariate map is even justified: bivariate Moran's I of 0.33 at p=0.005 on 199 permutations, Spearman 0.95 — passed, so the bivariate encoding is unlocked. If it hadn't passed, the system would have *refused* and produced side-by-side univariate maps instead."
>
> **[Close]** "Everything is seeded and traced — rerunning the pipeline reproduces the statistical trace byte-for-byte. The validated core — the diagnostic gates, the retrieval contract, the sanitizer — runs offline, and the validation itself completes in under three seconds; want to see it?" *(→ demo, §6)*

---

## 2. Research contributions, ranked

Lead with #1; it is the defensible novelty. The rest are supporting.

1. **The diagnostic→prescriptive rejection pattern (Gate 2).** Validation gates that return *mandates* — exact precomputed break points, mandated transforms, splice-ready code — rather than binary failures or natural-language critique. This converts an unbounded LLM revision loop into bounded transcription (≤3 iterations, then human escalation). Implemented, verified, reproducible (*Manual §4.1*).
2. **Authority separation as an architectural invariant.** "Zero statistical authority leakage" made concrete: the LLM never receives raw data values and no numeric constant in the final render originates from free generation — a property that is *auditable from the execution trace*, not a slogan (*Manual §8.2* shows how it becomes a type-level guarantee).
3. **Statistical justification gates for map *types*.** Gate 3b refuses bivariate encoding when variables lack spatial cross-correlation (bivariate Moran's I + Spearman, permutation-tested) and mandates the fallback. The system doesn't just style maps correctly — it refuses cognitively dishonest map choices.
4. **Spatial-first hybrid retrieval.** Deterministic bbox filtering *before* semantic ranking, so embeddings can never veto geometry — including correct antimeridian shard-splitting (the Aleutian test case). Small, but it names and fixes a real anti-pattern in geo-RAG.
5. **Reproducibility discipline as a first-class artifact.** Seeded everything, (M+1)/(R+1) pseudo p-values, JSON traces whose statistical content is byte-identical across runs — demonstrated live.

### 2.1 Positioning against related work (for Q&A and the related-work slide)

Be accurate and generous; the room may contain these authors.

- **Autonomous-GIS / LLM-Geo line (Li & Ning and successors), GIS copilots, GeoGPT-class systems:** these established that LLMs can decompose geospatial tasks and generate executable workflows. Their evaluation criterion is predominantly *task completion* — does the code run, is the answer right. **Your delta:** you validate the *cartographic-statistical validity of the output artifact*, and you enforce it with deterministic computation rather than model judgment. You constrain rather than extend the agent.
- **Self-critique / reflection loops (Reflexion-style, LLM-as-judge):** feedback is another stochastic pass — no guarantees, and the critic hallucinates too. **Your delta:** the critic is a theorem, not a model; feedback is a numeric mandate, not advice.
- **Guardrails / structured-output validation (schema validators, constrained decoding):** they check *form* (JSON shape, types, regex). **Your delta:** gates compute *domain statistics on the actual data* (GVF, Moran's I, distortion) and prescribe numeric remedies.
- **Neuro-symbolic systems (LLM + solver/planner):** closest in spirit; typically the symbolic side *solves* and the LLM *translates*. **Your delta:** an asymmetric authority design for a domain (cartography) with codified but previously unenforced validity rules — plus the prescriptive-feedback convergence mechanism.

One honest sentence to keep handy: *"Nothing in the gate mathematics is new — Jenks, GVF, Moran's I are classics. What's new is the architecture that gives those classics veto power over a generative model, and the prescription mechanism that makes the veto convergent."* Reviewers respect this framing and it is exactly true.

---

## 3. Communicating the neuro-symbolic novelty (without overclaiming)

**Define your terms early — three sentences:**
- *Neuro:* a frozen LLM checkpoint, temperature 0, restricted to cartographic concepts (intent, visual variables per Bertin, template choice, code assembly).
- *Symbolic:* deterministic algorithms — distribution diagnostics, spatial statistics, projection math, color science — with exclusive authority over every number.
- *The coupling:* Propose-Verify-Execute with prescriptive rejection; the interface between the two is a typed contract (proposals down, mandates up), never shared free text.

**Precision rules (these keep you out of trouble):**
- Say **"deterministic validation"**, not "deterministic system." The LLM tier is stochastic by nature; your claim is that its stochasticity cannot reach the artifact unverified. If pressed on API nondeterminism, that's Q6 — and your architecture is *specifically the answer to it*.
- Say **"the validated core is implemented; the surrounding architecture is specified"** — never imply all six gates run today (gap table in *Manual §7*). The two implemented gates are the two novel ones; the missing four are established computations. Scope stated is scope defended.
- Say **"synthetic variables on real geometry, by design"** — the SAR construction gives known ground truth, which is what lets you *verify the verifier*. This is a methodological choice you can defend proudly (Q1), provided you never let anyone believe the asthma data is real CDC data.

---

## 4. Poster review (current `Poster.jpg`) and slide sequences

### 4.1 What the current poster does well — keep

- **The three-tier visual grammar** (orange stochastic / blue deterministic / green data fabric) with the dashed authority boundary and rotated caption — the architecture is legible from 3 meters, which is rare.
- **Gate stack with PASS / REJECT→PRESCRIBE badges** — communicates "not just filters" at a glance.
- **Concrete numbers in the results block** (530 tracts, I_xy, ρ, thresholds, permutation count) rather than adjectives.
- **The honesty footnote** ("Variable values are SAR-generated synthetics calibrated to realistic spatial structure") — exactly right; §4.2 asks you to make it *slightly* more prominent, not less.
- The G2 histogram inset with LLM-proposed vs prescribed break lines — the prescription mechanism in one image.

### 4.2 Poster corrections (ordered by severity — do #1–#3 before printing)

1. **The GVF line is wrong and must change.** Poster says *"GVF Classification Fit: Raises GVF from failure to 0.894 (GVF of prescribed log+Jenks breaks)."* No script in the repo computes GVF for the Atlanta variables; 0.894 traces only to the demo's unrelated `well_behaved` synthetic (RUN_SUMMARY.json gvf=0.8937). Verified correct values (this review, exact reproduction of the seeded pipeline — *Manual §5*): **canopy 0.8348, asthma 0.8607, vs. naive quintile baseline 0.7514 / 0.7741.** Suggested replacement line:
   > *"GVF: prescribed log+Jenks raises fit 0.75 → 0.83 (canopy) and 0.77 → 0.86 (asthma) over naive quintiles."*
   This is *better* rhetoric too: "from failure to X" was hollow (the 0.0 in the trace means "no breaks proposed", not "failing fit"); a real before/after beats it.
2. **The "23% of proposals rejected" badge (G2 box) is currently unfalsifiable** — no benchmark corpus or ledger exists in the repo (*Manual §7 C9*). Either (a) run the mini-benchmark in §8 (half a day, honest number, likely close), relabeling as *"X% of naive proposals rejected across N scenarios"*, or (b) remove the badge. Do not stand next to a number you cannot regenerate.
3. **gVisor wording.** The sandbox callout credits gVisor with "Reflection: Blocked" — reflection blocking is the *AST sanitizer* (pre-execution, verified); gVisor is the designed containment layer and has not yet been exercised (no image built). Reword to: *"AST sanitizer: reflection & escape patterns blocked (verified) · Container isolation: gVisor, network-none (design)."* One clause of honesty that disarms the entire sandbox line of attack (Q10).
4. **Version footer consistency.** Poster says Python 3.14 / PySAL 4.14.1 / GeoPandas 1.1.3; `Codes/environment.yml` pins Python 3.11.8 / GeoPandas 0.14.4. The poster matches the machine that actually ran the figure — fix the env file (Manual P0-T2) so the two artifacts agree.
5. **Add a "Status & Roadmap" micro-box** (bottom-right, 4 lines): *implemented & verified* (G2, G3b, retrieval, sanitizer — reproducible offline, core validation <3 s) / *specified* (G1, G4, G5, G6, orchestrator, LLM tier) / next: real-variable benchmark. Poster sessions reward candor; this box converts your biggest vulnerability into evidence of rigor.
6. **Add contact + QR code** to the header (author block currently has name/venue only): repo link (after Manual P0 makes it public-ready) + email. Poster visitors who matter follow up later.
7. Minor: the left column is a ~200-word wall — cut to a 3-bullet failure gallery; the bottom-left whitespace can host the §5.1 killer figure once made; check the architecture PNG's title/banner overlap at the top edge before reprint (`architecture_boundary.png` shows the red stats banner colliding with the topmost gate box and title text).

### 4.3 Full-talk slide sequence (15 slides, ~12 min + Q&A)

| # | Slide | Content / asset | Speaker beat |
|---|---|---|---|
| 1 | Title | One-liner + Atlanta bivariate map as background | "The LLM proposes; the mathematics disposes." |
| 2 | The beautiful wrong map | 2×2 failure gallery (§5.1 fig F-NEW-1, or verbal + one example) | Each of these renders fine and lies. |
| 3 | Why prompting can't fix it | 3 bullets: no guarantees, temp-0 ≠ determinism, critique loops are stochastic too | Set up the inversion. |
| 4 | The inversion | Propose-Verify-Execute triad, minimal diagram | Authority, not intelligence, is the design variable. |
| 5 | Architecture | `architecture_boundary.png` | Walk the boundary; 20 seconds max on Tier 3. |
| 6 | The gate suite | 6-gate table w/ one-line rule each | "Two of these are research; four are engineering. The research ones are built." |
| 7 | Gate 2 deep-dive | `gate2_distribution_diagnostics.png` | Diagnosis regimes; prescription = breaks + snippet. |
| 8 | The arcsinh save | zoom of `negative_values_arcsinh` panel | Story beat (§5.2): the engine caught what the LLM would have silently clamped. |
| 9 | Gate 3b decision matrix | APPROVE/WARN/REJECT table + `gate3b_bivariate_scenarios.png` | The system refuses map *types*, with a mandated alternative. |
| 10 | Data fabric | bbox-first diagram + Aleutian case | "Embeddings never get to veto geometry." |
| 11 | Atlanta case | `atlanta_results_panel_publication.png` | Corrected GVF numbers (0.75→0.83, 0.77→0.86); I_xy=0.326 p=0.005; ρ=0.947. |
| 12 | Reproducibility | trace JSON excerpt + "byte-identical" diff screenshot | This is what 'deterministic validation' buys you. |
| 13 | Scope & limitations | Own it: synthetic variables (why), 2/7 gates, benchmark pending, container unbuilt | Pre-empts 80% of hostile Q&A (§7). |
| 14 | Roadmap | Manual §11 phase strip | Benchmark → full gate suite → gVisor → release. |
| 15 | Close | One-liner reprise + QR + "the validation runs offline in under 3 seconds — find me" | Invitation, not summary. |

### 4.4 Lightning version (5 frames, 3 min)

1. Beautiful wrong map (hook) → 2. The inversion (triad) → 3. Prescription mechanism (G2 histogram) → 4. Atlanta result (panel C + numbers) → 5. Limitations + QR. Cut everything else; do not compress all 15 slides into 3 minutes.

---

## 5. Figures: audit and recommendations

### 5.1 Existing assets (all in `output/figures/`)

| Asset | Verdict | Use |
|---|---|---|
| `ungated_vs_gated.png/.pdf` | **Built (F-NEW-1) — the killer visual; every number computed from the real pipeline** | Slide 2 payoff, poster bottom-left |
| `trace_excerpt.png/.pdf` | **Built (F-NEW-2) — the artifact in hand; Propose→Verify→Execute from the real trace** | Slide 12, poster, print handout |
| `rejection_sankey.png/.pdf` | **Built (F-NEW-3) — population view; every rejection routed to a remedy, driven by the real benchmark** | Slide 10/13, poster |
| `architecture_boundary.png/.pdf` | Good; fix top-edge text collision before reuse | Slide 5, poster |
| `atlanta_results_panel_publication.*` | Excellent; panel legends match the verified prescribed breaks exactly | Slide 11, poster centerpiece |
| `gate2_distribution_diagnostics.png` | Good teaching figure (5 regimes, LLM vs prescribed break lines) | Slide 7 |
| `gate3b_bivariate_scenarios.png` | Good (APPROVE/WARN/REJECT triptych) | Slide 9 |
| `gate3b_bivariate_map_approve.png` | Fine, superseded by Atlanta panel C | backup |

### 5.2 Figures to create (ranked by payoff)

1. **F-NEW-1 — "Ungated vs Gated", the killer visual — ✅ BUILT** (`scripts/gen_ungated_vs_gated.py` → `output/figures/ungated_vs_gated.png`). Same Atlanta variable (530 tracts, real TIGER geometry), two maps: LEFT = naive LLM output (equal-interval breaks + rainbow/jet ramp) — a flat wash where **414/530 tracts (78%) collapse into one class**; RIGHT = the gated output (Gate-2 log+Jenks, balanced 98/134/144/91/63, colour-blind-safe sequential ramp) revealing the real spatial gradient. A histogram strip shows *why* (equal-interval wastes classes on the sparse tail). Every number is computed by the real Gate 2, not asserted, and regression-tested (`tests/test_figures.py`). **Honesty note baked into the figure:** Gate 5 (colour) is labelled *specified*, not implemented; and — a sharper point discovered while building it — equal-interval actually scores a slightly *higher* GVF (0.87 vs 0.83) while producing the worse map, so the figure uses **class balance**, not GVF, as the honest failure metric. This doubles as a rebuttal to "isn't a gate just a GVF filter?": Gate 2 is a distribution *diagnostic*, and here it deliberately accepts lower GVF to produce a legible map. *This is the single highest-leverage artifact — the whole thesis in one glance.* Regenerate with `python scripts/gen_ungated_vs_gated.py` (needs `pip install -e .[geo]`).
2. **F-NEW-2 — Trace excerpt panel — ✅ BUILT** (`scripts/gen_trace_excerpt.py` → `output/figures/trace_excerpt.png`). One Gate-2 rejection end to end as a three-card **Propose → Verify → Execute** flow: the (simulated) LLM's naïve Fisher-Jenks proposal; the deterministic REJECT verdict *verbatim from the emitted JSON trace* (`"passed": false`, `prescribed_breaks`, and the bold `DO NOT propose alternative methods.` mandate); and the mandated code diff (naïve breaks struck out, `np.digitize` on the prescribed breaks added). Uses the demo's zero-inflated case (49.8% zeros) and is asserted at render time to match the committed trace byte-for-byte; content is regression-tested (`tests/test_trace_excerpt.py`). Honesty on the figure face: Tier 1 is labelled **simulated in V1**, and breaks are rounded for display (trace keeps full precision). This is the "artifact in hand" for poster conversations and the reproducibility slide — reviewers trust a real trace over a diagram.
3. **F-NEW-3 — Rejection-flow Sankey — ✅ BUILT** (`scripts/gen_rejection_sankey.py` → `output/figures/rejection_sankey.png`). The population view that complements F-NEW-2's single case: 24 naïve proposals flow **Proposal → Gate → Verdict → Mandated outcome**, with each rejection routed to its specific deterministic remedy (Gate 2's four prescriptions — break-at-0, log+Jenks, arcsinh, unique-value — and Gate 3b's side-by-side-univariate mandate). Driven entirely by `autocarto.benchmark.build_report()` — **no fabricated flows**, counts asserted to sum to the real scenarios, conservation regression-tested (`tests/test_rejection_sankey.py`). Honesty on the figure face: labelled an **adversarial stress corpus** (so the rejection share is high by design, not a natural rate), **first-pass verdicts** (not the full iterate-to-convergence loop), and it discloses the **1 false-approval** among the 6 Gate-3b approvals (the documented null-model limitation, R-2). *Exactly the "do not fabricate flows" discipline this guide demanded — the figure now exists because the benchmark does.*
4. The arcsinh story slide (Slide 8) is a crop of an existing figure — no new work, big narrative payoff: *"The LLM proposed log1p. The variable's minimum is −0.8 — log would silently clamp 3% of tracts to zero and corrupt the diagnosis downstream. The engine detected the negative support and mandated arcsinh with back-transformed breaks. This is exactly the class of silent error the architecture exists to catch."*

---

## 6. Live demo plan

### 6.1 Why this demo is safe (a rare luxury — exploit it)

`demo.py` is **offline, deterministic, dependency-light, and fast**. No API keys, no network, no conference-WiFi roulette, no LLM nondeterminism on stage. Verified again 2026-07-26: statistical output byte-identical to the committed traces (*Manual §5*).

**Timing, precisely (re-measured 2026-07-26):** the tool's own internal timer — printed as `Total wall-clock: ... ms` at the end of the run — stayed under 2.7 s across every test. The *total command latency*, stopwatch-to-stopwatch, measured 3.5–6.1 s, because Python/NumPy/SciPy/Matplotlib interpreter startup adds a few seconds that the internal timer doesn't count. **Say "the validation itself is under 3 seconds" and point at the printed line — never promise the whole command finishes in under 3 seconds.** An audience member with a phone timer will catch the difference.

### 6.2 Setup (before leaving for the conference)

```bash
# The known-good interpreter on the dev laptop (PATH python lacks scipy!):
# The package is now pip-installed (V1 build) — this replaces the old direct
# output/codes_patched/demo.py invocation, which still exists but is frozen.
C:\Users\abdul\AppData\Local\Python\bin\python.exe -m autocarto.demo
# or, if `autocarto` is on PATH after `pip install -e .`:
autocarto demo
```
- Dry-run on battery + on the actual presentation laptop; pre-open `output/figures/` thumbnails and one trace JSON in an editor tab.
- Record a 45-second screen capture of the run as the fallback (GIF/MP4 on the phone too).
- Print one Gate-2 REJECT trace excerpt on paper — the "artifact in hand" for poster conversations.

### 6.3 The 90-second narration (matches actual stdout)

> "Running the deterministic layer end-to-end — no network, everything seeded." **[run]**
> "Gate 2: five synthetic distributions. The well-behaved one passes with GVF 0.89. The zero-inflated one — half the tracts are zero — is rejected; the engine *prescribes* a manual break at zero plus Fisher-Jenks on the tail, with the exact break values. The negative-skewed one: log is invalid for negatives, so it mandates arcsinh. The LLM never chooses — it transcribes."
> "Gate 3b: three spatial scenarios on a contiguity grid. Strongly coupled fields — APPROVE, I 0.48, p 0.005. Weakly coupled — WARN, annotation required. Independent fields — REJECT, p 0.58: the system *refuses* to draw a bivariate map and mandates side-by-side univariates."
> "Retrieval: the Aleutian query crosses the antimeridian — naive bounding-box logic returns zero results; ours splits the box and finds both shards."
> "Sandbox: a reflection escape — `().__class__.__mro__` — blocked with three violations; a docstring that merely *mentions* subprocess passes. Static analysis with a low false-positive rate."
> "And if I run it again —" **[rerun]** "— the statistical trace is byte-identical. That's the reproducibility claim, demonstrated."

### 6.4 Demo honesty rule

If anyone asks whether the LLM is in the loop during the demo: *"No — the demo scripts the LLM's proposals so you're seeing the deterministic layer isolated; that's also how we unit-test it. The LLM integration is the orchestrator phase of the roadmap."* Never let a visitor walk away believing they watched an end-to-end autonomous run.

---

## 7. Hard Q&A bank

Rehearse the first eight; skim the rest. Format: question → the answer that is *true per the repo* → the trap to avoid.

**Q1. "Your results are synthetic."**
→ "Deliberately, and it's disclosed on the poster. The geometry and topology are real — 530 TIGER tracts, real queen-contiguity weights. The variables are SAR fields *because that gives us ground truth*: we control the true spatial structure, so we can verify the gates decide correctly — that's how you validate a validator. Real-variable integration (ACS, CDC PLACES) is the next milestone, and nothing in the gate math changes."
*Trap:* don't say "the data is basically realistic" — the value is *known truth*, not realism.

**Q2. "Only two of the six gates exist?"**
→ "Correct — and by design the two that carry research risk: the diagnostic-prescriptive classification engine and the bivariate justification gate. The remaining four are established computations — CRS checks, Tissot distortion, color-vision simulation, completeness checklists — specified with thresholds and libraries in the engineering plan. We claim a reference architecture plus a validated core, not a finished product."
*Trap:* never imply G1/G4/G5/G6 run today; the poster's uniform gate stack already walks this line (§4.2-5).

**Q3. "Isn't this just guardrails / input validation?"**
→ "Guardrails check structure — schemas, types, regex. These gates compute *domain statistics on the actual data* — GVF, Moran's I, permutation tests — and on rejection they return a numeric *mandate*: exact breaks, mandated transform, splice-ready code. Validation that prescribes is what turns an open-ended revision loop into bounded transcription."

**Q4. "Why not fine-tune the LLM to be a better cartographer?"**
→ "Fine-tuning shifts a distribution; it can't guarantee a property. A tuned model still fails silently on the next odd distribution, and every model update resets your trust. Deterministic verification is model-agnostic — swap the checkpoint, keep the guarantees. The two aren't rivals: a better LLM converges in fewer iterations; the gates make its failures unshippable."

**Q5. "What's actually novel? Jenks and Moran are decades old."**
→ Own it (§2.1): "The statistics are deliberately classical — that's what makes them trustworthy. The contribution is architectural: giving classical methods *veto power* over a generative model, and the prescription mechanism that makes vetoes convergent. To our knowledge, prior autonomous-GIS agents validate execution success, not cartographic-statistical validity of the artifact."

**Q6. "Temperature 0 isn't deterministic — API models drift."**
→ "Exactly right, and it's *why the architecture exists*. We don't claim the LLM is deterministic; we claim the LLM's stochasticity cannot reach the map unverified. Determinism lives in the validation layer — seeded permutation tests, byte-identical statistical traces, model ID and every proposal logged, so drift is *observable* and its consequences are gated. If the model changes its proposal next month, either it still passes the same gates or it gets the same prescription."
*This question is a gift — the answer is your thesis.*

**Q7. "Your thresholds are arbitrary. Why GVF 0.6? Why |I_xy|>0.15?"**
→ "Defaults from cartographic convention and pilot judgment, held in one config with a documented rationale per value — and honestly, uncalibrated: a sensitivity study sweeping thresholds over the benchmark corpus is scheduled (operating-characteristic curves per gate). The architectural claim is threshold-independent: whatever the community calibrates, the enforcement mechanism is the contribution. They're policy, not physics."

**Q8. "Moran's I gating would reject valid maps — rare-disease surveillance is spatially random but still worth mapping."**
→ "The gate rejects the *choropleth encoding*, not the analysis — the prescription is a proportional-symbol or dot alternative. A choropleth's message *is* its spatial pattern; if I≈0, that message is noise, and the honest map is a different map. Edge cases — negative autocorrelation, checkerboards — need two-sided handling, which is in the G3a spec. And there's a human escape hatch after three iterations; the system is opinionated, not authoritarian."

**Q9. "Where does '23% of proposals rejected' come from?"**
→ If you've run the §8 mini-benchmark: give the new number and its exact provenance. If not: "Pilot-phase observation; the formal benchmark harness that regenerates it from a fixed prompt corpus is in progress, and the number will be published with the corpus or not at all." *Trap:* do not improvise a methodology that doesn't exist. (Strong recommendation: resolve this before the conference — §8.)

**Q10. "AST blacklists are trivially bypassable."**
→ "Agreed — static sanitization is a cost-raiser, not a boundary. The design boundary is container isolation — gVisor, network-none, cap-drop — which is specified but not yet exercised, and we say so. Two additional mitigations: all seven attempted escape classes in our suite are blocked at the AST layer including reflection and `getattr` spellings; and the roadmap moves code generation to template assembly, where the LLM fills slots in audited templates and never writes free-form code at all — which collapses the attack surface far more than any sanitizer."
*Trap:* never say "100% of escapes blocked" unqualified — say "all attempted vectors in our suite (seven classes)."

**Q11. "530 tracts is a toy. What about a million features?"**
→ "The current implementation is dense-matrix and honest about it — fine to ~10k features. The design routes by scale: PySAL below 10k, PostGIS with GiST indexes to a million, Sedona beyond; sparse weights are the first upgrade. The gates' verdicts don't change with scale — only the executor does."

**Q12. "Your permutation test permutes y freely — that ignores y's own spatial autocorrelation and inflates significance."**
→ "Sharp — yes, the free-permutation null is liberal for two mutually autocorrelated fields. Two mitigations today: the decision requires effect size (|I_xy|>0.15) *and* aspatial correlation (|ρ|>0.20), not p alone. The rigorous upgrade — conditional permutation or Lee's L — is queued as a research task. The gate's role is conservative screening of an *encoding* choice, not causal inference."
*(Whoever asks this is your most valuable reviewer — get their name.)*

**Q13. "Why Qdrant bbox payload filters? PostGIS does exact spatial predicates natively."**
→ "Stage-1 bbox on the vector store guarantees the semantic ranker only ever sees spatially plausible candidates — geometry filters *before* similarity, in one system, cheaply. Envelope overlap is necessary, not sufficient, so the design adds exact ST_Intersects refinement in the deterministic tier before computation. A single PostGIS+pgvector store is a legitimate alternative; ours keeps the vector store swappable and the spatial authority in the tier that already owns determinism."

**Q14. "What if the user *wants* the 'invalid' map?" (the paternalism question)**
→ "Three answers: the WARN tier exists precisely for defensible-but-risky choices — proceed with mandatory annotation; after three failed iterations the system escalates to a human rather than looping; and thresholds are explicit policy, so an org can loosen them — but the *default* posture for an autonomous system publishing maps should be safe-by-construction. The gates encode communication validity, not taste."

**Q15. "Is 'zero authority leakage' falsifiable, or a slogan?"**
→ "Falsifiable: audit the trace — every numeric constant in the executed render code must trace to either a gate prescription or an audited template, never to free LLM generation. Today that's an auditable property of the trace; the next engineering phase makes it a *type-level* guarantee — the only object serializable into an LLM prompt is a schema-and-prescriptions context that structurally cannot contain data arrays."

**Q16. "Why should a spatiotemporal-science audience care about a cartography pipeline?"**
→ "Because the pattern generalizes: any spatial analysis an agent automates — hotspot detection, interpolation, cluster labeling — has the same shape: a fluent generator, a set of classical validity conditions, and today, nothing enforcing them. Thematic mapping is the cleanest demonstrator because its validity rules are codified. The architecture is the transferable artifact."

---

## 8. Claim discipline — and the half-day fix that de-risks everything

### 8.1 Assert / soften / drop

| Claim | Status | Action |
|---|---|---|
| Architecture, authority boundary, prescription mechanism | implemented at core, verified | **Assert** |
| Atlanta: 530 tracts, I_xy=+0.3262 (p=0.0050, 199 perms), ρ=+0.9471 | reproduced exactly | **Assert** |
| GVF improvement | verified this review | **Assert with corrected numbers**: 0.751→0.835 / 0.774→0.861 (never 0.894) |
| Byte-identical statistical traces; offline, core validation <3 s | verified | **Assert** — but say "core validation," never promise the whole command finishes in <3 s (interpreter startup alone takes 3.5–6 s; see §6.1) |
| Antimeridian handling; arcsinh negative-support catch | verified | **Assert** (great war stories) |
| Sandbox sanitization | verified for 7 attack classes | **Soften wording**: "all attempted vectors in our suite" — never "100% of escapes" |
| gVisor air-gapped execution | designed, never run | **Soften**: "designed for gVisor; containment layer under validation" |
| "23% of proposals rejected" | untraceable | **Drop or regenerate** (§8.2) |
| "34 s end-to-end / 90% LLM latency" (v1 abstract) | no code path exists | **Drop**; do not reintroduce without the benchmark |
| Six gates | 2 implemented | **Reframe**: "validated core + specified suite" |

### 8.2 The half-day mini-benchmark (strongly recommended before the conference)

The "23%" badge can become honest in ~4 hours, because the "naive LLM" is scriptable:
1. Define the naive proposal policy = what the demo already simulates (always propose `jenks` with quintile breaks; for bivariate, always propose bivariate encoding).
2. Corpus: ~30 variable scenarios from the existing generators (5 Gate-2 regimes × parameter draws) + ~10 bivariate SAR scenarios across ρ couplings (all code exists in `demo.py`).
3. Run gates over the corpus; report *"the deterministic suite rejected X% of naive proposals (N=40 scenarios; dominant causes: zero-inflated classification, absent cross-correlation)"*.
4. Commit corpus + runner + JSON ledger (seeds fixed) so the number regenerates by one command — then the poster badge survives any audit.
This is Manual P4-T2/T3 in miniature and becomes the seed of the real benchmark.

---

## 9. Pre-conference checklist

**Poster (requires reprint):**
- [ ] Replace GVF line with corrected numbers (§4.2-1) — *the one mandatory fix*
- [ ] Resolve the 23% badge: mini-benchmark (§8.2) or remove
- [ ] gVisor → sanitizer wording fix (§4.2-3)
- [ ] Add Status & Roadmap micro-box; add QR + contact
- [ ] Version footer ↔ environment file consistency

**Demo:**
- [ ] Dry-run `demo.py` on the presentation laptop with the known-good interpreter; verify offline
- [ ] Record 45 s fallback capture; print one REJECT-trace excerpt
- [ ] Prepare the two-command determinism show: run, rerun, `fc`/`diff` the trace

**Repo (if sharing the QR):**
- [ ] Manual Phase 0: git init, promote patched code, delete the stale `- Copy.py` and abstract clutter, README quickstart
- [ ] Snapshot TIGER GeoJSON (Manual TD-7) so the figure regenerates even if the API changes conference week

**Rehearsal:**
- [ ] 30-second pitch ×10 until automatic; 3-minute walkthrough ×3 aloud
- [ ] Q1, Q2, Q6, Q9, Q10 answers verbatim-comfortable
- [ ] Decide your "I don't know" protocol: *"Not measured yet — the harness to measure it is the next milestone"* beats improvisation every time

---

## 10. Cheat sheet — numbers you must own cold

| Number | Value | Source |
|---|---|---|
| Atlanta tracts (after island removal) | **530** (Fulton + DeKalb, TIGER) | gen_results_panel, reproduced |
| Bivariate Moran's I_xy | **+0.3262**, pseudo-p **0.0050** | 199 permutations, (M+1)/(R+1), seed 0 |
| Spearman ρ | **+0.9471** | same run |
| GVF canopy | naive 0.7514 → prescribed **0.8348** | verified this review |
| GVF asthma | naive 0.7741 → prescribed **0.8607** | verified this review |
| Gate 3b thresholds | APPROVE \|I\|>0.15 ∧ \|ρ\|>0.20 · WARN 0.08/0.10 | gate3b source |
| Gate 2 triggers | 40% zeros · skew 1.5 · >10% outliers · ≤10 unique · GVF ≥0.6 | gate2 source |
| Grid demo scenarios | APPROVE +0.476 (p=.005) · WARN +0.116 · REJECT −0.025 (p=.580) | demo trace |
| Iteration cap | 3, then human escalation | Gate 2 |
| Demo runtime | core validation <3 s (the tool's own printed timer), fully offline, statistical traces **byte-identical** across runs. Total command latency incl. Python/library startup: 3.5–6 s — don't quote "<3 s" for the whole command | re-verified 2026-07-26 |
| Sandbox suite | 7 attack classes blocked; docstring false-positive fixed; prod refuses in-process exec | sandbox trace |
| Patch cycle | 20 fixes: 2 blockers, 3 security, 15 correctness/robustness | CHANGES.md |
| Diagnosis regimes | 6 (well-behaved, zero-inflated, right-skew→log, negative-skew→**arcsinh**, outlier→head-tail, discrete→unique) | gate2 source |

**Final note.** This project's strongest presentation asset is that its central claims are *demonstrable on demand* — few poster neighbors can rerun their results byte-identically on a laptop in three seconds. Build the talk around that superpower, state the scope honestly, and the hard questions become your best material.
