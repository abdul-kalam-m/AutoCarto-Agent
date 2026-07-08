# AutoCarto-Agent (CartoLLM)

**A neuro-symbolic architecture for autonomous thematic cartography with deterministic spatial validation.**
The LLM proposes; the mathematics disposes: every numerical cartographic decision (classification breaks, projection, encoding choice) is either prescribed or vetoed by deterministic validation gates. Poster at the Spatiotemporal Data Science Symposium (STDS) 2026.

## V1 status — what runs today

| Component | Status |
|---|---|
| Gate 2 — classification diagnostic engine (prescriptive rejection, GVF) | ✅ implemented + tested |
| Gate 3b — bivariate justification (bivariate Moran's I, 199-perm test, Spearman) | ✅ implemented + tested |
| Hybrid spatial-first retrieval (bbox → semantic, antimeridian-safe) | ✅ implemented + tested |
| Sandbox sanitizer (AST import/attribute/open-mode blocking) | ✅ implemented + tested |
| Deterministic demo harness (offline, <3 s, byte-identical statistical traces) | ✅ `autocarto demo` |
| Mini-benchmark (naive-proposal rejection rates, regenerable) | ✅ `autocarto benchmark` |
| Gates 1/3a/4/5/6 · orchestrator · LLM tier · real-data connectors | 📋 specified in [Fable Review/03_V2_PRODUCTION_BLUEPRINT.md](Fable%20Review/03_V2_PRODUCTION_BLUEPRINT.md) |

## Quickstart

```bash
pip install -e .[dev]

autocarto demo                    # deterministic demo → ./output (figures, traces, log)
autocarto benchmark               # rejection-rate report → ./benchmarks
pytest                            # unit + golden-trace + determinism tests
```

No API keys, no network, no Docker required — the V1 core is fully offline and seeded. Rerunning the demo reproduces the statistical trace content byte-for-byte.

## Repository map

```
src/autocarto/            the package (execution/gates, execution/sandbox, data_fabric, demo, benchmark)
tests/                    pytest suite incl. golden-trace parity vs output/traces
data/                     pinned TIGER geometry snapshot + SHA-256 manifest
scripts/                  figure generators (Atlanta results panel, architecture diagram)
benchmarks/               committed mini-benchmark report (regenerate with `autocarto benchmark`)
output/                   frozen review-cycle artifacts: patched sources, blessed traces, figures (provenance)
Codes/                    original submission sources (frozen; superseded by src/autocarto)
Fable Review/             design review, operating manual, presentation guide, V2 blueprint, literature guide
docs/history/             archived abstract drafts and stale files
```

## Reproducing the poster numbers

- **Atlanta case (530 tracts, I_xy=+0.3262, p=0.0050, ρ=+0.9471; GVF 0.751→0.835 / 0.774→0.861):**
  `python scripts/gen_results_panel.py` — reads the pinned snapshot in `data/` (pass `--live` to re-query TIGERweb; requires `pip install -e .[geo]`).
- **Gate behavior + traces:** `autocarto demo` and compare `output/traces/` (the blessed copies are committed).
- **Rejection rates:** `autocarto benchmark` — the report embeds its corpus composition; quote the rate with it.

## Documentation

Start with [Fable Review/00_README.md](Fable%20Review/00_README.md): the operating manual (architecture, gap analysis, roadmap), the STDS presentation guide, the V2 production blueprint, the publication strategy, and the literature study guide.
