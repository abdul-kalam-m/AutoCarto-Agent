# Review Report — Round 1

**Reviewed:** `MANUSCRIPT_DRAFT.md` (7,551 words) → `MANUSCRIPT_REVISED.md` (8,009 words)
**Date:** 2026-08-11
**Standard applied:** top-tier international GIScience journal. **No venue selected**, so no journal-fit assessment is included — that dimension is deliberately omitted rather than scored against a venue that does not exist.

> ## ⚠ Methodological caveat on this review
> The pipeline specifies an independent reviewer model (generator–evaluator separation), reached via an external MCP reviewer or a fresh-context subagent. **Neither was used here:** the external reviewer service is not connected in this session, and spawning subagents was out of scope for this run. This review was therefore performed by the same agent that wrote the draft.
>
> That is a genuine weakness, not a formality. Self-review reliably under-detects framing and argument-level problems, because the reviewer shares the author's mental model. The findings below are concrete and verifiable (dangling references, unnamed variables, missing citations), which is the class of issue self-review *can* catch. **An independent read before submission is still required**, and the scores below should be treated as the author's own assessment rather than as an external evaluation.

## Scores (self-assessed; 10 = ready)

| Dimension | Score | Basis |
|---|---|---|
| Gap clarity | 8 | Three named gaps (G-1/G-2/G-3), each tied to a contribution and an experiment |
| Novelty precision | 8 | Mechanism-level claim, explicitly bounded; CartoAgent distinction stated generously and precisely |
| Methods rigor | 8 | Gates fully specified with thresholds and provenance; provenance contract is a structural argument, not a stylistic one |
| Results discipline | 9 | Every number traceable and re-run; counter-result reported in main text; single miss disclosed and quantified |
| Discussion depth | 7 | Transferability argued rather than demonstrated — acknowledged, but a reviewer may still press |
| Literature positioning | 5 | **Weakest dimension.** Citations exist as markers, not entries; Cluster D compressed to a single paragraph |
| Language flow | 8 | Consistent register; no unhedged superlatives |
| *(Journal fit)* | — | Not assessed: no venue selected |

**Verdict: strong draft, not submittable.** The blocker is bibliographic (Section "Major issues" M-3), not evidential or structural.

## Major issues

**M-1 — Dangling table reference. `RESOLVED.`**
§2.6 referenced "Table 3" but no Table 3 existed anywhere in the manuscript. Fixed by writing the positioning table (six system classes × objective/mechanism/relation).

**M-2 — Two figures never cited. `RESOLVED.`**
Figures 3 (Gate 2 diagnostics) and 4 (Gate 3b triptych) had manifest entries and captions but no body-text citation — a defect in any journal, and one that would likely have survived to submission because the figure list looked complete. Citations added in §4.2 and §4.4.

**M-3 — Bibliography is markers, not entries. `OPEN — blocking.`**
16 `[CITE:]` and 19 `[CITE-VERIFY]` markers remain. This is deliberate: the literature guide explicitly warns against writing a bibliography from memory, and no entry was fabricated. Resolving this requires the author to transcribe records from publishers. Tracked in `CITATION_GAPS.md`; highest priority is Lee (2001), the reference most likely to be raised by a spatial-statistics reviewer.

**M-4 — Synthetic/real variable conflation risk. `RESOLVED.`**
The controlled case's synthetic variables were unnamed in the body, while §6.4 uses *real* CDC asthma prevalence. A reader could easily conflate the synthetic "asthma hospitalisation rate" with the real asthma measure and conclude the controlled results were real-data results. Fixed by naming both synthetic variables and adding an explicit disambiguation note in §6.2.

**M-5 — Tier-1 model never identified. `RESOLVED.`**
The manuscript described "a frozen checkpoint" without naming it, which is a reproducibility gap. Fixed in §3.1, together with a clarification that gate statistics are invariant to which Tier-1 client proposed — which both closes the gap and converts it into an architectural point that supports the central claim.

## Moderate issues

**m-1 — Under-length relative to plan. `PARTIALLY RESOLVED.`** 7,551 → 8,009 words against a 9,000 plan. Related work (Cluster D) and the Data Fabric tier remain thin. Material exists in `docs/architecture.md`; this is expansion, not research. Tracked in `COVERAGE_GAPS.md` §4.

**m-2 — Figure 6 depicts a superseded corpus. `OPEN.`** The Sankey shows 24 scenarios; the headline result uses 42. Currently handled by disclosure in the caption, which is honest but presents two corpus sizes to the reader. Regeneration preferred. Tracked in `COVERAGE_GAPS.md` §1.

**m-3 — Three claims may need citations they lack. `OPEN.`** Colour-vision-deficiency prevalence; non-monotonic lightness of rainbow ramps; "models are replaced every few months." Tracked in `CITATION_GAPS.md` Category C.

## Minor issues

- §6.1 "roughly half are pathological" — actual is 22/39 (56%); acceptable as written.
- The timing claim ("core validation under 3 seconds") was deliberately omitted from the paper; noted here so it is not reintroduced by a later editor.

## Verification performed

| Check | Result |
|---|---|
| Retired claims ("23%", "100% of escapes") absent | ✅ clean |
| Unbounded security language | ✅ only in explicit negation ("we do not claim … unbreakable") |
| Venue name leakage | ✅ clean — no venue named anywhere |
| Figure references resolve (1–8) | ✅ all 8 cited after fix |
| Table references resolve (1–4) | ✅ all 4 rendered after fix |
| Every headline number re-derived from source | ✅ see `CLAIM_SUPPORT_MAP.md` |
| Placeholders | ✅ zero |
