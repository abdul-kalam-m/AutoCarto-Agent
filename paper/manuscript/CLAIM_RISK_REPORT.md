# Claim Risk Report

Audit of manuscript wording against the evidence in `CLAIM_SUPPORT_MAP.md`. Risk = the chance a reviewer reads the sentence as claiming more than the evidence bears.

## Risk: none — wording matches evidence exactly

| Claim | Wording check |
|---|---|
| 38/39 (97.4%) decision accuracy | Denominator stated; 3 unscored borderline cases disclosed in the same sentence |
| GVF 0.7514→0.8348, 0.7741→0.8607 | Baseline named ("naive quintile-derived proposal"), not left implicit |
| 414/530 (78%) collapse | Both fraction and percentage given; identified as adversarial single-variable illustration |
| 27 of 27 red-team vectors | Bounded by "tested"; sanitizer-disabled condition stated; universal claim explicitly declined |
| 236 tests passing | Skip count given; no coverage percentage claimed anywhere |
| Real ACS × CDC I_xy = −0.56 | Rounded value in prose, exact −0.5555 in support map; n=519 with the 11 exclusions explained |

## Risk: low — correct but depends on a scope word

| Claim | The load-bearing word | Why it holds |
|---|---|---|
| "gate **verdicts** are byte-identical" | *verdicts* | §5 states plainly that 2 of 4 trace files vary in timing fields. Removing "verdicts" would make this false. **Do not let an editor generalise this to "traces."** |
| "the **container** is the boundary" | *container* | §3.4 and §6.7 both separate sanitizer (cost-raiser) from container (boundary). The 27/27 result belongs to the container alone |
| "**tested** vectors" | *tested* | Guards against the unfalsifiable universal |

## Risk: moderate — flagged, defensible, will draw questions

**Bounded convergence (≤3 iterations).**
The cap is architectural, so termination is guaranteed. But "converges in ≤3 iterations" could be read as an empirical distribution over many prompts, which we do not have. §8 states this explicitly ("bounded by construction, not characterised empirically"). *A reviewer will still ask. The answer is in the text.*

**"Recovers a documented health-equity gradient."**
The statistic is verified; the epidemiological interpretation is not ours to make. §6.4 and §7.5 both restrict this to a statistical claim. Wording holds provided no revision upgrades it to a finding *about asthma*.

**Transferability beyond thematic cartography (§7.4).**
Explicitly labelled as argued rather than demonstrated, in both §7.4 and §8. Acceptable in a discussion section; would be an overclaim in the abstract, where it does not appear.

## Risk: eliminated — claims removed from inherited material

The original conference abstract (`Abstract_revised.txt`) contained two claims that were later retired. Both were filtered out and verified absent:

| Retired claim | Why it fails | Replacement |
|---|---|---|
| "rejected 23 percent of initial LLM proposals" | No corpus ever supported it; unfalsifiable as stated | 42-scenario ground-truth corpus, 38/39 |
| "100 percent of attempted sandbox escapes blocked" | Unfalsifiable universal | "27 of 27 tested vectors," container-only |

**Standing instruction for any future revision:** neither claim may be reintroduced, including as historical framing.

## Highest-risk sentence in the manuscript

> §6.4: "The system was not directed toward it; it was asked to map two variables and determined that their joint encoding was statistically justified."

Accurate — but it invites the reading that the system *discovered* the health pattern. It did not: it validated that a bivariate encoding of two supplied variables was statistically defensible. The following sentence already constrains this ("We claim this as evidence … not as an epidemiological finding"). Retain both sentences together; deleting the second would create an overclaim.
