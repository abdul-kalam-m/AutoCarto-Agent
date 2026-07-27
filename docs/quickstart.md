# Quickstart

## Install

```bash
pip install -e .[dev]
```

This installs the core dependencies (numpy, scipy, pandas, matplotlib, jenkspy, pyproj, colorspacious) plus `pytest`/`esda` for running the test suite. Two optional extras add real geometry and retrieval support:

```bash
pip install -e .[geo]         # geopandas, libpysal -- real GeoDataFrames, spatial weights
pip install -e .[retrieval]   # qdrant-client -- real vector search (Docker Qdrant instance)
pip install -e .[embeddings]  # sentence-transformers -- real semantic embeddings (~80MB one-time download)
```

Nothing above requires an API key or network access at runtime except the one-time `sentence-transformers` model download. Everything else — geometry, demo data, benchmark corpus — is either computed or loaded from a snapshot committed in `data/`.

## The deterministic demo (start here)

```bash
autocarto demo
```

Runs Gate 2 (classification diagnostics), Gate 3b (bivariate correlation), hybrid retrieval (mock Qdrant), and the sandbox sanitizer end to end against seeded synthetic data. Writes figures, JSON traces, and a run log to `./output/`. Takes under 3 seconds, uses zero network, and reproduces byte-identical statistical traces across runs — this determinism guarantee is load-bearing (see [`tests/test_determinism.py`](../tests/test_determinism.py)).

```bash
autocarto benchmark
```

Regenerates the mini-benchmark: a scripted corpus of 42 scenarios across all six gates, scored against the correct decision (not against what the system happened to output), currently 97.4% strict decision accuracy with the one miss disclosed and explained.

## Running the full orchestrator

```bash
autocarto run "Map tree canopy loss in Atlanta"
```

Drives the actual Propose→Verify→Execute loop: an LLM proposal, the six validation gates, a mandate-and-retry cycle on rejection (capped at 3 iterations, then human review), constrained code generation, and a rendered map. Defaults to `MockLLM` (deterministic, rule-based, zero network) and the synthetic Atlanta dataset.

```bash
# Real ACS income + CDC PLACES asthma data (still offline -- both are
# committed snapshots, not live-fetched)
autocarto run "Map median household income" --data real

# Real open-source LLM (NVIDIA-hosted Llama 3.1 70B) -- requires
# NVIDIA_API_KEY in the environment or a .env file
autocarto run "Show income vs asthma prevalence" --llm nvidia --data real
```

Every run writes `trace.json` (the full iteration-by-iteration gate history) and, on success, `map.png` to `--out` (default `./output/run`).

## Air-gapped mode

```bash
AUTOCARTO_OFFLINE=1 autocarto run "..."
```

Structurally disables every network-capable code path (`--llm nvidia`, `SentenceTransformerEmbedder`) rather than silently substituting something else — a request for one of these raises a clear error instead of quietly downgrading. See [`src/autocarto/offline.py`](../src/autocarto/offline.py) and [`tests/test_offline_mode.py`](../tests/test_offline_mode.py) (which proves zero sockets are opened during a full demo run under this flag, not just that the network-capable classes go unused).

## Running the test suite

```bash
pytest
```

~215 tests: gate behavior (branch-complete per gate), the orchestrator's full convergence loop, codegen (each template's output actually executed against a real GeoDataFrame, not just parsed), determinism + golden-trace parity, the sandbox sanitizer, and the offline-mode guarantees. A handful skip cleanly when their dependency isn't available (a live Qdrant instance, `AUTOCARTO_LIVE_LLM_TESTS=1` for the real-NVIDIA-API test, a working `--runtime=runsc` Docker runtime for the red-team suite) — see each test module's skip reason rather than assuming a skip means something is broken.

```bash
pytest tests/security/test_escapes.py -v   # red-team suite; skips without gVisor
```

The red-team suite's 27 escape vectors only actually execute where gVisor is set up (see [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)'s `gvisor-security` job) — on a normal dev machine or the main CI matrix, they skip rather than silently pass, which would be a much worse failure mode than an honest skip.

## Building and running the sandbox image locally

```bash
docker build -f Dockerfile.sandbox -t autocarto-sandbox:latest .
```

This is the container `SandboxExecutor(backend="docker")` runs LLM-generated code inside — non-root, no shell, `--network=none`, `--read-only`, `--cap-drop=ALL`, `--pids-limit=64`. Building and running it does **not** require gVisor; gVisor (`--runtime=runsc`) adds an additional syscall-interception layer on top of the base container isolation and needs Linux (see `.github/workflows/ci.yml`'s `gvisor-security` job for how CI sets it up). See [`architecture.md`](architecture.md#execution-two-genuinely-different-security-postures-deliberately) for what this container is, and is not, a security boundary for.

## Where things are

| Path | What |
|---|---|
| `src/autocarto/execution/gates/` | The six validation gates |
| `src/autocarto/orchestrator.py` | The Propose-Verify-Execute state machine |
| `src/autocarto/semantic/` | LLM client interface, `MockLLM`, real `NvidiaLLM`, constrained codegen |
| `src/autocarto/execution/sandbox.py` | Sanitizer + sandboxed execution (dev in-process and production Docker/gVisor backends) |
| `src/autocarto/data_fabric/` | Hybrid spatial-first retrieval, real data connectors (ACS, CDC PLACES), embedders |
| `tests/` | pytest suite; subdirectories mirror `src/autocarto/`'s structure |
| `data/` | Committed geometry/data snapshots + SHA-256 manifests |
| `output/` | Blessed demo traces + figures the test suite compares against |
| `Fable Review/01_OPERATING_MANUAL.md` | The full engineering history: what's built, what's disclosed-as-open, every real bug found and how it was fixed |

For the "why," not just the "what," [`architecture.md`](architecture.md) and [`validation_gates.md`](validation_gates.md) are the next stop.
