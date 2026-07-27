# AutoCarto-Agent (CartoLLM)

**A neuro-symbolic architecture for autonomous thematic cartography with deterministic spatial validation.**
The LLM proposes; the mathematics disposes: every numerical cartographic decision (classification breaks, projection, encoding choice) is either prescribed or vetoed by deterministic validation gates. Poster at the Spatiotemporal Data Science Symposium (STDS) 2026.

## Status — what runs today

All six roadmap phases (Fable Review/01_OPERATING_MANUAL.md §11) are implemented and tested; CI runs on every push (Linux + Windows × Python 3.12/3.14, plus a dedicated gVisor security job).

| Component | Status |
|---|---|
| Gates 1–6 (CRS, classification, univariate + bivariate spatial structure, projection distortion, color accessibility, completeness) | ✅ implemented + tested — see [docs/validation_gates.md](docs/validation_gates.md) |
| Orchestrator (Propose→Verify→Execute loop, mandate-and-retry, human-review escape hatch) | ✅ implemented + tested |
| LLM tier — `MockLLM` (deterministic, offline) + `NvidiaLLM` (real API, genuine intent parsing) | ✅ implemented + tested |
| Constrained codegen (3 audited templates, LLM fills slots only) | ✅ implemented + tested against real rendered figures |
| Hybrid spatial-first retrieval (bbox → exact refinement → semantic, antimeridian-safe) | ✅ implemented + tested, incl. against a live Qdrant instance |
| Real data connectors (Census ACS, CDC PLACES) + real embedder (sentence-transformers) | ✅ implemented + tested |
| Sandbox: sanitizer + Docker/gVisor container (non-root, no shell, network-isolated) | ✅ implemented + red-team tested (27 escape vectors, see [docs/architecture.md](docs/architecture.md#execution-two-genuinely-different-security-postures-deliberately)) |
| Air-gapped mode (`AUTOCARTO_OFFLINE=1`) | ✅ implemented; verified zero sockets opened |

## Quickstart

```bash
pip install -e .[dev]

autocarto demo                    # deterministic demo → ./output (figures, traces, log)
autocarto benchmark                # rejection-rate report → ./benchmarks
autocarto run "Map tree canopy loss in Atlanta"   # full orchestrator, MockLLM, offline
pytest                            # ~215 tests: gates, orchestrator, determinism, security
```

No API keys, no network, no Docker required for the core loop — it's fully offline and seeded by default. Rerunning the demo reproduces the statistical trace content byte-for-byte. See [docs/quickstart.md](docs/quickstart.md) for the real LLM tier, real data, air-gapped mode, and the sandbox image.

## Repository map

```
src/autocarto/            the package (execution/gates, execution/sandbox, semantic, data_fabric, demo, benchmark)
tests/                    pytest suite incl. golden-trace parity vs output/traces, tests/security/ red-team suite
data/                     pinned TIGER geometry + real ACS/CDC snapshots, SHA-256 manifests
docs/                     architecture.md, validation_gates.md, quickstart.md
scripts/                  figure generators, threshold-sensitivity sweep, snapshot regeneration
Dockerfile.sandbox        builds autocarto-sandbox:latest, the gVisor-isolated execution image
benchmarks/               committed mini-benchmark report (regenerate with `autocarto benchmark`)
output/                   blessed demo traces + figures the test suite compares against
Codes/                    original submission sources (frozen; superseded by src/autocarto)
Fable Review/             the full engineering review: operating manual, presentation guide, literature guide
docs/history/             archived abstract drafts and stale files
```

## Reproducing the poster numbers

- **Atlanta case (530 tracts, I_xy=+0.3262, p=0.0050, ρ=+0.9471; GVF 0.751→0.835 / 0.774→0.861):**
  `python scripts/gen_results_panel.py` — reads the pinned snapshot in `data/` (pass `--live` to re-query TIGERweb; requires `pip install -e .[geo]`).
- **Gate behavior + traces:** `autocarto demo` and compare `output/traces/` (the blessed copies are committed).
- **Rejection rates:** `autocarto benchmark` — the report embeds its corpus composition; quote the rate with it.

## Documentation

- [docs/architecture.md](docs/architecture.md) — the three-tier design, the authority-boundary contracts, what the sandbox is (and isn't) a security boundary for.
- [docs/validation_gates.md](docs/validation_gates.md) — every gate's statistic, threshold, rationale, and prescription.
- [docs/quickstart.md](docs/quickstart.md) — every command, including the real LLM tier, real data, air-gapped mode, and the sandbox image.
- [Fable Review/01_OPERATING_MANUAL.md](Fable%20Review/01_OPERATING_MANUAL.md) — the complete engineering history: every phase, every real bug found and how it was diagnosed and fixed, every claim's current disclosed status. Start here for the "why," not just the "what."
