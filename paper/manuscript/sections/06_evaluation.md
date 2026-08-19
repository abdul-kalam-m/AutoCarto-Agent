# 6. Evaluation

The evaluation answers four questions: whether the gates decide correctly against known ground truth (§6.1), whether the constrained pipeline produces defensible maps in a controlled setting where the truth is known (§6.2–6.3) and on real data where it is not (§6.4), how sensitive the verdicts are to threshold choice (§6.5), and where the inference is weakest (§6.6).

## 6.1 Decision accuracy against ground truth

Evaluating a validator requires knowing the right answer in advance, which real data cannot supply. We therefore constructed a corpus of 42 seeded scenarios spanning all six gates, each labelled with the outcome a correct validator should reach. Roughly half are pathological by construction — the correct behaviour is refusal.

Of the 42, three are borderline by construction; these are reported but not scored, since forcing a verdict on a deliberately ambiguous case would measure the threshold rather than the decision. On the remaining 39:

**Table 2. Decision accuracy on the ground-truth corpus.**

| Measure | Result |
|---|---|
| Strict decision accuracy | **38 / 39 (97.4%)** |
| Benign inputs (correct outcome: accept) | 17 / 17 |
| Pathological inputs (correct outcome: reject) | 21 / 22 |
| Borderline, reported not scored | 3 |
| Rejections by cause | heavy right skew 6 · discrete-ordinal 3 · zero-inflated 3 · G3a white noise 3 · G3b independent 2 · G3b weak coupling 1 · G4 Web-Mercator (CONUS) 1 · G4 Web-Mercator (Georgia) 1 · G5 red–green diverging 1 · G1 geographic density 1 |

The single miss is disclosed rather than aggregated away: a Gate 3b scenario in which two independently generated fields, each individually autocorrelated, produced a spurious cross-correlation strong enough to pass. Section 6.6 identifies the cause and quantifies it.

The corpus-wide rejection rate is 22 of 42 (52.4%). We report this figure only alongside the corpus composition, because it is a property of an adversarial corpus rather than a natural rejection rate, and quoting it without that context would be meaningless. Figure 6 shows the routing structure — every rejection terminating in a specific prescription — for the earlier 24-scenario version of this corpus.

## 6.2 Controlled case: 530 Atlanta tracts

The controlled case uses real geometry and topology (530 census tracts across two Georgia counties, with queen-contiguity weights) carrying two seeded spatially autoregressive variables, generated as *y* = (I − ρW)⁻¹ε and labelled *tree-canopy loss* and *asthma hospitalisation rate*. The synthetic construction is the point: because the data-generating process fixes the true spatial structure, "the gate decided correctly" is a checkable statement. Real data cannot support that check.

> **A note on nomenclature, to prevent a conflation.** The variable labelled "asthma hospitalisation rate" in this controlled case is a *synthetic* field carrying a plausible name; it is not measured health data and must not be read as such. The real asthma measure — CDC PLACES asthma prevalence — appears only in §6.4, alongside real income. The two cases share geometry and nothing else.

Both variables are heavily right-skewed. Gate 2 rejected the naive quintile-derived proposal for each and prescribed a log transform followed by Jenks natural breaks. Goodness-of-variance fit rose from **0.7514 to 0.8348** for canopy loss and from **0.7741 to 0.8607** for the synthetic rate variable.

Gate 3b then evaluated whether a bivariate encoding was justified: bivariate Moran's I_xy = **+0.3262** (pseudo-*p* = 0.0050, 199 permutations) and Spearman ρ = **+0.9471**, both above threshold, yielding APPROVE. Only then was the bivariate map produced (Figure 5).

## 6.3 Ablation: what the gates prevent

Figure 1 isolates the effect of the classification gate on a single variable. Under the unconstrained proposal — equal-interval breaks — **414 of 530 tracts (78%) fall into one class**. Under the gated pipeline, the prescribed log-plus-Jenks classification produces balanced classes of **98, 134, 145, 90, and 63** tracts.

One result here runs against the system's own interest, and we report it in the main text rather than a footnote. The rejected equal-interval classification attains a **higher** goodness-of-variance fit than the prescribed one (0.866 versus 0.835). A validator that maximised GVF would have preferred the map that hides the pattern.

