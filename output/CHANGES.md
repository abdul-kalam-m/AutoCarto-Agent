# CHANGES — AutoCarto-Agent code review and run

This document lists every modification made to the four source files in
`Codes/` plus the rationale, grouped by file. Originals are untouched;
patched copies live in `output/codes_patched/`. Every patched line is
annotated with a `# PATCH:` comment so the diff is reviewable in place.

The patch criteria were:

1. **Air-gap tightening** — close holes in the sandbox that would let
   LLM-generated code escape its restrictions.
2. **Cross-platform correctness** — the original sandbox crashed on
   Windows because of Unix-only primitives.
3. **Statistical correctness** — the abstract makes claims (fixed seed,
   significance testing for Gate 3b) that the code did not honour.
4. **Runnability** — replace external dependencies (Qdrant, OpenAI) with
   deterministic in-process fallbacks so the modules can be exercised in
   air-gapped tests.

Bug severities below: `BLOCKER` = code refuses to run / panics;
`SECURITY` = sandbox escape; `CORRECTNESS` = wrong answer or silent
inconsistency with abstract; `ROBUSTNESS` = handles fine inputs but
fragile under edge cases.

---

## sandbox.py

### S1. `signal.SIGALRM` is Unix-only — BLOCKER on Windows
**Original** (L174-188): the timeout wrapper unconditionally called
`signal.signal(signal.SIGALRM, ...)` and `signal.alarm()`. Both raise
`AttributeError` on Windows because `signal` does not define `SIGALRM`
there.

**Fix**: replaced with a cross-platform threading-based timeout in
`_execute_inprocess`. The user-supplied code now runs in a daemon
thread, and the main thread joins with a deadline. If the deadline
elapses, we return a `timeout` `SandboxResult` and let the daemon be
reaped at interpreter exit (CPython does not allow safe thread
cancellation without C extensions; the harness should treat timeouts as
hard failures).

**Why this is acceptable**: the in-process executor is documented as
*development only*. The production path is gVisor + Docker, where the
container's own SIGKILL handles timeouts. The threading shim only needs
to keep development working on every platform without crashing.

### S2. `__builtins__`-dict reflection escape — SECURITY
**Original** (L297, 310): the in-process executor injected a custom
`safe_builtins` dict but exposed `getattr`, `hasattr`, and pure-Python
`type` reachable via `(1).__class__`. The classic escape
`().__class__.__mro__[1].__subclasses__()` walks the class tree to
arbitrary code execution.

**Fix**:
- Added an AST pass that flags any `.attr` access whose name is in a
  hard-coded `DANGEROUS_ATTRIBUTES` set (`__class__`, `__bases__`,
  `__mro__`, `__subclasses__`, `__globals__`, `__builtins__`,
  `__dict__`, `__getattribute__`, `__reduce__`, `__reduce_ex__`,
  `__import__`, `__loader__`, `__spec__`, `__code__`, `__closure__`).
- Added a call-site check that flags `getattr(x, '__class__')` style
  reflection.
- Removed `getattr`, `hasattr` from `safe_builtins`. Legitimate
  scientific code (numpy/pandas) does not need these at the sandbox
  boundary because the modules already expose typed attributes
  directly.

Verified with the `reflection_escape` test case in `demo.py`, which is
now rejected with three violations.

### S3. Bypassable regex on `open(..., 'w')` — SECURITY / ROBUSTNESS
**Original** (L55-56): `re.compile(r"open\s*\(.*['\"]w")` is bypassed by
`open(path, mode='w')` (keyword form), `open(path, "w+")` was caught
but `open(path, "x")` (exclusive create) and `open(path, mode='a+')`
were not. The pattern also produced false positives in docstrings.

**Fix**: replaced with an AST-level inspection of `ast.Call` nodes
named `open`, extracting the `mode` argument from positional index 1
*or* the `mode=` keyword, then checking whether any character is in
`{w, a, x, +}`. Two new test cases in `demo.py`
(`blocked_open_write`, `blocked_open_write_kwarg`) confirm both forms
are now rejected.

### S4. Regex false positives in docstrings — ROBUSTNESS
**Original**: every `BLOCKED_PATTERNS` regex ran against raw source, so
the word "subprocess" appearing in a docstring would trigger
`Blocked pattern detected`. This breaks the second-most-common LLM
output mode: writing a function and documenting it.

**Fix**: added `_strip_strings_and_comments(code)` that walks the AST,
replaces string-literal spans with spaces, and drops everything after
`#` on each line. The regex pass then runs on the scrubbed buffer.
Verified by `docstring_mentions_subprocess` test case (passes
sanitisation, executes successfully).

