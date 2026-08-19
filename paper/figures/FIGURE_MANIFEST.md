# Figure Manifest — AutoCarto-Agent (DRAFT)

**Policy: reuse, do not re-derive.** Every figure below already existed, was regenerated from its own script, and was visually inspected on 2026-07-27/28. Copies were taken into `paper/figures/`; the originals in `output/figures/` were read only, never written.

**Provenance note (2026-08-11):** `ungated_vs_gated.pdf` and `atlanta_results_panel_publication.pdf` in `output/figures/` carry uncommitted modifications timestamped 2026-07-28 ~04:10, made during poster finalization — after and independent of this pipeline. The PNG variants (which are the versions visually verified) are unmodified and are what the manuscript references. No figure was regenerated for this paper.

| ID | File | Generating script | Status | Verified |
|---|---|---|---|---|
| F1 | `ungated_vs_gated.png` / `.pdf` | `scripts/gen_ungated_vs_gated.py` | Ready — **hero** | Visual + numeric (2026-07-28) |
| F2 | `architecture_boundary.png` / `.pdf` | `scripts/gen_architecture_diagram.py` | Ready | Visual (2026-07-28); false-claim banner confirmed absent |
| F3 | `gate2_distribution_diagnostics.png` | demo pipeline | Ready | Existing verified asset |
| F4 | `gate3b_bivariate_scenarios.png` | demo pipeline | Ready | Existing verified asset |
| F5 | `atlanta_results_panel.png` / `.pdf` | `scripts/gen_results_panel.py` | Ready | Visual + numeric (2026-07-28) |
| F6 | `rejection_sankey.png` / `.pdf` | `scripts/gen_rejection_sankey.py` | Ready — see caveat | Visual (2026-07-28) |
| F7 | `trace_excerpt.png` / `.pdf` | `scripts/gen_trace_excerpt.py` | Ready | Visual (2026-07-28) |
| F8 | `threshold_sensitivity.png` / `.pdf` | `scripts/threshold_sensitivity.py` | Ready | Numeric (report JSON read 2026-08-11) |

## Caveats that must be carried into captions

- **F6 (Sankey) covers 24 of the 42 scenarios — a deliberate gate subset, not stale data.** `scripts/gen_rejection_sankey.py` calls `build_report()` (the *current* 42-scenario corpus) and filters to `gate in ("G2", "G3b")`, which is documented in the script itself: the two-gate flow is the shipped poster design, and those are the gates whose rejections choose among alternative prescriptions. An earlier revision of this manifest described the figure as depicting a "superseded 24-scenario corpus" — that was wrong, and the caption and manuscript have been corrected to state the subsetting accurately. Regenerating the figure across all six gates would make it match Table 2's scenario count directly, but G1/G4/G5 rejections have a single prescription each and would add rows without adding information.
- **F1 is an adversarial single-variable illustration**, not a population result; the population view is F6 and the accuracy result is Table 2.
- **F3/F4** derive from the demo pipeline's seeded scenarios, not from the Atlanta case.

## Not produced

- A 2×2 positioning diagram. Carried as Table 3 instead; a rendered diagram would require an external image pass and adds nothing the table lacks.
