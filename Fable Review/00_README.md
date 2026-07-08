# Fable Review — AutoCarto-Agent (CartoLLM)

Independent technical design review, engineering handover, and conference-presentation package for the STDS 2026 submission *"AutoCarto-Agent: A Neuro-Symbolic Architecture for Autonomous Thematic Cartography with Deterministic Spatial Validation."*

**Reviewer:** Claude (Fable 5) acting as Principal Software Architect / spatiotemporal research engineer · **Date:** 2026-07-06
**Scope:** the entire repository as of this date — `Codes/` originals, `output/codes_patched/` (canonical), all abstracts, figures, traces, and the print poster. Every claim in these documents is traceable to a file in this repo or to a measurement executed during the review.

## The documents

The package has two horizons. **V1 (docs 01–02) is what you need for STDS now.** **V2 (docs 03–05) is future scope** — the full production agent, the journal paper, and the reading program behind both.

| File | What it is | Read it when |
|---|---|---|
| [01_OPERATING_MANUAL.md](01_OPERATING_MANUAL.md) | **V1 · Engineering handover:** how the system works, what exists vs. what the abstract claims (gap matrix), architecture assessment, technical-debt register, security review, 6-phase roadmap with task cards sized for a lower-capacity coding model, testing strategy, deployment & production-readiness | Before writing any code |
| [02_CONFERENCE_PRESENTATION_GUIDE.md](02_CONFERENCE_PRESENTATION_GUIDE.md) | **V1 · STDS presentation package:** narrative arc, pitches and walkthrough scripts, poster corrections (with verified replacement numbers), slide sequences, figure plan, live-demo script, 16-question hard-Q&A bank, claim-discipline table, checklist, cheat sheet | Before touching the poster or rehearsing |
| [03_V2_PRODUCTION_BLUEPRINT.md](03_V2_PRODUCTION_BLUEPRINT.md) | **V2 · Full-agent build spec:** the honest "is this needed for the conference?" answer (§0), SLOs, complete specs for all 7 gates + orchestrator state machine + Tier-1 LLM + real-data fabric + benchmark + deployment, and a priority ladder for what to cut | When planning the post-conference build / journal version |
| [04_V2_PUBLICATION_GUIDE.md](04_V2_PUBLICATION_GUIDE.md) | **V2 · Publication strategy:** the claim ladder (assert only as high as your evidence), positioning against the 2025–26 autonomous-GIS landscape, journal-paper skeleton, venue timeline, journal-grade reviewer defenses | When drafting the paper |
| [05_LITERATURE_STUDY_GUIDE.md](05_LITERATURE_STUDY_GUIDE.md) | **V2 · Reading program:** 7 thematic tracks (competition, neuro-symbolic, spatial stats, cartographic theory, retrieval, sandboxing, benchmarks) with verified 2026 citations + foundational works, each tied to the component it grounds; a 3-week crash program | Before writing related work / defending gates |

## Verification performed during this review (2026-07-06)

- `output/codes_patched/demo.py` re-executed in an isolated directory: Gate 2 and Gate 3b statistical traces **byte-identical** to the committed ones; retrieval/sandbox traces identical except wall-clock fields; 8/8 sandbox cases as designed.
- The seeded Atlanta pipeline (`gen_results_panel.py` logic) fully reproduced in an ephemeral environment: **530 tracts, I_xy=+0.3262, p=0.0050, ρ=+0.9471** — exact match to the poster.
- **New finding:** the poster's "GVF … 0.894" is not computed anywhere in the repo (it traces to an unrelated demo case). The true values, computed and verified during this review: **canopy 0.7514→0.8348, asthma 0.7741→0.8607** (naive quintile → prescribed log+Jenks). Corrected wording is provided in the presentation guide §4.2.

## The three actions that matter most (from the full prioritized lists inside)

1. **Fix the poster's GVF line and resolve the "23%" badge** before printing (Presentation Guide §4.2, §8.2 — a half-day honest mini-benchmark is specified).
2. **Phase 0 repo hygiene today:** `git init`, promote `output/codes_patched/` to a `src/` package, snapshot the TIGER GeoJSON (Manual §11 P0, §9 TD-1/2/7).
3. **Port `demo.py` cases into a pytest suite** — the project currently has zero tests protecting its byte-identical reproducibility, which is its single best asset (Manual §12).

## "Do I need to build all the gates / fetch real data for the conference?"

**No — and switching to real data would not strengthen your core claim.** The short version (full reasoning in Blueprint §0): it's a *poster*; the novelty (prescriptive gates) is already built and reproducible; and synthetic-SAR-on-real-geometry is actually the *better* choice for proving the validator decides *correctly*, because it gives known ground truth that real ACS/CDC data cannot. Real data demonstrates *utility*, not *validity* — that belongs in the journal version. For STDS, the only must-dos are the wording/number fixes above. Everything about the full agent lives in the V2 docs as future scope.