### S5. Stylesheet injection used hard-coded Unix path — BLOCKER
**Original** (L168-170):
`sanitized.replace("import matplotlib.pyplot as plt",
"import matplotlib.pyplot as plt\nplt.style.use('/styles/policy_report.mplstyle')")`.
The absolute Unix path does not exist on Windows, and the literal
replacement only handles one of the two common pyplot import idioms
(`from matplotlib import pyplot as plt` was missed).

**Fix**:
- Made the stylesheet path configurable via `SandboxExecutor(style=...)`,
  defaulting to matplotlib's built-in `"default"` so the injection
  cannot crash a clean run.
- JSON-quoted the path so a stray quote in the configured value cannot
  break the generated source.
- Added a second replacement branch for the `from matplotlib import
  pyplot as plt` form.

### S6. Wrapper inserted unwhitelisted imports — BLOCKER (latent)
**Original** wrapper (L173-188) prepended `import signal` and
`import sys`, neither of which is in `ALLOWED_IMPORTS`. The wrapper ran
*after* sanitisation, so the regex/AST checks didn't see it; but the
in-process executor's `_safe_import` would have rejected those imports
at runtime, failing the whole call.

**Fix**: the wrapper is gone. The threading-based timeout in
`_execute_inprocess` does not need to inject anything into the user
code. The Docker backend's container is responsible for its own
timeout via `subprocess.run(timeout=...)`.

---

## gate2_classification.py

### G2-1. Non-deterministic Shapiro-Wilk sampling — CORRECTNESS
**Original** (L66):
`sample = x_clean if n <= 5000 else np.random.choice(x_clean, 5000, replace=False)`.
The abstract claims "fixed random seed"; this call used the global
`np.random` state, making results irreproducible across runs.

**Fix**:
- Added `random_state: int = 0` to `DistributionProfile.from_array`,
  `ClassificationDiagnosticEngine.__init__`, and the standalone
  `characterize_distribution` helper.
- Switched to `np.random.default_rng(random_state).choice(...)` so the
  sample is deterministic for a given seed.

### G2-2. Zero-inflated prescription can produce duplicate breaks — CORRECTNESS
**Original** (L244): for ≥40 % zeros (the trigger condition), the 50th
percentile is also 0, producing breaks of `[0.0, 0.0, p90, max]`.
`np.digitize` then creates an empty interior class and GVF accounting
gets nonsense values.

**Fix**: added module-level `_dedupe_breaks(breaks)` that collapses
adjacent duplicates while preserving monotonicity, applied to every
prescription path (`zero_inflated`, `log_transform`, `head_tail`) and
to the GVF computation.

### G2-3. Well-behaved + low GVF returned a null instruction — CORRECTNESS
**Original** (L197-207): the `else` branch returned the prescription
dict from `_get_prescription`, but for `well_behaved` that dict is
`{"method": None, "breaks": None, "instruction": None}`. The LLM
received a non-pass verdict with nothing to do about it.

**Fix**: when the diagnosis is well-behaved but GVF falls below
threshold, synthesise a quantile-break fallback so the prescription is
always actionable: `quantile_breaks = percentile(values, [0,20,40,60,80,100])`,
deduped, with a clear instruction string.

### G2-4. `_prescribe_unique_values` used a no-op NaN filter — CORRECTNESS
**Original** (L315): `values[values > -np.inf]` — this filter is
effectively `[True]*n` because `NaN > -inf` is `False` only for actual
NaN, but the comparison silently keeps everything. The intent was to
remove non-finite values.

**Fix**: replaced with `values[np.isfinite(values)]` so NaN/Inf never
appear as spurious "unique classes".

### G2-5. Head-tail-break loop unbounded — ROBUSTNESS
**Original** (L371-380): `while len(remaining) > 1:` with a `break`
when no head is found. Pathological tied inputs could in principle loop
many times.

**Fix**: hard cap at 64 iterations. Real datasets terminate in
≤log₂(N) iterations; the cap is purely defensive.

### G2-6. `iteration_count` persists across calls — ROBUSTNESS
**Original** (L385-388): `reset()` exists but is easy to forget. If the
caller reuses an engine instance across variables, the second variable
inherits the first's iteration count.

**Decision**: kept the existing API (reset is the caller's
responsibility) but `demo.py` calls `engine.reset()` before every
variable to model correct usage.

---

## gate3b_bivariate_correlation.py