This is evidence for what Gate 2 is: a distribution *diagnostic* that selects a method appropriate to the distribution's shape, not an optimiser of a single fit statistic. It also answers the natural objection that the gate is a thresholded GVF filter — if it were, it would have accepted the worse map. The honest failure metric in this comparison is class balance, and we use it.

## 6.4 Real-data case: does it work on data nobody engineered?

The controlled case establishes that the gates decide correctly. It cannot establish that the system is useful on data with unknown structure. For that, the same gates — unmodified — were run against real Census American Community Survey median household income and real CDC PLACES asthma prevalence for the same tracts. Eleven of the 530 tracts lacked an estimate for one or both variables and were **dropped rather than imputed**, leaving 519; imputation would have manufactured structure the gates would then have validated against data that was never measured.

Gate 3a confirmed real univariate spatial clustering in income (Moran's I = **0.59**, *p* = 0.001). Gate 3b returned bivariate Moran's I_xy = **−0.5555** (*p* = 0.005) and Spearman ρ = **−0.7758**, and approved the bivariate encoding.

The recovered pattern — higher income co-locating with lower asthma prevalence — is a documented health-equity gradient. The system was not directed toward it; it was asked to map two variables and determined that their joint encoding was statistically justified. We claim this as evidence that the constrained pipeline produces defensible maps on unengineered data, not as an epidemiological finding.

## 6.5 Threshold sensitivity

Every threshold in Table 1 is policy rather than physics, and the honest question is how much the verdicts move when the policy moves. Where ground truth exists, we report operating characteristics (Figure 8).

For Gate 3a, against seeded ground truth defined by the generating autocorrelation parameter, the ROC area under the curve is **0.9149** (n = 240). For Gate 3b, against ground truth defined by the coupling weight, the AUC is **0.9569** for bivariate Moran's I_xy and **0.9978** for Spearman ρ (n = 165). Both gates are therefore well separated from chance across a wide range of threshold choices, and the deployed thresholds do not sit at a cliff.

For Gates 2 and 4 we report rejection-rate curves rather than ROC curves, because no independent ground truth for "an acceptable classification" or "an acceptable level of areal distortion" exists beyond the metric being thresholded. Constructing one would require the human-preference study we have not conducted. This is a limit on what can currently be calibrated, and we state it rather than substituting a curve that would imply more than it measures.

## 6.6 Where the inference is weakest

Gate 3b's default null model permutes one variable freely. For two variables that are each spatially autocorrelated, this null is liberal: it destroys the spatial structure of the permuted variable, so the reference distribution is narrower than it should be and significance is overstated.

We quantified this with a 999-permutation comparison against a conditional alternative — a toroidal shift, which preserves the permuted variable's own spatial autocorrelation exactly and randomises only its alignment with the other variable.

**Table 4. Null-model comparison (9 scenarios, 999 permutations).**

| Null model | False positives (α = 0.05) | False negatives |
|---|---|---|
| Free permutation (default) | 2 | 0 |
| Conditional toroidal shift | 1 | 1 |

Mean *p*-value inflation on the independent regime under the free-permutation null was **18.97×**. The conditional null removed one false positive — including the corpus miss reported in §6.1 — and introduced one false negative, as a genuinely related pair fell below significance under the stricter reference distribution.

Two design consequences follow, and we state both. First, this is why Gate 3b's decision rule requires effect size *and* aspatial correlation rather than significance alone: the decision matrix does not read the *p*-value, so the liberality of the null does not by itself admit a bad map. Second, we have **not** wired the conditional null into the default decision path. Doing so would trade a false positive for a false negative and would require its own calibration; making that trade silently would be worse than disclosing it. The stricter formulation in the bivariate spatial association literature [CITE-VERIFY: Lee 2001] remains the acknowledged path not yet taken.

## 6.7 Execution boundary

The container boundary was evaluated by red team rather than by inspection. Twenty-seven attack vectors — network exfiltration, filesystem writes, privilege escalation, resource exhaustion, reflection-based escapes, and raw syscalls — were executed against the sandbox **with the static sanitizer deliberately disabled**, so that the container alone was under test. All 27 were blocked, verified in continuous integration against a real gVisor runtime rather than on a developer machine.

We claim 27 of 27 tested vectors. We do not claim the boundary is unbreakable: an unknown vector or a runtime vulnerability remains possible in principle, and a universal claim would be unfalsifiable.
