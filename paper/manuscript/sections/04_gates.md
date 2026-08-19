# 4. The validation gate suite

Six gates run against every proposal. **Table 1** summarises each gate's statistic, threshold, threshold provenance, and the prescription it issues on rejection. Two gates carry the methodological weight of the contribution and are treated first.

**Table 1. The validation gate suite.**

| Gate | Statistic | Threshold | Provenance | Prescription on rejection |
|---|---|---|---|---|
| G1 CRS integrity | CRS presence, equal-area property for area-normalised roles | must be projected/equal-area for density and rate variables | cartographic requirement | reproject to a named equal-area CRS for the area of interest |
| G2 Classification | zero fraction, skewness, unique-value count, outlier share, GVF | 40% zeros · \|skew\| 1.5 · ≤10 unique · >10% outliers · GVF ≥ 0.6 | convention + pilot; rate curves in §6.5 | mandated method **and precomputed break values** |
| G3a Spatial structure | global Moran's I, queen contiguity, permutation inference | \|I\| > 0.1 | ROC AUC 0.9149 (§6.5) | proportional-symbol or dot encoding instead of choropleth |
| G3b Bivariate justification | bivariate Moran's I_xy + Spearman ρ, 199 permutations | \|I_xy\| > 0.15 **and** \|ρ\| > 0.20 | ROC AUC 0.9569 / 0.9978 (§6.5) | side-by-side univariate maps |
| G4 Projection distortion | Tissot areal distortion over the AOI | max areal exaggeration ≤ 20% | policy; rate curve in §6.5 | ranked alternative CRS candidates |
| G5 Colour accessibility | CVD simulation (deutan/protan/tritan), adjacent-class ΔE; WCAG contrast | ΔE ≥ 10.0; contrast ≥ 4.5:1 | colour-science convention | verified colour-vision-safe palette at the requested class count |
| G6 Completeness | render-manifest element checklist | required elements per map type | cartographic convention | add the missing elements |

## 4.1 Why a uniform rejection contract matters

All six gates return the same result type, and a structural invariant forbids a rejection without an attached prescription. This is not an implementation convenience; it is what makes the convergence argument hold. A suite in which some gates could refuse without remedy would reintroduce the unbounded loop for exactly those gates.

## 4.2 Gate 2 — classification as diagnosis, not filtering

Gate 2 is the gate around which the architecture was designed, and it is deliberately not a pass/fail test.

It first *profiles* the variable: the fraction of exact zeros, distributional skew, the count of distinct values, outlier share, and the goodness-of-variance fit attained by the proposed breaks. From that profile it identifies a regime — well-behaved, zero-inflated, heavy right skew, negative-support skew, outlier-dominated, or discrete-ordinal — and each regime carries a specific remedy. **Figure 3** shows the diagnostic across five regimes, with the proposed and prescribed break positions overlaid on each distribution.

On rejection the gate returns the mandated method **and the computed break values themselves**, together with an instruction that explicitly forbids proposing alternatives. Figure 7 reproduces one such rejection verbatim from the emitted trace. This is the difference between validation that critiques and validation that prescribes: the model is not asked to try again, it is told what to write.

Two regimes illustrate why the diagnosis must precede the remedy. A zero-inflated variable (in our demonstration corpus, 49.8% exact zeros) cannot be fixed by any smooth transform; the prescription is an explicit break at zero followed by natural breaks on the non-zero tail. A variable with negative support cannot be log-transformed at all — a naive log would silently clamp or drop observations — so the prescription is the inverse hyperbolic sine with back-transformed breaks [CITE-VERIFY: Burbidge, Magee & Robb 1988]. A single "apply a log transform" rule would corrupt the second case while appearing to work.

## 4.3 Gate 3a — is a choropleth warranted at all?

A choropleth's message is its spatial pattern. If a variable exhibits no spatial autocorrelation, the pattern a reader perceives is noise, and shading regions by value invites an inference the data does not support. Gate 3a computes global Moran's I under queen contiguity with permutation inference and, below threshold, prescribes a proportional-symbol or dot encoding — representations that display magnitude without implying spatial contiguity.

The gate rejects an *encoding*, never the analysis. A spatially random phenomenon remains worth mapping; it is the choropleth specifically that misrepresents it.

## 4.4 Gate 3b — is a bivariate encoding warranted?

Bivariate choropleths are cognitively demanding and visually persuasive, a combination that makes an unjustified one particularly damaging. Gate 3b requires that two conditions hold jointly before the encoding is permitted: a bivariate Moran's I_xy above 0.15 in magnitude, evaluated against a 199-permutation null with pseudo *p*-values computed as (M+1)/(R+1), **and** an aspatial Spearman ρ above 0.20 in magnitude.

Requiring both an effect size and an aspatial correlation, rather than significance alone, is a deliberate defence against the known liberality of the free-permutation null (Section 6.6): the decision never rests on the *p*-value by itself. On rejection the gate mandates side-by-side univariate maps — the analysis proceeds, but the misleading joint encoding does not. **Figure 4** shows the three regimes the gate distinguishes — strong coupling, weak coupling, and independence — and the verdict each receives.

## 4.5 Gates 1, 4, 5, and 6

**Gate 1** verifies that a coordinate reference system exists and, for variables whose semantic role is area-normalised (densities and rates), that it is equal-area. The check is deliberately role-conditional: a count variable is not area-normalised and does not require an equal-area CRS for its own sake, so applying the constraint universally would produce false rejections.

**Gate 4** computes Tissot areal distortion across the area of interest and rejects projections exceeding 20% maximum areal exaggeration for area-comparison maps, returning ranked alternatives measured over the same extent.

**Gate 5** simulates the three principal colour-vision deficiency types at the dichromatic limit and requires a minimum perceptual distance between adjacent classes, alongside a WCAG contrast check for text. On rejection it prescribes a verified safe palette at the requested class count. The scope of this gate is worth stating precisely, because it is narrower than "the colours are good": it measures *discriminability under simulated colour-vision deficiency*, not connotative appropriateness or perceptual ordering. A rainbow ramp can pass the adjacent-class discriminability test at moderate class counts while still failing as a sequential encoding for the separate reason that its lightness is non-monotonic. We report this rather than implying the gate catches more than it does.

**Gate 6** checks the render manifest emitted by the template against the required-element list for the map type — title, legend, scale indication, coordinate-system note, data citation, and classification note. It is a declarative checklist over what the template guarantees, not pixel inspection, which places the burden of manifest honesty on the audited templates rather than on inference from the image.