### G3b-1. `bivariate_morans_p` was always 0.0 — CORRECTNESS
**Original** (L122): the docstring promised a permutation test, the
comment said "Permutation test omitted for brevity", and the field was
always 0.0. This propagates into the JSON trace as a misleading
significance claim. The abstract explicitly says Gate 3b "calculates
bivariate Moran's I"; reporting `p=0.0` is worse than reporting no
p-value.

**Fix**: implemented a real permutation test in
`_permutation_pvalue`. Default 199 permutations under the null of no
spatial cross-association (we permute `y_std` only). The pseudo
p-value is `(M+1)/(R+1)` where `M` is the count of permutations whose
|I_xy| ≥ observed. Seed defaults to 0 (configurable per `evaluate`
call). Verified end-to-end: the strong-correlation scenario returns
p=0.005, the independent-variables scenario returns p=0.580.

### G3b-2. Division by zero on constant variables — CORRECTNESS
**Original** (L85-86):
`(x_clean - mean) / std`. For a constant variable `std=0` produces NaN
silently and the downstream `numerator/denominator` becomes NaN.

**Fix**: extracted `_zscore(v)` that returns `None` if `std < 1e-12`,
and the evaluator returns a clean REJECT with an explicit "variable is
constant" instruction.

### G3b-3. NumPy scalars broke JSON serialisation — CORRECTNESS
**Original**: `to_dict()` returned `numpy.float64` for the four numeric
fields, which `json.dumps` cannot encode without a custom encoder.

**Fix**:
- Coerced inputs at the top of `evaluate` (`x = np.asarray(x, dtype=float)`).
- Cast every result back to Python `float`.
- The demo's `JsonSerializable` encoder handles the residual cases
  defensively.

### G3b-4. `standardized=True` was the default — surprising behaviour
**Original** (L55): `standardized: bool = True`. Most callers pass raw
variables; defaulting to "already z-scored" silently caused biased
Moran's I when callers didn't read the kwarg.

**Fix**: flipped default to `standardized=False`. The demo passes raw
variables and gets correct results without surprises.

---

## hybrid_retrieval.py

### H1. `_embed` returned a constant zero vector — CORRECTNESS
**Original** (L238): `return [0.0] * 1536`. With identical embeddings
for every query, cosine similarity is undefined (zero norm) and
semantic ranking collapses to "insertion order".

**Fix**:
- Added module-level `_hash_embedding(text, dim=1536, seed=0)` that
  derives a stable unit-norm pseudo-vector from the SHA-256 of the
  input text. Production deployments should inject a real embedder
  (OpenAI, instructor-xl, etc.) via `HybridRetrieval(embedder=...)`.
- `_embed` calls the injected embedder when provided, otherwise falls
  back to the deterministic hash. The fallback is documented as
  air-gap-only.

### H2. MultiPolygon bbox only walked the first polygon's outer ring — CORRECTNESS
**Original** (L141):
`coords = [c for poly in geometry["coordinates"] for c in poly[0]]`.
The `poly[0]` selects the first ring of each polygon but the code only
iterates each polygon's first ring once — perfectly correct for the
outer envelope, but it silently ignores holes (interior rings) on
non-trivial MultiPolygons.

**Fix**: iterate every polygon and every linear ring inside it. The
result is identical for simple shapes and correct for complex ones.

### H3. No support for `Point` geometries — ROBUSTNESS
Some upstream APIs return `Point` features. The original raised
`ValueError`.

**Fix**: added a `Point` branch that returns a degenerate bbox
`[lon, lat, lon, lat]`. The downstream BBOX intersection then matches
any dataset whose bbox contains the point.

### H4. Qdrant import was unconditional — RUNNABILITY
**Original**: `from qdrant_client.models import Filter, FieldCondition,
Range` at function scope (L160, L211). Importing the module raised
`ModuleNotFoundError` in environments without `qdrant-client`, even
when callers wanted to mock the client (as our test harness does).

**Fix**: wrapped both imports in `try/except ImportError`, falling
back to plain-dict filter spec. The test harness's `MockQdrantClient`
accepts both formats.

### H5. Scroll loop had no iteration cap — ROBUSTNESS
**Original** (L186-199): `while True` loop with two termination
conditions. A misbehaving Qdrant server (or a mock with a bug) could
wedge the caller.

**Fix**: bounded `for _ in range(10_000)` cap. At Qdrant's default page
size of 100 this is a million-item ceiling — well above any reasonable
STAC catalog.

---

## Round-2 reviewer patches

These four additional issues were raised in post-submission jury review.

