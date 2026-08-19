# 3. Architecture

## 3.1 Three tiers and one boundary

AutoCarto-Agent is organised into three tiers separated by an authority boundary (Figure 2).

**Tier 1 — Semantic Engine.** A frozen language-model checkpoint at temperature 0, restricted to cartographic concepts: parsing the request into a mapping intent, selecting the visual encoding channel, selecting a map type and audited render template, and assembling declarative code by filling typed slots. Its inputs are variable *names*, data types, semantic roles, and units — never values. The implementation supports an open-weights model (Llama 3.1 70B, served through a hosted inference endpoint) and a deterministic rule-based client used for offline testing; the two are interchangeable behind one interface.

That interchangeability is not merely an engineering convenience — it is a consequence of the authority design, and it has an evaluative implication used throughout Section 6. Because every gate statistic is computed by Tier 2 from the data and the spatial weights alone, a gate's diagnostics and verdict are invariant to *which* Tier-1 client produced the proposal. The model influences which map is attempted; it cannot influence what the mathematics returns about it.

**Tier 2 — Deterministic Execution Engine.** Ordinary, non-stochastic software. It owns the orchestration loop, runs the six validation gates, computes every classification and statistic, and renders inside an isolated container. Nothing it computes depends on model output except the categorical choices the model is permitted to make.

**Tier 3 — Data Fabric.** Retrieval with a spatial-first contract: a deterministic bounding-box filter runs before semantic ranking, so embedding similarity can never override geometry, followed by exact geometric refinement and a seven-point metadata quality rubric that can refuse insufficiently documented data outright.

The dashed boundary in Figure 2 is the load-bearing element. Two invariants define it: raw data values never cross into Tier 1, and no numeric constant reaches the executed render without deterministic provenance. The first prevents the model from reasoning over data it might misread; the second prevents it from inventing a number even when it has not seen the data.

## 3.2 The provenance contract

The second invariant is enforced structurally rather than by policy. Every constant in the render plan is wrapped in a value object carrying a provenance tag: `GATE_PRESCRIBED` (computed by a gate), `TEMPLATE_DEFAULT` (a fixed constant in an audited template), or `FREE_LLM` (originating from generation). The plan's validation method refuses any plan containing a `FREE_LLM` constant, raising before any code text is produced.

This turns "the model never decides a number" from a claim about intent into a checkable property of the execution trace. An auditor does not need to trust the description of the architecture; they can read the trace and confirm that every numeric constant in the executed code resolves to either a gate computation or an audited template default.

The same discipline governs code generation. The model does not write free-form logic on the render path. It fills named slots in one of three audited templates (choropleth, bivariate choropleth, proportional symbol), and each template declares which completeness elements it guarantees, which Gate 6 then checks. Restricting generation to slot-filling eliminates most of the code-injection surface as a side effect: a template the model cannot alter has no injection surface beyond its slot values, and those are typed and provenance-checked.

## 3.3 Propose–Verify–Execute

The orchestrator drives a bounded state machine.

**Propose.** Tier 1 receives a semantic context — schemas, area of interest, and any prescriptions accumulated from previous rejections — and returns a map proposal.

**Verify.** The gate suite runs in a fixed order chosen so that each gate's preconditions are established by its predecessors: coordinate-system integrity and projection distortion first (they determine whether any area-based computation is meaningful), then spatial-structure tests, then classification, then colour. Every gate returns a uniform result carrying a decision, diagnostics, and — where the decision is a rejection — a prescription. A structural invariant enforces that a rejection cannot be returned without one.

**Mandate.** Rejections are consolidated into a single mandate rather than round-tripped one gate at a time, and returned to Tier 1 for the next iteration. Because the prescription contains the exact constants, the next proposal is a transcription rather than a fresh attempt.

**Execute.** Once no gate rejects, the plan is validated for provenance, code is generated from the audited template, and the result is rendered. A final completeness gate checks the emitted render manifest.

The iteration count is owned by the orchestrator, not the model, and is capped at three. On exhaustion the system produces an insufficiency report for human review rather than continuing. This is the concrete form of the convergence argument: the loop terminates because the space of remaining decisions shrinks to transcription after the first mandate, and terminates unconditionally at the cap regardless.

## 3.4 Execution isolation

Generated code is executed under two distinct mechanisms, and the distinction between them is stated explicitly because conflating them would overclaim.

An abstract-syntax-tree sanitizer runs before execution, rejecting imports outside a whitelist, attribute access into reflection chains, and write-mode file operations. This is a **cost-raiser**, not a boundary; static blacklists are bypassable in principle and we do not claim otherwise.

The boundary is a container: Docker with a gVisor runtime, no network namespace, all capabilities dropped, non-root, no shell, read-only filesystem. Section 6.7 reports the red-team evaluation of that boundary, conducted with the sanitizer deliberately disabled so that the container alone was under test.
