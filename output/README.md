# AutoCarto-Agent — review, patch, and run artifacts

This folder contains the artifacts produced by the code review and
demo execution for the *Spatiotemporal Data Science Symposium* poster
submission, *"A Neuro-Symbolic Architecture for Autonomous Thematic
Cartography with Deterministic Spatial Validation"*.

## Layout

```
output/
├── README.md               (this file)
├── CHANGES.md              detailed diff with reasoning per patch
├── RUN_SUMMARY.json        machine-readable summary of the run
├── codes_patched/          patched copies of the four source files + demo harness
│   ├── gate2_classification.py
│   ├── gate3b_bivariate_correlation.py
│   ├── hybrid_retrieval.py
│   ├── sandbox.py
│   ├── environment_fixed.yml
│   └── demo.py
├── figures/                rendered PNGs from the demo
│   ├── gate2_distribution_diagnostics.png
│   ├── gate3b_bivariate_scenarios.png
│   └── gate3b_bivariate_map_approve.png
├── traces/                 per-module JSON execution traces
│   ├── gate2_classification_trace.json
│   ├── gate3b_bivariate_trace.json
│   ├── hybrid_retrieval_trace.json
│   └── sandbox_trace.json
└── logs/
    └── run.log             stdout from the demo harness
```

The original `Codes/` directory is unchanged.

## How to re-run

From the repository root:

```
python output/codes_patched/demo.py
```

Required Python packages (already validated against this run):
`numpy`, `scipy`, `pandas`, `matplotlib`, `jenkspy` (recommended).
The demo does not require `qdrant-client`, `openai`, or `cartopy`; the
retrieval module ships with a deterministic hash-based embedder and the
demo harness ships with a `MockQdrantClient`.

The run is deterministic: every random draw is seeded
(`np.random.default_rng(42)` for synthetic data,
`random_state=0` everywhere inside the patched modules, `random_state=7`
for the Gate 3b permutation test).

## Headline findings

- **Sandbox**: 6 bug-class issues fixed — see `CHANGES.md §sandbox.py`
  for full list. Most important: the original sandbox could not run on
  Windows at all (used `signal.SIGALRM`), and the in-process executor
  was open to a classic `().__class__.__mro__[1].__subclasses__()`
  escape because reflective dunder access was not blocked.
- **Gate 2**: 6 correctness/robustness fixes. The most impactful was
  G2-3 — when a "well-behaved" distribution still fails GVF, the
  original returned `prescribed_method=None`, which would have left the
  LLM with no actionable feedback.
- **Gate 3b**: 4 fixes. Crucially, the abstract advertises significance
  testing on the bivariate Moran's I, but the original always reported
  `p=0.0`. We added a 199-permutation test seeded by `random_state`.
- **Hybrid retrieval**: 5 fixes. The original always returned an
  all-zeros embedding, collapsing the semantic ranking entirely.

`CHANGES.md` enumerates every modification with severity tags
(`BLOCKER`, `SECURITY`, `CORRECTNESS`, `ROBUSTNESS`) and explains why
each was made.

## What is intentionally not covered by this demo

- The Tier-1 LLM call. The harness simulates the LLM by directly
  feeding "proposed" classifications into Gate 2; the abstract's
  Propose-Verify-Execute triad is otherwise faithful.
- The full Docker+gVisor backend in `sandbox.py`. Verified by code
  review only — no Docker on this machine.
- Gates 1, 3a, 4, 5, 6 — only Gates 2 and 3b were supplied.
