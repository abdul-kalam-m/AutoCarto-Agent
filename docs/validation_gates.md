# Validation gates

Six deterministic gates sit between an LLM proposal and a rendered map. Each returns a `GateResult` (`src/autocarto/contracts.py`): a decision (`PASS`/`WARN`/`REJECT`), the statistic(s) that produced it, and — for every `REJECT` — a non-`None` `Prescription` (enforced structurally: `GateResult.__post_init__` raises `ValueError` if a `REJECT` ever lacks one). A gate never merely says "no"; it says what would make the proposal correct, and the orchestrator mandates that exact fix on the next iteration rather than asking the LLM to guess again.

All thresholds below live in [`src/autocarto/config.py`](../src/autocarto/config.py) as a single, versioned, rationale-carrying registry — `THRESHOLDS.gate2.gvf_threshold`, etc. — so a threshold change is a one-line diff with a citable reason, not an archaeology exercise through gate source files.

None of these thresholds have been through a formal calibration sweep against ground truth (Blueprint research task R-1, still open) except where noted below for Gate 3a/3b/2/4, where [`scripts/threshold_sensitivity.py`](../scripts/threshold_sensitivity.py) computed real ROC/AUC curves against independent SAR-generation ground truth. Where a threshold is "conventional" rather than calibrated, that's stated plainly, not implied to be more rigorous than it is.

---

## Gate 1 — CRS integrity

**File:** [`execution/gates/gate1_crs.py`](../src/autocarto/execution/gates/gate1_crs.py) · **Tests:** 8

**What it checks:** whether the dataset's CRS is appropriate for the map's purpose — specifically, whether a density/rate choropleth is about to be computed in a *geographic* CRS (lat/lon degrees), where a degree of longitude is not a constant length and area-based statistics silently misrepresent the data.

**Threshold:** not a numeric sweep — a declarative whitelist of known equal-area EPSG codes per AOI scale (CONUS Albers 5070, Equal Earth 8857, a handful of state-level Albers projections). This is a correctness requirement, not a calibrated statistic: either the CRS is equal-area for a density/rate purpose or it isn't.

**Decision:** `REJECT` if `map_purpose` implies a density/rate calculation and the current EPSG is not on the equal-area whitelist; `PASS` otherwise. A CRS mismatch during a spatial join (joining two layers in different CRSs) is also caught and rejected.

**Prescription on REJECT:** reproject to the whitelisted equal-area CRS for the dataset's scale (`gdf = gdf.to_crs(epsg=<n>)`), or, for a join mismatch, reproject the join layer to match.

---

## Gate 2 — Classification diagnostic engine

**File:** [`execution/gates/gate2_classification.py`](../src/autocarto/execution/gates/gate2_classification.py) · **Tests:** 15+ (plus golden-trace/determinism coverage)

This is the project's core intellectual contribution: not a binary pass/fail, but a diagnostic → prescriptive-rejection pipeline. It characterizes *why* a classification is wrong and mandates the exact fix, rather than vetoing and leaving the LLM to guess again.

**Statistic:** Goodness of Variance Fit (GVF) — `1 − (within-class variance / total variance)` — for the proposed classification, plus a distribution-shape diagnosis (`well_behaved`, `zero_inflated`, `heavy_right_skew`, `outlier_dominated`, `discrete_ordinal`, `insufficient_variance`) computed independently of whatever classification was proposed.

**Threshold:** GVF ≥ **0.6** (0.6–0.8 "acceptable," >0.8 "excellent" — the standard Jenks/Coulson cartographic-classification convention). Diagnosis triggers: zero-inflation ≥ **40%** zeros, outliers > **10%** beyond 1.5·IQR, discrete-ordinal ≤ **10** unique values, heavy-skew at `g1 > 1.5 ∧ Shapiro p < 0.01`. These four are the values shipped since the original review pass, not independently swept — see the AUC-based partial calibration below.

