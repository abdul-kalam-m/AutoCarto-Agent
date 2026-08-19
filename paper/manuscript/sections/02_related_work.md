# 2. Related work

## 2.1 Autonomous GIS agents

The framing of "autonomous GIS" — language models that decompose a spatial request into an executable workflow — originates with work that established both the vision and the solution-graph mechanism for realising it [CITE: Li & Ning 2023]. A subsequent research agenda formalised the space in terms of autonomy levels, functions, and scales, and identified trust and reliability as open problems [CITE: Li, Ning et al. 2025]. Systems in this line have targeted spatial analysis through tool documentation and execution feedback [CITE: Akinboyewa et al. 2025], and autonomous geospatial data retrieval through model-driven source selection [CITE: Ning et al. 2025].

These systems share a correctness mechanism: the workflow is correct if it runs, and errors are addressed by retrying against the traceback. That is an appropriate criterion when failure is loud. It is insufficient when failure is silent — when the code executes and the artifact is invalid. Our contribution is orthogonal rather than competing: we adopt the autonomous-GIS vision and invert its trust model, narrowing the domain in exchange for enforceable validity of the artifact.

## 2.2 Language models in cartography

The closest neighbouring work applies multimodal language models to cartographic style transfer and aesthetic evaluation, with a multi-agent design and a human study, and — importantly — a design principle we share: the agent designs the stylesheet and does not modify the underlying data [CITE: Wang et al. 2025]. Related work has explored natural-language interaction for map design more broadly [CITE: MapMate 2025].

The distinction from our work is clean and worth stating precisely, because it is easily misread as competition. That line evaluates **aesthetics**, and its evaluator is a **multimodal model** (supplemented by human judgment). We evaluate **statistical validity**, and our evaluator is a **deterministic algorithm** with veto authority. These are different axes and different mechanisms; a system could sensibly adopt both, using deterministic gates for validity and model judgment for style. We take the shared "do not touch the data" instinct as convergent evidence that the authority question is the right one to ask, and differ on how far to push it: not merely that the model should not modify data, but that it should not decide any number derived from data.

## 2.3 Neuro-symbolic coupling

Our architecture belongs to a broader family in which a neural component proposes and a symbolic component verifies or solves [CITE: Neuro-Symbolic AI systematic review 2024]. The canonical pattern — the model translates a problem into a formal representation and a symbolic engine decides it — has been demonstrated for logical reasoning [CITE-VERIFY: Pan et al., Logic-LM, EMNLP 2023] and for offloading correctness to a deterministic prover [CITE-VERIFY: Olausson et al., LINC, EMNLP 2023]. Tool-use frameworks similarly position the model as an orchestrator of deterministic components [CITE-VERIFY: Schick et al., Toolformer, NeurIPS 2023; Yao et al., ReAct, 2023].

Within the coupling taxonomy [CITE-VERIFY: Garcez & Lamb, Neuro-symbolic AI], our design is best described as **reasoning-constrains-generation**: the symbolic layer does not merely assist the neural layer or consume its output, it holds exclusive authority over every numerical decision and can refuse the neural layer's proposal outright. The distinguishing element relative to the tool-use line is that our symbolic components are not tools the model calls at its discretion — they are gates the model cannot bypass, and their rejections carry binding constants.

## 2.4 Cartographic validity as computable mathematics

Each gate rests on established cartographic and spatial-statistical scholarship rather than on novel methods. Classification draws on natural-breaks optimisation and goodness-of-variance fit [CITE-VERIFY: Jenks 1967], on the long-understood result that the choice of class intervals changes the map's message [CITE-VERIFY: Coulson 1987], and on head/tail breaks for heavy-tailed distributions [CITE-VERIFY: Jiang 2013]. Spatial structure testing rests on Moran's I [CITE-VERIFY: Moran 1950] and the modern permutation-based toolkit [CITE-VERIFY: Anselin 1995], with the spatial autoregressive model supplying our controlled data-generating process [CITE-VERIFY: Anselin 1988]. Visual encoding follows the visual-variables vocabulary [CITE-VERIFY: Bertin 1983], colour selection follows established colour-vision-safe palette work [CITE-VERIFY: Brewer, ColorBrewer], the cognitive cost of bivariate displays motivates Gate 3b [CITE-VERIFY: MacEachren 1995], and projection distortion follows standard Tissot-based treatment [CITE-VERIFY: Snyder 1987].

One reference deserves particular attention because it bounds a claim we make. Bivariate spatial association has a more rigorous formulation than the bivariate Moran's I with free permutation that we deploy [CITE-VERIFY: Lee 2001]. We adopt the simpler statistic, report its null-model weakness quantitatively (Section 6.6), and treat the stricter formulation as the acknowledged path not yet taken rather than as unrelated work.

## 2.5 Evaluating geospatial agents

The benchmark literature for spatial agents measures task success against reference answers [CITE: GeoAnalystBench; GeoBenchX]. To our knowledge, none measures the *validity of the produced artifact*, and none includes cases where the correct behaviour is refusal. Our 42-scenario corpus (Section 6.1) is a step in that direction: it scores whether the validator reached the right decision, and roughly half its scenarios are pathological by construction, with refusal as the correct outcome.

## 2.6 Positioning

**Table 3** summarises the comparison along the axis that matters here: what mechanism, if any, establishes that the produced artifact is correct.

**Table 3. Correctness mechanisms in related systems.**

| System class | Primary objective | Correctness mechanism | Relation to this work |
|---|---|---|---|
| Autonomous GIS workflow agents [CITE: Li & Ning 2023; Li, Ning et al. 2025] | general spatial-analysis workflows | model reasoning + execution success | we narrow the domain to gain enforceable artifact validity |
| Spatial-analysis copilots [CITE: Akinboyewa et al. 2025] | natural-language spatial analysis | tool documentation + retry on execution error | our gates compute statistics and veto; they do not retry on traceback |
| Autonomous data retrieval [CITE: Ning et al. 2025] | geospatial data discovery | source selection + debugging loop | retrieval is one tier of ours, with a spatial-first contract and downstream validation |
| Multimodal cartographic agents [CITE: Wang et al. 2025] | map style transfer, aesthetic quality | multimodal model judgment + human study | different axis (aesthetics vs. statistical validity) and different mechanism (model judgment vs. deterministic veto); complementary |
| Agent benchmarks [CITE: GeoAnalystBench; GeoBenchX] | measuring task completion | reference answers | none scores artifact validity or includes refusal as a correct outcome |
| **This work** | statistically defensible thematic maps | **deterministic gates with veto authority and prescriptive rejection** | — |

The empty region the table identifies is the combination of a narrow, well-codified domain with deterministic, non-negotiable enforcement of artifact validity. Prior autonomous-GIS agents ask whether the model can complete the task. We ask whether the artifact it produces is correct, and answer with computation that holds veto authority over the model.