### R2-1. Negative values in `_prescribe_log_transform` silently clamped to zero — CORRECTNESS (was gate2 G2-new)

**Reviewer**: "If a user prompts 'Map population decline in Rust Belt counties,' the variable
will contain negative values. Your code silently overwrites every negative growth rate to 0
with `np.maximum(values, 0)`. Gate 2 will then misdiagnose the resulting zero-inflated
distribution."

**Original** (L318): `transformed = np.log1p(values[values >= 0])` + the code snippet
contained `np.maximum(values, 0)`, both of which silently discard negative values.

**Fix** (in `_prescribe_log_transform`): added an explicit `if float(np.min(values)) < 0`
branch at the top of the method. When true, the method prescribes **arcsinh (Inverse
Hyperbolic Sine)** transform — `np.arcsinh(values)` — which is defined for all reals and
is scale-symmetric around zero. The break points are computed in arcsinh space via Jenks,
then back-transformed via `np.sinh`. The mandated code snippet no longer contains any
`np.maximum` clamping.

**Demonstrated**: the `negative_values_arcsinh` test case uses a chi-squared(df=2) shifted by
-0.8 (skewness≈1.6, min≈-0.8). Gate 2 correctly diagnoses `heavy_right_skew` and prescribes
`arcsinh_transform_then_jenks`.

### R2-2. Antimeridian (dateline) blindspot — CORRECTNESS (was hybrid_retrieval H-new)

**Reviewer**: "If the LLM proposes mapping the Aleutian Islands or Fiji, the polygon crosses
the 180th meridian. `min(lons)` might be 179° and `max(lons)` might be -179°. Your Qdrant
filter searches for items where `longitude <= -179 AND longitude >= 179`, returning exactly
zero results."

**Original** (L183-185): `return [min(lons), min(lats), max(lons), max(lats)]` — flat-earth
assumption, no antimeridian detection.

**Fix**: replaced `_geometry_to_bbox` with `_extract_bboxes` (the old name is kept as a
thin shim for backward compatibility). When `max(lons) - min(lons) > 180`, the function
splits the polygon into two non-crossing bbox shards:

- `east_bbox = [min(positive_lons), min_lat, 180.0, max_lat]`
- `west_bbox = [-180.0, min_lat, max(negative_lons), max_lat]`