**Decision logic** (order matters — diagnosis dispatch happens before the GVF check, and zero-inflation is checked before skew, since a distribution can trigger both and the more specific diagnosis should win):
1. Characterize the raw distribution shape, independent of the proposed classification.
2. If GVF ≥ 0.6, `PASS` regardless of diagnosis (a correctly-fit classification is correct even on an awkward distribution).
3. If GVF < 0.6, `REJECT` with a diagnosis-specific mandate.

**Prescription by diagnosis:**

| Diagnosis | Mandated method |
|---|---|
| `zero_inflated` | Manual break at 0, then Fisher-Jenks on the non-zero tail |
| `heavy_right_skew` (all values ≥ 0) | `log1p` transform, then Jenks, back-transformed breaks |
| `heavy_right_skew` (negative values present) | `arcsinh` transform (log-invalid for negatives), then Jenks |
| `outlier_dominated` | Head-tail breaks (recursive mean-split, designed for heavy tails) |
| `discrete_ordinal` | Unique-value classification (no continuous breaks) |
| `insufficient_variance` | Single class, annotated as near-constant |

Every prescription's `breaks` field carries the exact, full-precision values the LLM must transcribe verbatim (`Prescription.params["breaks"]`) — the accompanying human-readable `instruction` text embeds the same values rounded to 6 significant figures (readability, and immunity to harmless last-bit float drift across platforms; the numeric field stays full precision).

**Real-world validation:** [`scripts/threshold_sensitivity.py`](../scripts/threshold_sensitivity.py) computed honestly-labeled *rate* curves (not accuracy curves — no independent ground truth exists for "the right GVF cutoff") across the GVF threshold range. One genuine open finding, disclosed rather than smoothed over: the `heavy_right_skew` prescription only clears the GVF floor 82.5% of the time even when correctly applied — the weakest of the five prescriptive regimes.

**A real bug this gate exposed (2026-07-27):** an earlier version's decision logic required `diagnosis == "well_behaved"` *in addition to* GVF ≥ 0.6 — since the diagnosis label describes the raw distribution shape and never changes to `"well_behaved"` just because a correct classification was supplied, this meant an exactly-transcribed, GVF=0.967 prescription was rejected *forever*, with no LLM action able to ever pass. Undiscovered until the orchestrator actually drove a second iteration in testing — every prior test checked only the first rejection's content, never a resubmission. Fixed by removing the redundant diagnosis check.

---

## Gate 3a — Univariate spatial structure (Moran's I)

**File:** [`execution/gates/gate3a_spatial_autocorrelation.py`](../src/autocarto/execution/gates/gate3a_spatial_autocorrelation.py) · **Tests:** 6

**What it checks:** whether a choropleth's variable has *any* spatial structure at all. A variable with no spatial autocorrelation renders as visual noise — technically a valid map, substantively meaningless as a choropleth.

**Statistic:** global Moran's I, hand-rolled (not a wrapped `esda.Moran` call, to keep full seeded-permutation control matching Gate 3b's pattern) — cross-validated exactly against `esda.Moran` in tests (matches to 1e-9 before rounding).

