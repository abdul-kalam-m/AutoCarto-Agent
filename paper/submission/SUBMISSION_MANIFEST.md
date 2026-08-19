# Package Manifest

**Built:** 2026-08-19 (supersedes the 2026-08-11 build) · **Source:** `paper/manuscript/MANUSCRIPT_REVISED.md`
**Target venue:** none. The package is venue-neutral: standard `article` class, no journal template, no venue named in any artifact.

## Readiness

> ### This is a DRAFT. It is not submission-ready.
>
> Structure and evidence are complete — every quantitative claim is verified and traceable to a command that regenerates it. **The bibliography is now partial rather than absent:** 6 references were retrieved from CrossRef by DOI and are real, complete records; 4 further works and ~17 foundational references remain as visible markers because their records could not be confirmed from this environment. That is a deliberate refusal to fabricate, and it is the remaining blocking item for submission.

## What changed since the 2026-08-11 build

| Change | Why |
|---|---|
| **Bibliography created** (`latex/references.bib`, 6 entries, CrossRef-verified) | Was the single blocking gap; now partially closed with real records |
| 13 `\cite{}` commands wired into `body.tex`; author-year citations into the Markdown | Markers replaced only where the record was verified |
| **Gate 6 limitation added** (§4.5) | Two real template-manifest divergences were found in the interim — including a bivariate map that passed Gate 6 with no legend drawn. The paper now demonstrates the weakness it previously only conceded. |
| **§7.5 strengthened with an observed failure** | The abstract claim "a map can pass all six gates and answer the wrong question" now cites a real instance: a request for an absent variable silently produced a valid map of a different one |
| Test count 236 → **249** | Suite grew with the fixes above |
| Figure 6 characterisation **corrected** | The prior manifest called it a "superseded 24-scenario corpus." That was wrong — it is a deliberate G2/G3b subset of the *current* corpus, documented in the generating script. Caption, manifest, and §6.1 now say so. |
| `\DoNotLoadEpstopdf` added to `main.tex` | `epstopdf-base` began requiring `grfext`, absent from this TeX install and unfixable without a cross-release upgrade. All figures are PNG, so the documented opt-out is the correct fix, not a workaround. |

## Files

| Path | What it is | Status |
|---|---|---|
| `pdf/MANUSCRIPT_DRAFT.pdf` | Compiled manuscript, **25 pages** incl. 8 figures + references | ✅ built |
| `docx/MANUSCRIPT_DRAFT.docx` | Editable manuscript, 19 pages, 8,268 words, **4 tables verified present** | ✅ built |
| `latex/main.tex` | Document shell, title block, figure floats, bibliography | ✅ |
| `latex/body.tex` | Sections 1–9, 13 `\cite{}` commands | ✅ |
| `latex/references.bib` | **6 CrossRef-verified entries** | ✅ partial |
| `latex/abstract.tex`, `latex/keywords.tex` | Front matter | ✅ |
| `latex/figures/*.png` | 8 figures | ✅ |

## Build environment (for reproduction)

- **PDF:** `latexmk -pdf main.tex` under TinyTeX (TeX Live 2025). `microtype`, `caption`, `parskip` are absent from this minimal install; all three are cosmetic and reproduced inline. `grfext` is also absent, which now breaks `epstopdf-base`'s auto-load — handled by declaring `\DoNotLoadEpstopdf` before `graphicx` (its own documented opt-out; every figure here is PNG). BibTeX and `plainnat.bst` are present. The document builds on a bare distribution.
- **DOCX:** pandoc unavailable. Route: Markdown → well-formed HTML → Word (COM, late-binding `Dispatch`, `Format=8` for the web-page importer) → `.docx`. **Both details matter:** an HTML fragment without `<html>/<body>`, or opening without `Format=8`, silently drops every table — verified by re-opening the saved file and counting.

## Content gaps

| Gap | Severity | Tracked in |
|---|---|---|
| 4 works + ~17 foundational refs still unresolved | **Blocking** | `manuscript/CITATION_GAPS.md` |
| Review was self-performed, not independent | Process | `manuscript/REVIEW_REPORT.md` |
| Word count 8,268 vs 9,000 planned; Related Work cluster D and Tier 3 thin | Minor | `manuscript/COVERAGE_GAPS.md` §4 |

## Verified before packaging

- ✅ Retired claims absent — neither "23% of proposals rejected" nor "100% of escapes blocked" appears
- ✅ No unbounded security claim
- ✅ No venue named in any artifact
- ✅ All 8 figures cited in body text; all 4 tables render in both PDF and DOCX
- ✅ Zero `[PLACEHOLDER]` blocks
- ✅ **Zero undefined citations** and zero BibTeX warnings in the build
- ✅ Every bibliography entry fetched live from CrossRef, none written from memory
- ✅ References page verified visually in the compiled PDF (page 25)

## Next steps, in order

1. Resolve the remaining references. Start with **Lee (2001)** — the rigorous alternative to our null model, and the citation a spatial-statistics reviewer is most likely to raise. The 3 arXiv works need only a reachable arXiv API.
2. Confirm the MapMate record from the ScienceDirect PII directly; do not trust a title search.
3. Obtain an **independent** read. Round-1 review was self-performed, which under-detects argument-level problems.
4. Expand Related Work cluster D and the Tier 3 description (material exists in `docs/architecture.md`).
5. Only then select a venue and re-format.
