# Citation Gaps

**No bibliography entry in this draft was written from memory.** Entries in `paper/submission/latex/references.bib` were retrieved from the CrossRef API by DOI; everything still carrying a marker in the text is listed below as outstanding.

## Category A — RESOLVED (6 of 10): retrieved from CrossRef, in `references.bib`

Each record below was fetched live from `api.crossref.org` on 2026-08-19 and carries a complete author list, volume, issue, pages, and DOI. These now render as `\cite{}` in the LaTeX and as author-year in the Markdown.

| BibTeX key | Work | DOI |
|---|---|---|
| `li2023autonomous` | Li & Ning, *Autonomous GIS: the next-generation AI-powered GIS*, Int. J. Digital Earth 16(2), 4668–4686 | 10.1080/17538947.2023.2278895 |
| `li2025giscience` | Li, Ning, Gao, Janowicz, Li, et al. (16 authors), *GIScience in the era of Artificial Intelligence*, Annals of GIS 31(4), 501–536 | 10.1080/19475683.2025.2552161 |
| `akinboyewa2025giscopilot` | Akinboyewa, Li, Ning, Lessani, *GIS Copilot*, Int. J. Digital Earth 18(1) | 10.1080/17538947.2025.2497489 |
| `ning2025llmfind` | Ning, Li, Akinboyewa, Lessani, *An autonomous GIS agent framework for geospatial data retrieval*, Int. J. Digital Earth 18(1) | 10.1080/17538947.2025.2458688 |
| `wang2025cartoagent` | Wang, Kang, Gong, Zhao, Feng, Zhang, Li, *CartoAgent*, 39(9), 1904–1937 | 10.1080/13658816.2025.2507844 |
| `krechetova2025geobenchx` | Krechetova & Kochedykov, *GeoBenchX*, ACM SIGSPATIAL GenAI workshop, 27–35 | 10.1145/3764915.3770721 |

## Category A′ — OUTSTANDING (4 of 10)

| Marker | Work | Why unresolved |
|---|---|---|
| `[CITE: GeoAnalystBench]` | *GeoAnalystBench* (arXiv:2509.05881) | arXiv API returned HTTP 429 / timeouts from this environment; no CrossRef DOI found |
| `[CITE: Neuro-Symbolic AI systematic review 2024]` | *Neuro-Symbolic AI in 2024: A Systematic Review* (arXiv:2501.05435) | same |
| `[CITE: GISclaw]` | GISclaw — source of the "syntactically valid but semantically incorrect GIS code" observation (arXiv:2603.26845) | same |
| `[CITE: MapMate 2025]` | *MapMate* (ScienceDirect PII S1569843225007204) | **CrossRef title search returned a different work** — a MODSIM2025 conference paper, not the ScienceDirect article. Deliberately not used: a plausible-looking wrong citation is worse than a marked gap. |

> **Note on the CartoAgent citation.** Its record names the journal it appeared in, as any correct citation must. That is a statement about *that* work's publication history and carries no implication about where this draft is aimed; this manuscript still names no target venue.

## Category B — Foundational works needing edition/page confirmation

Real, canonical works cited from established scholarship. The literature guide explicitly warns: *do not trust any AI for a bibliography without checking.* Confirm each against a publisher or library record.

| Marker | Work |
|---|---|
| `[CITE-VERIFY: Jenks 1967]` | Jenks, *The Data Model Concept in Statistical Mapping*, Int. Yearbook of Cartography |
| `[CITE-VERIFY: Coulson 1987]` | Coulson, *In the Matter of Class Intervals*, Cartographica |
| `[CITE-VERIFY: Jiang 2013]` | Jiang, *Head/Tail Breaks*, The Professional Geographer |
| `[CITE-VERIFY: Moran 1950]` | Moran, *Notes on Continuous Stochastic Phenomena*, Biometrika |
| `[CITE-VERIFY: Anselin 1995]` | Anselin, *Local Indicators of Spatial Association — LISA*, Geographical Analysis |
| `[CITE-VERIFY: Anselin 1988]` | Anselin, *Spatial Econometrics: Methods and Models* |
| `[CITE-VERIFY: Lee 2001]` | Lee, *Developing a bivariate spatial association measure*, J. Geographical Systems — **highest priority**: the rigorous alternative to our null model, and the reference a spatial-statistics reviewer is most likely to raise |
| `[CITE-VERIFY: Bertin 1983]` | Bertin, *Semiology of Graphics* (Eng. trans.; ESRI reissue 2011) |
| `[CITE-VERIFY: Brewer, ColorBrewer]` | Brewer, *Designing Better Maps* / ColorBrewer, The Cartographic Journal |
| `[CITE-VERIFY: MacEachren 1995]` | MacEachren, *How Maps Work* |
| `[CITE-VERIFY: Snyder 1987]` | Snyder, *Map Projections: A Working Manual*, USGS PP1395 |
| `[CITE-VERIFY: Burbidge, Magee & Robb 1988]` | inverse hyperbolic sine transform, JASA |
| `[CITE-VERIFY: Pan et al., Logic-LM]` | EMNLP 2023 |
| `[CITE-VERIFY: Olausson et al., LINC]` | EMNLP 2023 |
| `[CITE-VERIFY: Garcez & Lamb]` | *Neuro-symbolic AI: The 3rd Wave* |
| `[CITE-VERIFY: Schick et al., Toolformer]` | NeurIPS 2023 |
| `[CITE-VERIFY: Yao et al., ReAct]` | 2023 |

## Category C — Claims that may need a citation but currently have none

| Location | Claim | Note |
|---|---|---|
| §1 | "unreadable to a substantial fraction of viewers" (colour-vision deficiency prevalence) | Needs a prevalence source; the ~1-in-12-men figure is standard but should be cited |
| §4.5 | Rainbow ramps have non-monotonic perceived lightness | Well documented in visualisation literature; needs a specific source |
| §7.1 | "models are replaced every few months" | Rhetorical; either cite or soften |