**Threshold:** `|I| < 0.10` rejects (the conventional "negligible spatial autocorrelation" cutoff — Moran's I ranges roughly [−1, 1] under typical contiguity weights, and values this close to the CSR expectation of −1/(N−1) are indistinguishable from noise for cartographic purposes). 999 permutations for the p-value (the PySAL/esda inference-grade default), α = 0.05.

**Decision:** `REJECT` below the |I| floor regardless of p-value significance (a genuinely negligible I that happens to test "significant" at large N is still not visually meaningful on a map). This is one of the system's two built-in **negative controls** — the `white_noise` benchmark regime — where `REJECT` is *permanently* correct: no proposal iteration can ever manufacture spatial structure that isn't in the data.

**Real-world validation:** AUC 0.915 against independent SAR-generation ground truth ([`scripts/threshold_sensitivity.py`](../scripts/threshold_sensitivity.py)) — the one gate with genuine accuracy-curve (not just rate-curve) validation, since SAR draws provide known ground-truth spatial structure independent of the gate's own statistic.

---

## Gate 3b — Bivariate spatial cross-correlation

**File:** [`execution/gates/gate3b_bivariate_correlation.py`](../src/autocarto/execution/gates/gate3b_bivariate_correlation.py) · **Tests:** 15+ (plus 12 null-model comparison tests)

**What it checks:** for a bivariate choropleth (two variables), whether they're actually spatially related to each other — not just each individually autocorrelated, and not just globally correlated ignoring space.

**Statistics:** bivariate Moran's I (I_xy — does x here predict y nearby?), Spearman's ρ (non-spatial rank correlation, reported alongside for context), and a permutation-based p-value.

**Thresholds:** `APPROVE` at `|I_xy| > 0.15 ∧ |ρ| > 0.20`; `WARN` at `|I_xy| > 0.08 ∧ |ρ| > 0.10`; `REJECT` below both. Roughly half Gate 3a's univariate cutoff, reflecting that a bivariate cross-statistic is noisier. 199 permutations by default (minimum resolvable p-value 1/200 = 0.005 — a runtime/resolution tradeoff for interactive use).

**Null model:** the default (`null_model="free_permutation"`) randomly reshuffles y with no spatial constraint, which is a *permissive* null — it can under-detect that a spurious correlation comes from two independently-autocorrelated fields rather than genuine co-location. An opt-in `null_model="toroidal_shift"` mode (added 2026-07-27, R-2) instead performs a rigid wrap-around lattice translation of y, which preserves y's own spatial autocorrelation exactly and randomizes only its *alignment* with x. Measured, honest result: false positives on a known problem case improved from 2/3 to 1/3 of seeds — but with a disclosed, real specificity/power tradeoff (one previously-detected true relationship flipped to a false negative under the stricter null). The default decision matrix does **not** use the p-value at all (only |I_xy|/|ρ| magnitude) — this was true before the null-model study and remains true after it; wiring significance into the decision would need its own calibration pass, not a silent addition.

**Prescription on REJECT:** none in the corrective sense Gate 2 provides — a genuinely uncorrelated pair cannot be prescribed into correlation. This is the system's second built-in negative control (the `independent` benchmark regime): `REJECT` here is permanently correct, and the prescription is simply "do not render this as a bivariate map."

---

## Gate 4 — Projection distortion (Tissot)

**File:** [`execution/gates/gate4_projection_distortion.py`](../src/autocarto/execution/gates/gate4_projection_distortion.py) · **Tests:** 5

**What it checks:** how much a chosen projection distorts *area* across the AOI — relevant whenever the map purpose involves visually comparing region sizes (choropleths, especially).

**Statistic:** areal-scale factor sampled over a graticule (default 12×12 grid) spanning the AOI's bounding box, via `pyproj.Proj(...).get_factors().areal_scale`. Reports the maximum measured exaggeration across all sampled points.

**Threshold:** max areal exaggeration ≤ **20%** (the figure specified in the project abstract for area-comparison maps). 12×12 graticule resolution balances sampling fidelity against per-node `pyproj` cost; adequate where distortion varies smoothly across the AOI (tract/county/state scale), not swept independently.

**Decision:** `REJECT` above the 20% ceiling. Verified against real projections, not synthetic distortion values: Web Mercator over CONUS measures 136% max exaggeration (correctly `REJECT`s); Albers Equal-Area over CONUS measures 0% (correctly `PASS`es, as an equal-area projection must).

**Prescription on REJECT:** reproject to the equal-area CRS for the AOI's scale, from the same `EQUAL_AREA_CRS_BY_SCALE`/`STATE_EQUAL_AREA_CRS` lookup Gate 1 uses.

---

## Gate 5 — Color-vision accessibility

**File:** [`execution/gates/gate5_color_accessibility.py`](../src/autocarto/execution/gates/gate5_color_accessibility.py) · **Tests:** 5

**What it checks:** whether a proposed color palette remains distinguishable under the three common forms of color-vision deficiency (protanopia, deuteranopia, tritanopia), and whether legend/label text meets standard contrast requirements.

**Statistics:** CVD simulation via `colorspacious`, then perceptual color-difference (CIEDE2000, "delta-E") between adjacent classes under each simulated deficiency; WCAG 2.1 contrast ratio for text against its background.

**Thresholds:** minimum delta-E of **10.0** between perceptually-adjacent classes under every CVD simulation (a just-noticeable-difference is ~1–2 dE; 10 is a conservative "clearly distinguishable" floor meant to survive print/screen degradation, not merely clear a lab threshold). WCAG 2.1 Level AA contrast: **4.5:1**.

**Decision:** `REJECT` if any adjacent-class pair collapses below the delta-E floor under any simulated deficiency, or if text contrast falls short. Verified against real palettes: the classic RdYlGn diverging ramp collapses to delta-E = 0.48 under deuteranomaly simulation (correctly `REJECT`ed — this is the canonical "looks fine to most people, invisible to ~8% of men" cartographic color mistake); ColorBrewer YlOrRd measures delta-E = 11.84 (correctly `PASS`es).

**Prescription on REJECT:** substitute a palette from the accessibility-verified set (diverging → a CVD-safe diverging ramp; sequential → a CVD-safe sequential ramp), diverging vs. sequential chosen to match the map type (Gate 5 is told whether the palette needs to be diverging for a bivariate map).

---

## Gate 6 — Map completeness

**File:** [`execution/gates/gate6_completeness.py`](../src/autocarto/execution/gates/gate6_completeness.py) · **Tests:** 6

**What it checks:** whether the *rendered* map carries every element a competent cartographer would consider mandatory — title, legend, scale indicator, data citation, CRS note, and (for bivariate maps specifically) the correlation statistic that justified the bivariate encoding in the first place.

**Threshold:** not numeric — a declarative required-element manifest per map type, following standard cartographic-completeness checklists (Slocum et al., *Thematic Cartography and Geovisualization*). Choropleth: title, legend, scale/graticule, citation, CRS note, classification note. Bivariate: the same plus a bivariate legend and the correlation statistic. Proportional symbol: title, legend, scale/graticule, citation, CRS note.

**Decision:** unlike Gates 1–5, this runs *after* codegen, against the `RenderManifest` the audited template actually produced — and unlike the others, a `REJECT` here indicates a defect in the *template itself* (since templates are audited and LLM-unmodifiable), not in the proposal. There is no LLM-side fix; a Gate 6 rejection is recorded in the trace as an assertion, not fed back into the mandate loop. All three current templates (`choropleth_v1`, `bivariate_v1`, `proportional_symbol_v1`) are verified in tests to satisfy their full required-element set by actually running generated output through this gate, not just inspecting the template source.

---

## Why prescriptions, not just rejections

Every `REJECT` above (except Gates 3b and 3a's two negative-control regimes, where no fix exists because none should) carries a `Prescription`: a method name, a human-readable instruction, and — where applicable — the exact numeric parameters (breaks, target CRS, palette) the next iteration must use verbatim. The LLM's role on a mandate iteration is deliberately reduced to *transcription*, not re-proposal: [`semantic/llm_client.py`](../src/autocarto/semantic/llm_client.py)'s `MockLLM` and [`semantic/nvidia_llm.py`](../src/autocarto/semantic/nvidia_llm.py)'s `NvidiaLLM` both skip any further reasoning (and, for `NvidiaLLM`, any further API call) once a `Prescription` exists — this is what makes the convergence loop's iteration bound (`max_iter`, default 3, then human review) a provable property rather than a hopeful one.
