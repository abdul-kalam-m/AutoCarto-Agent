# `paper/` — manuscript workspace

A **draft** research paper on AutoCarto-Agent. No target venue is selected, and no venue is named in any artifact here.

## Layout

| Path | What |
|---|---|
| `PAPER_PLAN.md` | Outline, claims–evidence matrix, figure plan, evidence provenance |
| `manuscript/MANUSCRIPT_REVISED.md` | **The source of truth.** Edit here, then rebuild. |
| `manuscript/sections/*.md` | Pre-revision section drafts, kept for history |
| `manuscript/{CLAIM_SUPPORT_MAP,COVERAGE_GAPS,CITATION_GAPS,REVIEW_REPORT,CLAIM_RISK_REPORT}.md` | Traceability and open-gap tracking |
| `figures/FIGURE_{MANIFEST,CAPTIONS}.md` | Figure provenance and manuscript-ready captions |
| `submission/latex/` | `main.tex`, `body.tex`, `references.bib` |
| `submission/pdf/MANUSCRIPT_DRAFT.pdf` | Compiled manuscript (committed) |
| `submission/docx/MANUSCRIPT_DRAFT.docx` | Editable manuscript (committed) |

## Figures are not committed here

The eight figures are **byte-identical copies** of `output/figures/` (verified by hash), so storing them again under `paper/` would keep three copies of the same images. Repopulate before a LaTeX build:

```bash
for f in ungated_vs_gated architecture_boundary gate2_distribution_diagnostics gate3b_bivariate_scenarios atlanta_results_panel rejection_sankey trace_excerpt threshold_sensitivity; do cp output/figures/$f.png paper/figures/ 2>/dev/null; cp output/figures/$f.pdf paper/figures/ 2>/dev/null; done && mkdir -p paper/submission/latex/figures && cp paper/figures/*.png paper/submission/latex/figures/
```

None of them is regenerated for the paper — each was produced by its own script in `scripts/` and visually verified. See `figures/FIGURE_MANIFEST.md`.

## Rebuilding

**PDF** (TinyTeX; BibTeX and `plainnat.bst` required):

```bash
cd paper/submission/latex && latexmk -pdf main.tex && cp main.pdf ../pdf/MANUSCRIPT_DRAFT.pdf
```

`main.tex` declares `\DoNotLoadEpstopdf` before `graphicx`. That is deliberate: `epstopdf-base` requires `grfext`, which is absent from minimal TeX installs, and every figure here is PNG so EPS conversion is dead weight. Removing that line breaks the build on a bare distribution.

**DOCX** (no pandoc in this environment; uses Word via COM):
Markdown → well-formed HTML → `Documents.Open(..., Format=8)` → save as `.docx`. Both details matter — an HTML fragment lacking `<html>`/`<body>`, or opening without `Format=8`, silently drops every table. Verify by reopening the saved file and counting tables, not by trusting the count taken before Word finishes parsing.

## Status

Draft. The blocking gap is the bibliography: 6 references are CrossRef-verified and present; 4 further works plus ~17 foundational references remain as visible `[CITE:]` / `[CITE-VERIFY]` markers because their records could not be confirmed from this environment. **No entry was written from memory.** See `manuscript/CITATION_GAPS.md` and `submission/SUBMISSION_MANIFEST.md`.
