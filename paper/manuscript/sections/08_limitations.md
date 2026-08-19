# 8. Limitations and future work

The limitations below are claims about what was not measured, and they are as verified as the positive results.

**No large-scale natural-language prompt benchmark.** The 42-scenario corpus scores *gate decisions* on seeded inputs. It does not measure how the system handles a large, labelled set of natural-language requests routed through a hosted model. Building one would require many paid API calls and was deliberately bounded out. This is the largest single evidence gap in the paper: end-to-end runs with a real open-weights model are demonstrated (§6.4) but not measured at scale.

**Convergence is bounded by construction, not characterised empirically.** The three-iteration cap guarantees termination, and observed end-to-end runs converged in two iterations. We do not report a distribution of iteration counts over a large prompt sample — that requires the benchmark above.

**Test coverage is unmeasured.** Every gate branch has an explicit test and 236 tests pass, but no coverage tool has been run and no percentage is claimed.

**Scale.** Spatial weights are dense matrices, practical to roughly 10⁴ features. The gates' verdicts are unaffected by scale; only the executor would need to change (sparse weights, then a spatial database, then a distributed engine). This is an engineering limit, not a methodological one, but it bounds the settings in which the current implementation is directly usable.

**Null-model liberality.** Quantified in §6.6 rather than merely acknowledged: 18.97× mean *p*-value inflation on the independent regime, one corpus false positive attributable to it. The conditional alternative is implemented and opt-in, with its own cost of one false negative. Adopting the more rigorous bivariate spatial association formulation [CITE-VERIFY: Lee 2001] is the natural next step and would require recalibrating the decision matrix.

**Thresholds for Gates 2 and 4 are uncalibrated.** ROC analysis exists for the two spatial-structure gates; for classification and projection distortion no independent ground truth exists, and only rejection-rate curves are reported.

**Single domain.** Transferability is argued (§7.4), not demonstrated.

**No human-subject evaluation.** Whether validated maps are better understood, better trusted, or preferred by readers and expert cartographers is untested. This is the most consequential open question for the architecture's practical claim, since the entire premise is that certain maps mislead readers — a premise grounded in the cartographic literature but not re-established experimentally here.

**Split execution paths.** The orchestrator's render path executes in-process; the gVisor container is a separately tested standalone boundary (§6.7). Unifying them is straightforward engineering but is not yet done, and the paper does not claim that the end-to-end pipeline currently runs inside the tested container.

## Future work

The priorities follow directly from the gaps. A labelled natural-language prompt corpus, scored against expected gate outcomes and including requests that should be refused, would close the largest gap and would additionally constitute a validity benchmark of independent value — the existing benchmark literature measures task success, and none measures artifact validity. A human-subject study comparing gated and ungated outputs would ground the default thresholds in expert preference rather than convention. Adopting a conditional null throughout, with a recalibrated decision matrix, would strengthen the bivariate inference. Sparse weights and a routed compute backend would lift the scale ceiling.
