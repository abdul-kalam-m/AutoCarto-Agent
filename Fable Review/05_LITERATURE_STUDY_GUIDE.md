# AutoCarto-Agent — Literature Study Guide

**A structured reading program for the AutoCarto-Agent research.** Purpose: give you (and any co-author or continuation engineer) the intellectual scaffolding to (1) write a defensible related-work section, (2) answer expert questions at STDS and in review, and (3) know which classical result each gate rests on so you can defend every threshold.

**Version:** 1.0 · **Date:** 2026-07-06 · Companion to [04_V2_PUBLICATION_GUIDE.md](04_V2_PUBLICATION_GUIDE.md).

**How citations are marked:**
- 🔎 **verified** — confirmed via web search during this review (2026-07-06); URL given.
- 📖 **foundational** — established canonical work I am citing from standard knowledge; author/title/venue are reliable, but **confirm the exact edition/year/page before citing in a manuscript** (do not trust any AI, including me, for a bibliography without checking).

Each track states *why it matters to this project* and *which component it grounds*, so you read with purpose rather than breadth for its own sake.

---

## Track 0 — Reading strategy (start here)

You do not need to read everything. Read in this order of return-on-effort:

1. **Track 1** (autonomous-GIS landscape) — this is your competition and your related-work section. Read first, read closely. *~1 week.*
2. **Track 3** (classification & spatial stats) — grounds Gates 2/3a/3b, the parts that are *built and novel*. You must be able to defend every statistic. *~1 week.*
3. **Track 2** (neuro-symbolic) — grounds your architectural framing. *~3 days.*
4. **Track 4** (cartographic theory) — grounds Gates 1/4/5/6 and the "publication-quality" claim. *~3 days.*
5. Tracks 5–7 (retrieval, sandboxing, benchmarks) as needed when you build those components.

Maintain a one-line-per-paper synthesis matrix (paper → claim → how it relates to AutoCarto → gap it leaves) — that matrix *is* your related-work section and your novelty defense.

---

## Track 1 — Autonomous GIS & LLM geospatial agents (your direct competition)

**Why:** this is the field you are publishing into. Every paper here is a potential reviewer and a related-work citation. Your entire novelty argument is "these optimize capability; I enforce correctness" (Publication Guide §3). Know them cold.

