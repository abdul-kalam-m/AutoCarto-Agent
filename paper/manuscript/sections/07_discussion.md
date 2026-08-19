# 7. Discussion

## 7.1 When to constrain rather than extend

The prevailing response to unreliable model output is to improve the model: better prompts, domain fine-tuning, a stronger critic. Those interventions shift a distribution of behaviour. They cannot establish a property.

The distinction matters whenever the cost of a silent failure is high and the validity condition is *computable*. Thematic cartography satisfies both: an invalid map is persuasive precisely because it looks finished, and the conditions that make it invalid have been formalised for decades. Under those circumstances, constraining the generator is strictly stronger than improving it — and the two are not rivals. A better model converges in fewer iterations; the gates determine what is shippable regardless of which model is behind them. Swapping the checkpoint does not disturb the guarantees, which is a practical property in a field where models are replaced every few months.

The converse is equally worth stating: where validity is genuinely a matter of judgment — aesthetic quality, narrative emphasis, audience fit — this architecture has nothing to offer, and model judgment or human review is the appropriate mechanism. The gates encode communication validity, not taste.

## 7.2 Why prescription, not just rejection

The convergence property does not come from the veto; it comes from the form of the veto. A validator that returns "rejected: classification unsuitable" leaves the model to guess again, and there is no reason for the second guess to be better than the first. A validator that returns the mandated method together with the computed break values leaves nothing to guess.

This reframes the agent's role. Once a prescription exists, the model is not a cartographer being corrected; it is an assembler transcribing constants into an audited template. That is a smaller role than the autonomous-agent literature typically assigns, and deliberately so — it is the role for which a stochastic component is actually well suited.

## 7.3 Refusing the map, not the analysis

Gates 3a and 3b refuse *encodings*, never questions. A spatially random phenomenon still merits mapping; what it does not merit is a choropleth, whose visual grammar asserts spatial contiguity. Two unrelated variables still merit analysis; what they do not merit is a bivariate encoding, which asserts joint structure.

In both cases the gate mandates an alternative representation, so the user's question is still answered. This distinguishes the system from a filter: it is opinionated about representation, not obstructive about inquiry. The three-iteration cap and subsequent escalation to a human are the corresponding admission that the system's opinion is not final.

## 7.4 Transferability

The pattern generalises to any setting combining a fluent generator, codified validity conditions, and no current enforcement: interpolation with assumptions that can be tested, hotspot detection with multiple-comparison corrections that can be applied, cluster labelling with stability that can be measured. In each case the same three components transfer — a typed proposal contract, deterministic gates with veto authority, and prescriptive rejection carrying computed constants.

We demonstrate the pattern in one domain and argue rather than demonstrate its transfer. Thematic cartography was chosen as the cleanest demonstrator precisely because its validity rules are already formalised; domains where they are not would first require that formalisation, which is substantial work in itself.

## 7.5 What deterministic validation cannot do

Three limits are structural rather than incidental.

The gates verify *properties of the artifact*, not *fitness for the user's purpose*. A map can pass all six gates and answer the wrong question.

The gates encode thresholds, and thresholds are policy. We report operating characteristics where ground truth allows (§6.5) and decline to manufacture them where it does not. An organisation adopting this architecture inherits our defaults and should calibrate them.

Finally, the architecture constrains what the model may decide, not what the data means. Gate 3b established that income and asthma prevalence are spatially cross-correlated in Atlanta; it has nothing to say about why, and the system's approval of that map is not an epidemiological claim.
