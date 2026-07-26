# AutoCarto-Agent — STDS 2026 Poster Copy (final draft)

**Venue:** International Symposium of Spatiotemporal Data Science (STDS) · poster session
**Prepared:** 2026-07-17 · **Companion:** [02_CONFERENCE_PRESENTATION_GUIDE.md](02_CONFERENCE_PRESENTATION_GUIDE.md) (delivery scripts, Q&A) · [§9 checklist](#9-pre-print-verification-checklist)
**How to use:** each block below is paste-ready text for `output/figures/Poster_STDS26.ai`, with placement, what it replaces, and the source that regenerates every printed number. Nothing here is aspirational — every claim traces to a command you can run at the poster session.

**Design principle — the three reads.** A poster is three documents at three distances:
- **3-second read (across the aisle):** title strap + the F-NEW-1 before/after pair. A visitor should *get the thesis from the two maps alone.*
- **30-second read (walking past):** the three-tier diagram + the four verdict badges + the results numbers.
- **3-minute read (they stopped):** failure gallery, gate mechanics, benchmark, status box, footnotes. This is where honesty boxes buy credibility.

---

## 1. Title block (top banner)

**Keep the submitted title** — it must match the program listing — but shrink it one step and add the strap, which is the actual 3-second message.

> # AutoCarto-Agent: A Neuro-Symbolic Architecture for Autonomous Thematic Cartography with Deterministic Spatial Validation
>
> ## The LLM proposes; the mathematics disposes.

**Author strip (replaces current name/venue-only block):**

> **Abdul Kalam Mustaq** · Rutgers University
> International Symposium of Spatiotemporal Data Science (STDS) 2026
> Autonomous GIS · Generative AI & Agentic Systems · Spatial AI: Theory & Uncertainty
> ✉ ar.abdulkalam.mustaq@gmail.com   `[QR → repository]`

*Rationale:* the strap is the memorable one-liner (Guide §1.2) and doubles as the verbal pitch opener, so poster and speech reinforce each other. The topic line mirrors the symposium's own theme names — signals fit to session chairs and browsers. QR + email were missing from the printed poster (Guide §4.2-6); add the QR only if the repo is shared (it is now clean, tagged, and tested).

---

## 2. Left column — replace "Why constrain the LLM?" (~200 words → ~95)

**Header:**

> ## LLMs draw beautiful, wrong maps

**Failure gallery (three bullets, each one failure + its gate):**

> - **Classification.** Equal-interval breaks on a skewed variable collapse **414 of 530 tracts (78%) into one class** — the map renders fine and says nothing. *→ Gate 2*
> - **Encoding.** Bivariate palettes get applied to variable pairs with **no spatial cross-correlation** — a map of pure noise that looks like a pattern. *→ Gate 3b*
> - **No guarantees.** Temperature 0 is not determinism, and self-critique is another stochastic pass. Prompting cannot *enforce* anything.

**Thesis paragraph:**

> **AutoCarto-Agent removes the LLM's statistical authority instead of improving its judgment.** The LLM parses intent, selects visual variables and templates, and assembles code. A deterministic engine computes every number, vetoes invalid proposals, and — the key move — **rejects with a prescription**: the mandated method, the precomputed break values, splice-ready code. Rejection with prescription converges in ≤3 iterations, because the LLM's remaining job is transcription of the mandated method. Every decision lands in a machine-readable trace.

*Rationale:* the 78% figure is the poster's own F-NEW-1 headline number (computed, tested); leading the gallery with it links the text column to the killer visual. Each bullet names the gate that catches it — the architecture becomes the answer to the failure list. The old column's ~200-word paragraph buried this structure (Guide §4.2-7).

---

## 3. Architecture band (three tiers) — targeted edits only

The three-tier layout, colour grammar, and authority-boundary caption are the poster's strength — **keep them**. Three surgical text changes:

**3a. Gate 2 badge — REMOVE `"23% of proposals rejected and prescribed"`.** Replace with:

> **G2 (Diagnostic)**
> Rejections carry precomputed breaks — the LLM transcribes, never negotiates.

**3b. Sandbox callout — fix the attribution** (currently credits gVisor with "Reflection: Blocked"; reflection blocking is the AST sanitizer, and the container is unbuilt):

> **Execution Sandbox**
> AST sanitizer — escape & reflection vectors blocked *(verified)*
> Container isolation — gVisor, network-none *(designed — not yet built)*

**3c. Boundary caption — keep verbatim** (it is the best line on the poster):

> The LLM reasons about concepts. It NEVER consumes raw data values.

*Rationale:* 3a replaces the one unfalsifiable number on the poster with the mechanism claim, which is both true and more distinctive (the population number now lives in §5's benchmark block, with its corpus). 3b is one clause of honesty that disarms the entire sandbox line of attack (Guide Q10) — "verified/designed" reads as rigor, not weakness.

---

## 4. Center-bottom — F-NEW-1 placement (the 3-second read's payoff)

Place `output/figures/ungated_vs_gated.png` in the bottom-left region (the old whitespace). Caption:

> **Same variable, same 530 tracts.** Ungated: equal-interval breaks collapse 78% of tracts into one class — a flat wash. Gated: Gate 2 diagnoses the skew and prescribes **log-transform + Jenks** — balanced classes **[98 / 134 / 144 / 91 / 63]** reveal the gradient. *Every number computed by the shipping Gate 2; regression-tested.*

*Rationale:* this pair is the thesis with zero reading required. The class-count list is deliberately printed — it is the kind of concrete detail reviewers photograph.

*Note — log-transform, not arcsinh:* Gate 2 branches on the sign of the data (`gate2_classification.py`): strictly non-negative variables (canopy loss, min = 0.57 here) get `log1p`; only variables with negative support get the arcsinh remedy (a *different* demo case, used in the talk's "arcsinh save" story, Guide §4.3 Slide 8). Both are real, correct, and distinct — don't merge them into one caption.

---

## 5. Results panel — full replacement copy

**Header:**

> ## Verified results — every number regenerates from one command

**Block A — Atlanta case (fixes the wrong 0.894 line):**

> **Atlanta bivariate case** · 530 census tracts, Fulton + DeKalb (real TIGER geometry)
> Both variables heavy-right-skew → Gate 2 vetoes the naïve quintile-derived proposal, prescribes **log-transform + Jenks**
> **GVF: 0.75 → 0.83** (canopy) and **0.77 → 0.86** (asthma) over the naïve quintile breaks
> **Gate 3b:** I_xy = **+0.326** (pseudo-p = 0.005, 199 permutations) · Spearman ρ = **+0.947** → **APPROVE** — bivariate encoding unlocked

**Block B — ground-truth benchmark (new; replaces the retired "23%"):**

> **Ground-truth benchmark** · 24 seeded scenarios with known correct outcomes
> **95% correct** on the 21 unambiguous cases (20/21) — 6/6 benign passed, 14/15 pathological rejected, **every rejection with its prescription**. 3 more are borderline by construction and correctly flagged, not forced.
> The one miss — two independent fields spuriously cross-correlating — is disclosed; a conditional-permutation null is queued.

*(Print-space note: if the box is tight, the middle line may compress to "6/6 benign passed, 14/15 pathological rejected (3 borderline, correctly flagged)" — keep "20/21," never bare "24," so the denominator is never ambiguous on the printed poster.)*

**Block C — reproducibility strip (one line, monospace if possible):**

> `pip install -e . && autocarto demo` → statistical traces **byte-identical** across runs · < 3 s · fully offline · 67 tests · pinned TIGER snapshot (SHA-256)

*Rationale:* Block A's GVF line replaces the untraceable "raises GVF from failure to 0.894" with the verified before/after (Manual §5); "quintile-derived" (not "Jenks") matches the exact terminology `demo.py` and `benchmark.py` use for this baseline — see the footnote below on why F-NEW-1 uses a *different* naive baseline (equal-interval) on purpose. Block B leads with **decision accuracy against known truth** — the defensible headline the synthetic corpus actually supports — accounts for all 24 scenarios explicitly (21 scored + 3 disclosed-borderline, not silently dropped), and *prints the miss*, which converts your weakest point into evidence of rigor before anyone asks Q12. Block C is the claim no poster neighbor can match; keep it terse and typeset like code.

**Footnote — two naive baselines, used on purpose, not inconsistently:** F-NEW-1 (§4) uses **equal-interval** breaks because that isolates the classic "even spacing ignores distribution shape" failure most visibly (78% collapse). Block A and the benchmark (§5, §8) use **quintile-derived** breaks because that is the exact naïve policy the demo/benchmark harness scripts as "the LLM's default proposal." Both are real failure modes Gate 2 catches; neither substitutes for the other. If a viewer asks why the two differ, that's the answer.

---

## 6. Right-bottom — Status & Roadmap box (new; ~4 lines)

> **STATUS — what runs today vs. what is specified**
> ✅ *Implemented & verified:* Gates 2, 3b · spatial-first retrieval · sandbox sanitizer · deterministic demo + benchmark (67 tests)
> 📋 *Specified (engineering plan):* Gates 1, 3a, 4–6 · orchestrator + LLM tier · gVisor container
> → *Next:* real ACS/CDC variables · full gate suite · conditional-permutation null

*Rationale:* Guide §4.2-5 — poster sessions reward candor; this box answers "only two gates?" (Q2) before it's asked and makes the uniform gate stack in the architecture band honest. **Re-verified before this draft:** `grep`-checked the full source tree for any univariate Moran's I / Gate 3a implementation — none exists (`src/autocarto/execution/gates/` contains only `gate2_classification.py` and `gate3b_bivariate_correlation.py`; the Atlanta results panel only ever computes *bivariate* Moran's I). The two-gate claim was already accurate; do not add Gate 3a to the implemented list without shipping the code first.

---

## 7. Footnote strip (bottom edge) — upgrade the synthetic-data note from apology to method

**Replace** the current small-print note with:

> **Synthetic by design:** variables are seeded SAR fields on real TIGER topology — *known ground truth is what lets us verify the validator.* Real-variable case study is the next milestone. · Geometry: Census TIGER (Fulton + DeKalb, GA), pinned snapshot · Python 3.14 · PySAL 4.14 · GeoPandas 1.1

*Rationale:* same disclosure, reframed as the methodological choice it is (Guide Q1). The version footer now matches the shipped `environment.yml` (TD-6 closed).

---

## 8. Optional additions (if layout allows) + the handout

- **F-NEW-3 Sankey** (`rejection_sankey.png`), small, beside Block B, caption: *"Where 24 naïve proposals go — every rejection routed to a deterministic remedy. First-pass verdicts; adversarial corpus; the one false-approval is shown."* Skip it if it crowds the maps — the poster must breathe.
- **F-NEW-2 trace excerpt** (`trace_excerpt.png`) — **do not put on the poster.** Print ~20 copies as the A4 handout ("artifact in hand", Guide §6.2): it's the piece visitors take away, with the QR repeated on it.
- If a line must be cut anywhere, cut in this order: Sankey → topic line in §1 → third bullet of §2. Never cut Block C — reproducibility is the differentiator.

---

## 9. Pre-print verification checklist

Every printed number, its value, and the command that regenerates it. Run all four on the presentation laptop **before sending to print**; if anything drifts, the poster is wrong, not the code.

| Printed claim | Value | Regenerate with |
|---|---|---|
| 530 tracts · GVF 0.75→0.83 / 0.77→0.86 · I_xy +0.326, p .005 · ρ +0.947 | Block A | `python scripts/gen_results_panel.py` |
| 78% / 414-of-530 collapse · classes [98/134/144/91/63] | §2, §4 | `python scripts/gen_ungated_vs_gated.py` (+ `pytest tests/test_figures.py`) |
| 95% (20/21 of 24; 3 disclosed-borderline) · 6/6 benign · 14/15 pathological · 1 disclosed miss | Block B | `autocarto benchmark` |
| Byte-identical traces · <3 s · offline · 67 tests | Block C | `autocarto demo` twice + `pytest` |
| "escape & reflection vectors blocked (verified)" | §3b | `pytest tests/sandbox/` (sanitizer suite) |

**Removed from the old poster — do not reintroduce:** `GVF … 0.894` (untraceable; wrong), `23% of proposals rejected` (unfalsifiable as printed), `Reflection: Blocked` under gVisor (misattributed).

---

*Copy drafted against the verified state at commit `a1fdb0a` (67 tests green). If the benchmark or figures are regenerated with different seeds/corpus before printing, re-run §9 and update the affected blocks — never the other way around.*