| Work | Read for | Connection to AutoCarto |
|---|---|---|
| 🔎 Li & Ning, *Autonomous GIS: the next-generation AI-powered GIS*, Int. J. Digital Earth 16(2), 2023 — [LLM-Geo repo](https://github.com/gladcolor/LLM-Geo) | the origin of the "autonomous GIS" framing; solution-graph workflow generation | you inherit the vision, invert the trust model |
| 🔎 Li, Ning et al., *GIScience in the Era of AI: A Research Agenda Towards Autonomous GIS*, Annals of GIS 2025 — [arXiv:2503.23633](https://arxiv.org/abs/2503.23633) | the 5 goals / 5 levels / 5 functions / 3 scales framework; **cite your system's autonomy level explicitly** | position AutoCarto on their taxonomy; their "trust/reliability" gap is your contribution |
| 🔎 Akinboyewa et al., *GIS Copilot: Towards an Autonomous GIS Agent for Spatial Analysis*, 2025 — [arXiv:2411.03205](https://arxiv.org/abs/2411.03205), [repo](https://github.com/Teakinboyewa/SpatialAnalysisAgent) | tool-documentation approach; execution-feedback loop; their eval protocol (100+ tasks) | contrast: retry-on-error vs. deterministic veto+prescription |
| 🔎 Ning et al., *LLM-Find: An Autonomous GIS Agent Framework for Geospatial Data Retrieval*, Int. J. Digital Earth 18(1), 2025 — [Tandfonline](https://www.tandfonline.com/doi/full/10.1080/17538947.2025.2458688) | LLM-as-decision-maker for data source selection | your Tier 3 does retrieval too, but spatial-first + validated |
| 🔎 Wang et al., *CartoAgent: multimodal LLM multi-agent cartographic framework*, IJGIS 39(9), 2025 — [arXiv:2505.09936](https://arxiv.org/abs/2505.09936), [repo](https://github.com/GISense/CartoAgent) | **your closest neighbor**; "design stylesheets, never modify the data"; MLLM aesthetic eval + human study | the critical distinction: aesthetics-by-MLLM-judgment vs. validity-by-deterministic-algorithm. State it explicitly. |
| 🔎 *MapMate: bridging NL interaction and map design through LLMs*, 2025 — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1569843225007204) | NL→map-design UX | you refuse+prescribe; they design |

**Deliverable from this track:** the 2×2 positioning figure (Publication Guide §3) and three sentences that distinguish you from Li/Ning, GIS Copilot, and CartoAgent respectively.

---

## Track 2 — Neuro-symbolic AI & constrained LLMs (your architectural framing)

**Why:** your paper calls itself "neuro-symbolic." A reviewer from the NSAI community will hold you to the term. Know the taxonomy so you can place yourself in it precisely (Publication Guide §3 warns against loose usage).

| Work | Read for | Connection |
|---|---|---|
| 📖 Garcez & Lamb, *Neuro-symbolic AI: The 3rd Wave*, 2023 (also *Neural Computing and Applications* survey) — 🔎 survey landscape [arXiv:2501.05435](https://arxiv.org/pdf/2501.05435) | the coupling-degree taxonomy; "learning for reasoning" vs "reasoning for learning" vs "co-design" | you are a *reasoning-constrains-generation* design; name it with their vocabulary |
| 🔎 *Neuro-Symbolic AI in 2024: A Systematic Review* — [arXiv:2501.05435](https://arxiv.org/pdf/2501.05435) | current landscape, where LLM+symbolic sits | situates your asymmetric-authority design |
| 📖 Pan et al., *Logic-LM: Empowering LLMs with Symbolic Solvers*, EMNLP 2023 | LLM proposes, symbolic solver verifies/executes | the canonical "LLM translates, symbolic decides" pattern — your ancestor; cite it |
| 📖 Olausson et al., *LINC: Neurosymbolic Logical Reasoning via LMs + FOL provers*, EMNLP 2023 | offloading correctness to a deterministic checker | same instinct in a different domain |
| 📖 Schick et al., *Toolformer*, NeurIPS 2023; and the *ReAct* (Yao et al., 2023) tool-use line | LLM-as-orchestrator-of-deterministic-tools | your gates are the "tools," but with *veto* not just *call* |

**The framing sentence:** *"AutoCarto-Agent is a reasoning-constrains-generation neuro-symbolic system: the symbolic layer does not merely assist the neural layer, it holds exclusive authority over every numerical decision."* This is more precise than "neuro-symbolic" alone and pre-empts the "which kind?" question.

---

## Track 3 — Classification & spatial statistics (grounds your *built, novel* gates)

**Why:** Gates 2, 3a, 3b are the implemented contribution. Every threshold and method must be defensible from primary sources. This is where a spatial-statistician reviewer will probe hardest (Presentation Guide Q7, Q8, Q12).

**Classification (Gate 2):**
- 📖 Jenks, G.F., *The Data Model Concept in Statistical Mapping*, Int. Yearbook of Cartography, 1967 — the natural-breaks / GVF origin.
- 📖 Coulson, M.R.C., *In the Matter of Class Intervals*, Cartographica, 1987 — why classification method changes the map's message (the *reason* Gate 2 exists).
- 📖 Slocum et al., *Thematic Cartography and Geovisualization* (4th ed.) — modern textbook treatment of classification schemes, GVF, head-tail. **Your single best desk reference for Gate 2.**
- 📖 Jiang, B., *Head/Tail Breaks*, The Professional Geographer, 2013 — grounds your `head_tail_breaks` prescription for heavy-tailed data.
- On the **arcsinh** prescription for negative-support skew: 📖 the inverse-hyperbolic-sine transform literature in econometrics (Burbidge, Magee & Robb, JASA 1988) — cite it to justify arcsinh over log1p.

**Spatial autocorrelation (Gates 3a, 3b):**
- 📖 Moran, P.A.P., *Notes on Continuous Stochastic Phenomena*, Biometrika, 1950 — Moran's I origin.
- 📖 Anselin, L., *Local Indicators of Spatial Association—LISA*, Geographical Analysis, 1995 — the modern spatial-autocorrelation toolkit; grounds your permutation inference.
- 📖 Anselin, *Spatial Econometrics*, 1988 — row-standardization, the SAR model (your synthetic data generator `y=(I−ρW)⁻¹ε`), weights matrices. **Read the SAR section — you must be able to explain your own data-generating process.**
- 📖 **Lee, S.-I., *Developing a bivariate spatial association measure (Lee's L)*, J. Geographical Systems, 2001** — the rigorous alternative to your bivariate-Moran's-I + free-permutation approach. **This is the paper behind Presentation Guide Q12 and research task R-2.** Read it before the journal submission; it is your strongest reviewer's likely reference.
- 📖 Tobler, W., *A Computer Movie Simulating Urban Growth in the Detroit Region*, Economic Geography, 1970 — the First Law; the one-sentence justification for why spatial structure matters at all.

**MAUP (grounds the H3/simplification design decisions):**
- 📖 Openshaw, S., *The Modifiable Areal Unit Problem*, CATMOG 38, 1984 — why administrative-unit choice changes results; your rationale for restricting H3 to point/raster data.

**Deliverable:** a one-paragraph defense for each threshold (GVF 0.6, |I_xy|>0.15, ρ>0.20, the 20% distortion) citing a primary source or explicitly labeling it a calibratable policy default (Manual §15.1, research task R-1).

---

## Track 4 — Cartographic theory & design (grounds "publication-quality" and Gates 1/4/5/6)

**Why:** your abstract claims "publication-quality" and grounds visual-variable selection in Bertin. Gates 4/5/6 rest on projection, color, and map-completeness theory. A cartographer reviewer lives here.

- 📖 **Bertin, J., *Semiology of Graphics*, 1967 (Eng. trans. 1983; ESRI reissue 2011)** — the visual-variables vocabulary your Tier 1 is "grounded in." Cited in your abstract; **you must actually know it.** Read the visual-variables chapter.
- 📖 MacEachren, A., *How Maps Work: Representation, Visualization, and Design*, 1995 — cognition of map reading; grounds *why* bivariate maps are cognitively expensive (Gate 3b's premise).
- 📖 **Brewer, C., *Designing Better Maps* (2nd ed.) and the ColorBrewer work (Brewer et al., *The Cartographic Journal*)** — grounds Gate 5's palette prescriptions and the colorblind-safe requirement. ColorBrewer is your embedded palette source.
- 📖 Tufte, E., *The Visual Display of Quantitative Information*, 1983 — "data-ink ratio," the phrase your revised abstract uses for the stylesheet claim.
- 📖 Stevens, J., *Bivariate Choropleth Maps* (joshuastevens.net tutorial, 2015) — the exact 3×3 palette construction your code uses (`BIVAR_HEX`); cite the method even if informal.
- 📖 Projection distortion (Gate 4): 📖 Snyder, J.P., *Map Projections: A Working Manual*, USGS PP1395, 1987 — Tissot indicatrix, areal distortion math. Your Gate-4 spec computes exactly this.
- 📖 Monmonier, M., *How to Lie with Maps*, 3rd ed. — the popular framing of "fluent but misleading maps"; a great intro-section citation and a talk-opener.

**Deliverable:** the intro's "beautiful wrong map" framing gains authority when each failure mode cites its cartographic source (bad breaks→Jenks/Coulson; bad projection→Snyder; bad color→Brewer; bad bivariate→MacEachren).

---

## Track 5 — Geospatial retrieval, STAC & vector search (grounds Tier 3)

**Why:** grounds the hybrid-retrieval module and the "spatial-first" contract; read when building V2-P5.

- 📖 STAC specification (stacspec.org) — the catalog standard your indexer targets; read the item/collection/bbox model.
- 📖 Qdrant documentation — payload filtering + vector search (the mechanism behind your Stage-1/Stage-2 split).
- 📖 The RAG literature (Lewis et al., *Retrieval-Augmented Generation*, NeurIPS 2020) — the general pattern; your contribution is the *spatial-first ordering* that prevents embeddings from vetoing geometry.
- 📖 R-tree / spatial indexing (Guttman, 1984) and PostGIS GiST docs — grounds the compute-router's exact-intersection tier (ST_Intersects, C7′).

---

## Track 6 — Secure code execution & LLM safety (grounds the sandbox)

**Why:** grounds the sandbox security claims; read when building V2-P7.

- 📖 gVisor documentation (gvisor.dev) — the user-space-kernel isolation model; the *actual* boundary (vs. the AST blacklist).
- 📖 Python sandboxing lore — the canonical "why `exec` sandboxes leak" writeups (the `().__class__.__mro__[1].__subclasses__()` escape family your sanitizer blocks); read enough to internalize *"blacklists raise cost; containers are the boundary"* (Manual §10, Presentation Guide Q10).
- 🔎 Note from the field: the GISclaw authors document that single-pass LLMs "produce syntactically valid but semantically incorrect GIS code" — [arXiv:2603.26845](https://arxiv.org/html/2603.26845). This is external evidence for *why your gates are needed*; cite it in the intro.

---

## Track 7 — Benchmarks & evaluation (grounds your evaluation + the CartoValidBench opportunity)

**Why:** grounds Blueprint §9 and the "validity benchmark" contribution (Publication Guide §5). Read before designing the evaluation.

| Work | Read for |
|---|---|
| 🔎 *GeoAnalystBench: assessing LLMs for spatial-analysis workflow & code generation* — [arXiv:2509.05881](https://arxiv.org/html/2509.05881v1) | how the field measures spatial-analysis agents (task success) — the gap you fill (validity) |
| 🔎 *GeoBenchX: Benchmarking LLMs in Multistep Geospatial Tasks*, ACM SIGSPATIAL GenAI workshop 2025 — [ACM](https://dl.acm.org/doi/10.1145/3764915.3770721) | multistep task benchmarking; venue signal (the workshop = your R1 target) |
| 🔎 GeoAgentBench / GeoNatureAgent (2026 arXiv preprints, from the search) | frontier vs. open-weight model comparison; evaluation design patterns |

**The opening:** none of these measures *output validity*. Your labeled corpus (prompts × expected gate outcomes, including should-refuse cases) is the seed of the first cartographic-validity benchmark — a second publishable artifact.

---

## Appendix — a 3-week crash program (if time-boxed before the journal draft)

- **Week 1 (competition):** Track 1 in full + the 2×2 figure + three distinction sentences. Skim Track 2. → you can write related work.
- **Week 2 (your own math):** Track 3 (Jenks/GVF, Moran/Anselin, **Lee's L**, SAR/Openshaw) + Track 4 Bertin & Brewer. → you can defend every gate and threshold.
- **Week 3 (build-facing):** Tracks 5–7 as relevant to the next build phase + the evaluation design (Blueprint §9). → you can specify the benchmark and the human eval.

Keep the synthesis matrix updated as you go; by the end it is simultaneously your related-work section, your novelty defense, and your reviewer-question insurance.

---

## Consolidated verified sources (2026-07-06)

- [LLM-Geo (Li & Ning 2023)](https://github.com/gladcolor/LLM-Geo) · [Autonomous GIS agenda 2025 (arXiv)](https://arxiv.org/abs/2503.23633) · [Annals of GIS version](https://www.tandfonline.com/doi/full/10.1080/19475683.2025.2552161)
- [LLM-Find / data-retrieval agent 2025](https://www.tandfonline.com/doi/full/10.1080/17538947.2025.2458688)
- [GIS Copilot 2025 (arXiv)](https://arxiv.org/abs/2411.03205) · [repo](https://github.com/Teakinboyewa/SpatialAnalysisAgent)
- [CartoAgent 2025 (arXiv)](https://arxiv.org/abs/2505.09936) · [repo](https://github.com/GISense/CartoAgent)
- [MapMate 2025](https://www.sciencedirect.com/science/article/pii/S1569843225007204)
- [Neuro-Symbolic AI in 2024: A Systematic Review](https://arxiv.org/pdf/2501.05435)
- [GeoAnalystBench](https://arxiv.org/html/2509.05881v1) · [GeoBenchX (ACM)](https://dl.acm.org/doi/10.1145/3764915.3770721) · [GISclaw](https://arxiv.org/html/2603.26845)

*Foundational (📖) works above are cited from established scholarship — verify exact edition/year/pages against the publisher or a library database before putting them in a manuscript bibliography.*
