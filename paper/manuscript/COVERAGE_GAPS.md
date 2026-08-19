# Coverage Gaps — what must be resolved before this draft is submittable

Ordered by severity. Items 1–3 are blocking for submission; 4–6 are quality improvements.

## 1. ~~BLOCKING — Figure 6 shows a superseded corpus~~ — RESOLVED, and the original claim was wrong

**This entry was based on a misreading and is retracted.** `scripts/gen_rejection_sankey.py` calls `build_report()` — the *current* 42-scenario corpus — and then filters to `gate in ("G2", "G3b")`, a restriction documented in the script with its rationale (the two-gate flow is the shipped poster design; those are the gates whose rejections select among alternative prescriptions). The figure was never generated against a superseded corpus; it shows a deliberate 24-of-42 subset of live data.

**Resolved by** correcting the description rather than the figure: the manuscript (§6.1), `FIGURE_CAPTIONS.md`, and `FIGURE_MANIFEST.md` now state the subsetting and its reason explicitly, and note that figure and table derive from the same benchmark run and so cannot disagree.

**Optional improvement, not blocking:** extending the Sankey to all six gates would let its scenario count match Table 2 directly. G1/G4/G5 rejections carry a single prescription each, so this adds rows without adding information — judged not worth redesigning a shipped asset.

**Separately resolved:** the committed `benchmarks/mini_benchmark_report.json` *was* genuinely stale (24-scenario v2 at 95.24%) and has been regenerated to the current 42-scenario corpus at 97.4%, so the repository artifact now matches the paper.

## 2. BLOCKING — `[CITE-VERIFY]` markers must be resolved

Roughly 15 foundational references carry `[CITE-VERIFY]` because the literature guide flagged their edition/year/pages as unconfirmed. These are real works, but no bibliography entry should be written from memory. See `CITATION_GAPS.md`.

## 3. BLOCKING — bare `[CITE: ...]` markers in Sections 1–2

The autonomous-GIS and benchmark citations exist as verified URLs in the literature guide but were not expanded into full bibliographic entries in this draft. They need author lists, volumes, and DOIs.

## 4. Word budget is at the low end

7,551 words including front matter (~7,000 body). The plan budgeted 9,000. The sections most under-developed relative to plan:

| Section | Actual | Planned | Gap |
|---|---|---|---|
| Related work | 889 | 1,200 | Cluster D (cartographic theory) is compressed to one paragraph |
| Architecture | 792 | 1,400 | Tier 3 (Data Fabric) is described in one sentence; retrieval contract deserves a subsection |
| Reproducibility | 347 | 700 | Trace structure could be shown, not just described |

None of these gaps is an evidence gap — the material exists in `docs/architecture.md` and the operating manual. This is expansion work, not new research.

## 5. Figure 8 not visually re-verified in this pass

`threshold_sensitivity.png` numbers were read from the report JSON (2026-08-11) but the image itself was last inspected 2026-07-27. Regenerate and view before submission.

## 6. No graphical abstract / positioning diagram

The 2×2 positioning is carried as Table 3. If a target venue later requests a graphical abstract, this is the natural candidate.

---

## Explicitly *not* gaps

- **The synthetic/real split.** This is a design rationale (§6.2), defended in text, not a shortcoming to be apologised for.
- **The single benchmark miss.** Disclosed, quantified, and traced to a named cause (§6.6).
- **The GVF counter-result.** Reported in the main text deliberately; it strengthens rather than weakens the argument.