`retrieve()` now calls `_spatial_filter` once per shard and unions the returned IDs. The
Qdrant query becomes a logical OR across two correct axis-aligned bboxes. For catalog items
that straddle the antimeridian, the STAC indexer must also split them into east/west records
following the same convention (demonstrated in the demo's mock catalog).

**Demonstrated**: the `seabird habitat coastal alaska` query with an antimeridian-crossing
polygon returns `spatial_candidates=2 items=['aleutian-seabird-east', 'aleutian-seabird-west']`.
Without the fix, this returns zero results.

### R2-3. No row-standardisation enforcement on weights matrix — CORRECTNESS (was gate3b G3b-new)

**Reviewer**: "If the Compute Router passes a raw contiguity matrix or a sparse distance-decay
matrix from PostGIS, this calculation will wildly inflate or deflate the statistic."

**Original**: docstring said "row-standardized" but there was no enforcement. A raw binary
queen weights matrix (row sums ≈ 4-8, not 1) would silently produce an I_xy ten times too
small. A KNN-k=20 matrix (row sums=20) would produce a stat twenty times too large.

**Fix**: inserted an `np.allclose(row_sums, 1.0, atol=1e-6)` check at the top of `evaluate`
(after coercing W to `float64`). Failure raises a `ValueError` with an actionable message
and the explicit correction formula `W_std = W / W.sum(axis=1, keepdims=True)`. This
converts a silent corruption into a hard, visible contract violation.

**Demonstrated**: passing a fully-connected binary matrix (row sums=49) raises:
`ValueError: Gate 3b requires a row-standardized weights matrix ... Received row sums in [49.0000, 49.0000]`.

### R2-4. `_execute_inprocess` still called `exec()` in production — SECURITY (was sandbox S-new)

**Reviewer**: "Strip `_execute_inprocess` entirely from the production repository. If
Docker/gVisor is unavailable, the pipeline must throw a hard `RuntimeError` rather than
falling back to an insecure `exec()`."

**Original** (after round-1 patch): a threading-based `exec()` was still available in
`SandboxExecutor` when `backend="inprocess"`.

**Fix**:
- `SandboxExecutor.__init__` now raises `RuntimeError` immediately if `backend='inprocess'`
  is passed. No exec() path is reachable from the production class.
- `SandboxExecutor.execute()` raises `RuntimeError` for any backend other than `docker`
  or `pyodide`, making the production class strictly refuse any unknown fallback.
- `SandboxExecutor._execute_inprocess()` is replaced with a docstring-only tombstone that
  raises `RuntimeError` unconditionally, explaining why and directing maintainers to
  `_DevOnlySandboxExecutor`.
- All exec() logic is moved into `_DevOnlySandboxExecutor` — a clearly-named subclass with
  a leading underscore, a mandatory dev-only constructor that bypasses the guard, and a
  comment requiring CI to enforce that no non-test file imports it.

**Demonstrated**: `SandboxExecutor(backend='inprocess')` raises `RuntimeError` immediately;
the demo harness uses `_DevOnlySandboxExecutor()` explicitly and this is reflected in the
log header (`=== Sandbox (sanitizer + _DevOnlySandboxExecutor) ===`).

---

## environment.yml — separate `environment_fixed.yml`

### E1. `visvalingam-whyatt==0.2.1` does not exist on PyPI
The correct package name is `visvalingamwyatt` (no hyphen, no
underscore). `pip install visvalingam-whyatt==0.2.1` fails. The package
is not actually imported by any of the four supplied files, but a
`conda env create -f environment.yml` would abort before installing
anything else.

**Fix**: replaced with `visvalingamwyatt==0.2.0` (latest existing
version) and added a comment explaining the rename. Saved as
`output/codes_patched/environment_fixed.yml`.

---

## What was NOT changed

- The `BLOCKED_PATTERNS` list. The original list is a reasonable
  blacklist; the patches harden the *matching procedure* rather than
  the list contents.
- The `ALLOWED_IMPORTS` whitelist. Adding modules is a policy decision
  that belongs with the cartographic templates, not a sandbox fix.
- The gVisor command-line in `_execute_docker`. Untested in this
  environment (no Docker available); preserved verbatim.
- The Pyodide backend. Untouched stub.

## Behavioural sanity checks (from RUN_LOG.txt)

| Case | Expected | Observed |
|---|---|---|
| Gate 2 well_behaved (N(50,12)) | passed, GVF > 0.6 | passed, GVF = 0.894 |
| Gate 2 zero_inflated (49.8% zeros) | rejected, prescribe break@0 | rejected, prescribed `manual_break_at_zero_then_fisher_jenks`, breaks=[0, 7.86, 20.61, 68.88] |
| Gate 2 heavy_right_skew (g1=3.65) | rejected, prescribe log+jenks | rejected, prescribed `log_transform_then_jenks` |
| Gate 2 discrete_ordinal (5 unique values) | rejected, prescribe unique_values | rejected, prescribed `unique_values`, breaks=[1,2,3,4,5] |
| Gate 2 negative+skewed (chi-sq shifted, min=-0.8) | rejected, prescribe arcsinh | rejected, prescribed `arcsinh_transform_then_jenks` |
| Gate 3b SAR-coupled (ρ=0.94) | APPROVE | APPROVE, I_xy=+0.476, p=0.005 |
| Gate 3b weakly coupled (ρ=0.31) | WARN | WARN, I_xy=+0.116, p=0.005 |
| Gate 3b independent SAR fields | REJECT | REJECT, I_xy=-0.025, p=0.580 |
| Retrieval: Atlanta query | 3 spatially-overlapping items | 3 items: atl-canopy, atl-noise, cdc-asthma |
| Retrieval: Manhattan query | 2 spatially-overlapping items | 2 items: nyc-vision-zero, cdc-asthma |
| Retrieval: Aleutian Islands (antimeridian) | 2 items (east + west shard) | 2 items: aleutian-seabird-east, aleutian-seabird-west |
| Gate 3b raw binary W (row sums=49) | ValueError raised | ValueError: row sums in [49.0, 49.0] |
| SandboxExecutor(backend='inprocess') | RuntimeError raised | RuntimeError: backend='inprocess' not permitted |
| Sandbox safe numpy | pass+execute | pass+execute |
| Sandbox `subprocess` import | block | block (2 violations) |
| Sandbox `eval()` | block | block |
| Sandbox `open(path,'w')` | block | block |
| Sandbox `open(path,mode='a+')` | block | block (kwarg form) |
| Sandbox reflection escape | block | block (3 violations: __subclasses__, __mro__, __class__) |
| Sandbox docstring mentions "subprocess" | pass | pass (the original would have rejected) |

All 20 cases behave as designed.
