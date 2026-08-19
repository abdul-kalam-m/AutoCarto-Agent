# 1. Introduction

A large language model can be asked, in plain English, to map median household income across a metropolitan area, and it will return executable code within seconds. The code imports the right libraries, joins the right tables, calls the right plotting functions, and produces a map that looks professionally made. Whether that map is *true* is a separate question, and one that nothing in the pipeline has asked.

The failure is not exotic. Give a language model a heavy-tailed variable — income, tree-canopy loss, disease counts — and ask for a five-class choropleth, and the default equal-interval classification will place almost every observation in the lowest class. In the case examined in this paper, 414 of 530 census tracts (78%) collapse into a single colour. The resulting map is not merely unattractive; it is a claim about the world, and the claim is false: it asserts spatial uniformity where a strong gradient exists. The code raised no exception. A reviewer looking only at execution success would record a completed task.

Analogous failures recur across the cartographic pipeline. Projections are selected without reference to areal distortion at the area of interest, so polygons are compared by eye at unequal scale. Diverging red–green ramps are applied to ordered quantities, unreadable to a substantial fraction of viewers and non-monotonic in perceived lightness regardless of vision. Bivariate encodings — visually compelling, cognitively expensive — are applied to variable pairs with no spatial cross-correlation whatsoever, producing an image of noise that reads as a pattern. Each of these is a well-documented cartographic error with a well-established remedy. What is new is that they can now be produced automatically, at volume, by systems whose fluency invites trust.

## 1.1 Capability, not correctness, is what the field measures

The autonomous-GIS literature has advanced rapidly. Work in this line has established that language models can decompose spatial tasks, select data sources, generate runnable workflows, and even transfer cartographic style [CITE: Li & Ning 2023; Li, Ning et al. 2025; Akinboyewa et al. 2025; Ning et al. 2025; Wang et al. 2025]. A parallel benchmark literature has emerged to measure this progress [CITE: GeoAnalystBench; GeoBenchX].

Across both, the evaluation axis is overwhelmingly **capability**: did the agent complete the task, did the code execute, did a plausible artifact appear. Correctness of the artifact is either inferred from execution success or delegated to model judgment — a second stochastic pass, whether by self-critique or by multimodal aesthetic evaluation. This is not an oversight so much as an inherited assumption from software agents generally, where a program that runs and returns the expected type has largely succeeded. Cartography does not share that property. A map can execute flawlessly and lie.

Independent evidence for the gap comes from within the field: single-pass language models have been observed to produce "syntactically valid but semantically incorrect" geospatial code, including wrong coordinate transforms and inverted band indices [CITE: GISclaw]. Those errors are invisible to execution-success criteria by construction.

Three specific gaps follow.

**G-1. Execution success does not imply cartographic validity.** No widely used agent computes whether a proposed classification is defensible for the distribution it is applied to.

**G-2. Model-judged correctness inherits model failure modes.** Reflection loops and model-as-judge evaluation add stochastic passes. They can improve average behaviour; they cannot *guarantee* a property, and the critic is subject to the same failure modes as the generator.

**G-3. Rejection without remedy does not converge.** A validator that only refuses leaves an unbounded revision loop. Nothing in the current literature makes a veto convergent.

## 1.2 The inversion

The instinctive response to G-1 and G-2 is to make the model a better cartographer — better prompts, domain fine-tuning, a stronger critic. We take the opposite approach: **remove the model's statistical authority entirely.**

In AutoCarto-Agent, the language model reasons about concepts — what kind of map answers this request, which variables, which template, which visual encoding channel. It never receives raw data values. Every numeric decision that determines whether the map is valid — classification breaks, projection, colour assignment, whether a bivariate encoding is warranted at all — is computed by deterministic algorithms that hold veto authority over the model's proposal.

The mechanism that makes this practical, rather than merely restrictive, is the form of the veto. A gate that rejects returns a **prescription**: the mandated method, the precomputed break values, the exact constants, ready to be spliced into the next attempt. The model's remaining task is transcription, not invention. This converts what would otherwise be an open-ended negotiation into a bounded loop — at most three iterations before the system escalates to a human rather than continuing to argue with itself.

The statistics doing the vetoing are deliberately classical: Jenks natural breaks and goodness-of-variance fit, Moran's I and its bivariate extension under permutation inference, Tissot areal distortion, colour-vision simulation. None is novel, and that is the point — their standing is what makes them trustworthy as arbiters. The contribution is architectural: giving classical, computable validity conditions veto power over a generative model, and making that veto convergent.

## 1.3 Contributions

1. **Diagnostic-to-prescriptive rejection.** Validation gates that return executable mandates — precomputed break values, mandated transforms, exact constants — rather than binary verdicts or natural-language critique, converting an unbounded revision loop into bounded transcription (Sections 4.2, 4.4).

2. **Authority separation as a structural invariant.** Every render constant carries a provenance tag; a plan containing any freely generated numeric constant fails validation before code text exists. "The model never decides a number" is therefore checkable in the execution trace rather than asserted (Section 3.2).

3. **Statistical justification of map *type*.** Gate 3b refuses bivariate encoding when variables lack spatial cross-correlation and mandates the univariate fallback — declining a cognitively misleading map choice rather than styling it well (Section 4.4).

4. **A ground-truth corpus for validation decisions.** Forty-two seeded scenarios across all six gates with known-correct outcomes, scoring decision accuracy rather than rejection rate, and including cases that *should* be refused (Section 6.1).

5. **Reproducibility as an enforced property.** Seeded permutation inference with (M+1)/(R+1) pseudo *p*-values, and gate verdicts that are byte-identical across runs (Section 5).

**What we do not claim.** We do not claim the architecture improves outcomes for map readers; no human-subject study was conducted. We do not claim the thresholds are empirically optimal; they are calibratable policy, and we report operating characteristics where ground truth permits and say so plainly where it does not. We do not claim the language model tier is reliable — the entire design assumes it is not.
