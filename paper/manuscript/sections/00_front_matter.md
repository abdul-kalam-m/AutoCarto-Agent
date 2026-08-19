# AutoCarto-Agent: Deterministic Spatial Validation for Autonomous Thematic Cartography

**DRAFT MANUSCRIPT — not submitted; no target venue selected.**

Abdul Kalam Mustaq
Edward J. Bloustein School of Planning and Public Policy, Rutgers University–New Brunswick
ar.abdulkalam.mustaq@gmail.com

*Draft of 2026-08-11. Formatting is venue-neutral. Reference entries marked `[CITE-VERIFY]` require edition and page confirmation before submission.*

---

## Abstract

Large language models generate fluent geospatial code, but fluency is not cartographic validity: model-authored thematic maps routinely misclassify skewed distributions, select area-distorting projections, and apply bivariate encodings to variable pairs with no spatial cross-correlation. The autonomous-GIS literature has advanced rapidly on *capability* — task decomposition, executable workflow generation, style transfer — while correctness of the produced artifact is either inferred from execution success or delegated to model judgment, itself a stochastic process.

We present AutoCarto-Agent, a neuro-symbolic architecture that inverts the trust relationship. A frozen language model reasons only about cartographic concepts — map type, visual encoding, template — and never receives raw data values. A deterministic engine computes every numeric decision, evaluates six validation gates covering coordinate-system integrity, distribution-aware classification, univariate and bivariate spatial structure, projection distortion, colour-vision accessibility, and completeness, and holds veto authority over the model's proposal. The mechanism that makes the veto convergent rather than merely obstructive is prescriptive rejection: a gate that rejects returns the mandated method together with precomputed constants, reducing the model's remaining role to transcription within an audited template. A typed provenance contract refuses any render plan containing a freely generated numeric constant, making authority separation auditable from the execution trace rather than asserted.

Across a 42-scenario corpus with known-correct outcomes spanning all six gates, the engine reaches the correct decision in 38 of 39 scored cases (97.4%), with the single miss disclosed and traced to a quantified null-model limitation. In a controlled case on 530 census tracts with real geometry and seeded spatially autoregressive variables, the classification gate raises goodness-of-variance fit from 0.7514 to 0.8348 and from 0.7741 to 0.8607 over the naive proposal; an ablation shows the unconstrained classification collapsing 414 of 530 tracts (78%) into a single class where the gated pipeline yields balanced classes. Notably, the rejected classification attains a *higher* goodness-of-variance fit than the prescribed one, evidence that the gate is a distribution diagnostic rather than a fit optimiser. Run unmodified against real American Community Survey income and CDC PLACES asthma prevalence for 519 tracts, the same gates recover a documented health-equity gradient (bivariate Moran's I_xy = −0.56, *p* = 0.005; Spearman ρ = −0.78).

We report what is not established: no large-scale natural-language prompt benchmark, no human-subject evaluation, uncalibrated thresholds for two of six gates, and a bivariate null model whose liberality we quantify at 18.97× mean *p*-value inflation on independent fields. The contribution is a transferable pattern for constrained spatial agents: deterministic validation with veto authority, and rejection that prescribes.

**Keywords:** autonomous GIS · neuro-symbolic architecture · thematic cartography · spatial validation · large language models · reproducibility
