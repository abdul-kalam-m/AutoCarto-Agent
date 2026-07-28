"""Orchestrator — the Propose-Verify-Execute state machine (Blueprint §4).

The system's namesake, and previously the single largest gap between the
paper's claims and the repository: prior to this module, the loop existed
only as prose and as ``demo.py``'s hard-coded proposals (Manual §6.2-1).

State machine (Blueprint §4):

    ParseIntent -> Retrieve -> Profile -> Propose -> Validate
        Validate --[all gates PASS/WARN]--> Execute -> done
        Validate --[any REJECT]--> Mandate -> Propose (iter++)
        Mandate --[iter > max_iter]--> HumanReview -> done

"Pure core, effectful edges": ``run()`` is deterministic given its
injected collaborators (``LLMClient``, the six gates, ``SandboxExecutor``)
and a seed. The orchestrator itself owns the iteration counter — this
retires Gate 2's stateful ``iteration_count`` footgun (Manual TD-10) by
constructing a fresh ``ClassificationDiagnosticEngine`` every iteration,
so Gate 2's own internal HITL branch never fires; only the orchestrator's
``max_iter`` bound decides when to stop.

Gate execution order (contracts.GATE_ORDER): G1 -> G4 -> [G3a|G3b] -> G2 ->
G5, run against every proposal and collected into one consolidated mandate
(Blueprint §3.6 — fewer round-trips than gate-by-gate rejection). G6 runs
once, after codegen, against the renderer's own manifest — there is
nothing an LLM iteration could "fix" about a completeness gap in an
audited template, so G6 is a post-render assertion, not a proposal-loop
gate (see ``_run_post_render_gate6`` docstring).

Retrieve/Profile (Tier 3) are represented by an injected ``Dataset`` rather
than a real STAC/Qdrant pipeline — that integration is Phase 3 scope
(Manual §11) and remains unbuilt; this module's job is the orchestration
loop and the authority-boundary contract around it, which test with any
``Dataset``, real or synthetic, exactly as ``demo.py`` already proves is
possible for the gates individually.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from autocarto.contracts import (
    AreaOfInterest,
    AuthorityViolation,
    FieldSchema,
    GateResult,
    GateSuiteResult,
    MapProposal,
    Prescription,
    ProvenancedValue,
    RenderPlan,
    SemanticContext,
    adapt_gate2,
    adapt_gate3b,
)
from autocarto.execution.gates.gate1_crs import CRSIntegrityGate
from autocarto.execution.gates.gate2_classification import ClassificationDiagnosticEngine
from autocarto.execution.gates.gate3a_spatial_autocorrelation import SpatialStructureGate
from autocarto.execution.gates.gate3b_bivariate_correlation import BivariateCorrelationGate
from autocarto.execution.gates.gate4_projection_distortion import ProjectionDistortionGate
from autocarto.execution.gates.gate5_color_accessibility import ColorAccessibilityGate
from autocarto.execution.gates.gate6_completeness import CompletenessGate, RenderManifest
from autocarto.execution.sandbox import CodeSanitizer
from autocarto.semantic.codegen import generate as codegen_generate
from autocarto.semantic.llm_client import LLMCallRecord, LLMClient

_BIVARIATE_DEFAULT_PALETTE: List[str] = [
    "#e8e8e8", "#ace4e4", "#5ac8c8",
    "#dfb0d6", "#a5add3", "#5698b9",
    "#be64ac", "#8c62aa", "#3b4994",
]
_PROPORTIONAL_SYMBOL_DEFAULT_PALETTE: List[str] = ["#2166ac"]
_DEFAULT_CHOROPLETH_CMAP = "YlOrRd"
_DEFAULT_N_CLASSES = 5


def _sample_colormap_hex(cmap_name: str, n: int) -> List[str]:
    """Concrete hex classes sampled from a named matplotlib colormap.

    Gate 5 needs literal hex colors to CVD-simulate; a bare colormap *name*
    is not evaluable. Resolving to hex once, up front, also means Gate 5
    validates the exact colors codegen will render — not a proxy.
    """
    import matplotlib
    from matplotlib.colors import to_hex
    n = max(n, 2)
    cmap = matplotlib.colormaps[cmap_name].resampled(n)
    return [to_hex(cmap(i / (n - 1))) for i in range(n)]


@dataclass
class Dataset:
    """Tier-2-only container: real geometry and variable values.

    Never passed into a `SemanticContext` — only its schema (via
    `to_field_schemas` / `to_aoi`) is allowed to cross into Tier 1.
    `weights` must be a row-standardized queen-contiguity matrix (or
    `None` if spatial-structure gates should be skipped, e.g. for a
    proportional-symbol-only dataset).
    """
    id: str
    gdf: Any  # geopandas.GeoDataFrame — typed Any to avoid a hard import here
    variables: Dict[str, np.ndarray]
    variable_roles: Dict[str, str] = field(default_factory=dict)
    weights: Optional[np.ndarray] = None
    description: Optional[str] = None
    citation: str = "Source: unspecified"
    # Optional per-variable citation fragments (e.g. {"asthma_prevalence":
    # "Asthma: CDC PLACES 2023, measure CASTHMA."}), appended to `citation`
    # for only the variables actually in a given proposal -- see
    # _resolve_citation. A dataset that mixes sources (e.g. real_data.py's
    # ACS income + CDC asthma) must not print every source's citation on
    # every map regardless of which variables that specific map uses; a
    # flat `citation` string structurally cannot express that distinction.
    # None (the default) preserves old behavior exactly: `citation` alone.
    citation_by_variable: Optional[Dict[str, str]] = None
    # Optional per-variable unit ("USD", "percent", ...), used to format
    # legend/colorbar tick labels sensibly (currency with thousands
    # separators, a percent sign, etc.) instead of printing raw floats --
    # and, via to_field_schemas below, given to the LLM as context too.
    # Empty dict (the default) falls back to plain thousands-separator
    # formatting with no unit symbol.
    variable_units: Dict[str, str] = field(default_factory=dict)

    def to_field_schemas(self) -> List[FieldSchema]:
        return [
            FieldSchema(
                name=name, dtype=str(np.asarray(arr).dtype),
                role=self.variable_roles.get(name),
                unit=self.variable_units.get(name),
            )
            for name, arr in self.variables.items()
        ]

    def to_aoi(self) -> AreaOfInterest:
        try:
            bounds = tuple(float(b) for b in self.gdf.to_crs(epsg=4326).total_bounds)
        except Exception:
            bounds = tuple(float(b) for b in self.gdf.total_bounds)
        return AreaOfInterest(
            id=self.id, bbox_4326=bounds,
            feature_count=int(len(self.gdf)), description=self.description,
        )

    def crs_epsg(self) -> Optional[int]:
        return self.gdf.crs.to_epsg() if self.gdf.crs is not None else None


@dataclass
class MapResult:
    """What `Orchestrator.run` returns: success/failure, the full iteration
    trace (replayable — Blueprint §4), and, on success, the rendered
    artifact's code, manifest, and figure."""
    success: bool
    iterations: int
    trace: Dict[str, Any]
    proposal: Optional[MapProposal] = None
    code: Optional[str] = None
    manifest: Optional[RenderManifest] = None
    figure: Optional[Any] = None
    human_review: bool = False
    insufficiency_report: Optional[str] = None

    def trace_json(self) -> str:
        return json.dumps(self.trace, indent=2, sort_keys=False)


class Orchestrator:
    """Propose-Verify-Execute loop. See module docstring for the state machine."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        max_iter: int = 3,
        seed: int = 0,
    ) -> None:
        self.llm = llm
        self.max_iter = max_iter
        self.seed = seed
        self.gate1 = CRSIntegrityGate()
        self.gate3a = SpatialStructureGate()
        self.gate3b = BivariateCorrelationGate()
        self.gate4 = ProjectionDistortionGate()
        self.gate5 = ColorAccessibilityGate()
        self.gate6 = CompletenessGate()

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, prompt: str, dataset: Dataset) -> MapResult:
        trace: Dict[str, Any] = {
            "prompt": prompt,
            "dataset_id": dataset.id,
            "seed": self.seed,
            "max_iter": self.max_iter,
            "iterations": [],
        }

        prescriptions: List[Prescription] = []
        diagnoses: List[str] = []
        iteration = 0
        proposal: Optional[MapProposal] = None
        suite: Optional[GateSuiteResult] = None
        resolved: Dict[str, Any] = {}

        while iteration <= self.max_iter:
            context = SemanticContext(
                dataset_schemas=dataset.to_field_schemas(),
                aoi=dataset.to_aoi(),
                diagnoses=list(diagnoses),
                prescriptions=list(prescriptions),
            )
            proposal, llm_record = self.llm.propose(context, prompt)
            suite, resolved = self._run_pre_render_gates(proposal, dataset)

            trace["iterations"].append({
                "iteration": iteration,
                "llm_call": llm_record.to_dict(),
                "proposal": proposal.to_dict(),
                "gate_suite": suite.to_dict(),
            })

            if suite.decision != "REJECT":
                break

            new_prescriptions = suite.consolidated_mandate()
            prescriptions.extend(new_prescriptions)
            diagnoses.extend(
                f"{r.gate_id}:{r.diagnostics.get('diagnosis', r.decision)}"
                for r in suite.rejections
            )
            iteration += 1

        assert proposal is not None and suite is not None  # loop always runs >=1 time

        if suite.decision == "REJECT":
            report = (
                f"Automated validation failed to converge after {self.max_iter} "
                f"mandate iterations. Outstanding rejections: "
                f"{[r.gate_id for r in suite.rejections]}. Returning for human review."
            )
            trace["human_review"] = True
            trace["insufficiency_report"] = report
            return MapResult(
                success=False, iterations=iteration, trace=trace,
                proposal=proposal, human_review=True, insufficiency_report=report,
            )

        # ── Execute: build a provenanced RenderPlan, generate code, render ──
        render_plan = self._build_render_plan(proposal, resolved)

        try:
            code, manifest = codegen_generate(
                proposal, render_plan,
                citation=self._resolve_citation(dataset, proposal.variables),
                crs_note=f"EPSG:{render_plan.projection.value}",
                correlation_note=self._correlation_note(suite),
                variable_unit=dataset.variable_units.get(proposal.variables[0]),
            )
        except AuthorityViolation as exc:
            trace["execution_error"] = f"AuthorityViolation: {exc}"
            return MapResult(success=False, iterations=iteration, trace=trace, proposal=proposal)

        gate6_result = self._run_post_render_gate6(manifest, proposal.map_type)
        trace["gate6"] = gate6_result.to_dict()

        exec_globals = self._build_exec_globals(dataset, proposal)
        ok, error = self._execute_render(code, exec_globals)
        trace["render_success"] = ok
        if error:
            trace["render_error"] = error

        figure = exec_globals.get("fig") if ok else None
        trace["code_hash"] = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]

        return MapResult(
            success=ok, iterations=iteration, trace=trace, proposal=proposal,
            code=code, manifest=manifest, figure=figure,
        )

    # ── Pre-render gate suite ────────────────────────────────────────────────

    def _run_pre_render_gates(
        self, proposal: MapProposal, dataset: Dataset,
    ) -> "tuple[GateSuiteResult, Dict[str, Any]]":
        """Run G1/G4/[G3a|G3b]/G2/G5 and return both the suite result and
        the *exact* concrete values each gate was asked to evaluate
        (breaks/epsg/palette). Provenance tagging (`_build_render_plan`)
        derives directly from these — the value that gets rendered is
        provably the same value the gate suite actually validated, not a
        separately recomputed "default" compared after the fact.
        """
        results: List[GateResult] = []
        primary_var = proposal.variables[0]
        role = dataset.variable_roles.get(primary_var, "count")

        results.append(self.gate1.evaluate(dataset.gdf, proposal.map_type, role))

        epsg = proposal.projection_epsg or dataset.crs_epsg() or 4326
        try:
            bounds_4326 = tuple(float(b) for b in dataset.gdf.to_crs(epsg=4326).total_bounds)
        except Exception:
            bounds_4326 = tuple(float(b) for b in dataset.gdf.total_bounds)
        results.append(self.gate4.evaluate(epsg, bounds_4326, proposal.map_purpose))

        if proposal.map_type == "choropleth" and dataset.weights is not None:
            results.append(self.gate3a.evaluate(
                dataset.variables[primary_var], dataset.weights, random_state=self.seed,
            ))
        elif proposal.map_type == "bivariate" and dataset.weights is not None and len(proposal.variables) >= 2:
            x = dataset.variables[proposal.variables[0]]
            y = dataset.variables[proposal.variables[1]]
            results.append(adapt_gate3b(
                self.gate3b.evaluate(x, y, dataset.weights, random_state=self.seed)
            ))

        breaks_used: Optional[List[float]] = None
        if proposal.map_type == "choropleth":
            engine = ClassificationDiagnosticEngine(random_state=self.seed)  # fresh -- TD-10
            g2 = engine.evaluate(
                dataset.variables[primary_var],
                proposed_method=proposal.classification_method or "jenks",
                proposed_breaks=proposal.classification_breaks,
            )
            results.append(adapt_gate2(g2))
            breaks_used = proposal.classification_breaks

        n_classes = len(breaks_used) - 1 if breaks_used else _DEFAULT_N_CLASSES
        palette_used = self._resolve_palette(proposal, n_classes)
        results.append(self.gate5.evaluate(
            palette_used, diverging=(proposal.map_type == "bivariate"),
            variable_names=proposal.variables,
        ))

        resolved = {"breaks": breaks_used, "epsg": epsg, "palette": palette_used}
        return GateSuiteResult(results=results), resolved

    def _run_post_render_gate6(self, manifest: RenderManifest, map_type: str) -> GateResult:
        """G6 runs once, after codegen, against the manifest the (audited,
        LLM-unmodifiable) template produced. Unlike G1-G5, there is no
        LLM-side fix for a completeness gap here — a REJECT would indicate
        a defect in the template itself, not the proposal, so this gate is
        an assertion recorded in the trace rather than a loop participant.
        """
        return self.gate6.evaluate(manifest, map_type)

    # ── RenderPlan construction: provenance derived from what the winning ──
    # ── gate suite actually evaluated, not from a re-derived comparison ────

    @staticmethod
    def _build_render_plan(proposal: MapProposal, resolved: Dict[str, Any]) -> RenderPlan:
        """Build a RenderPlan whose every value is exactly what the gate
        suite that just PASSED (`suite.decision != "REJECT"`) evaluated.

        This makes "GATE_PRESCRIBED" mean what it should: not narrowly
        "the product of a REJECT+mandate cycle," but "validated by the
        deterministic gate before use" — which covers both a corrected
        prescription *and* an LLM proposal the gate independently checked
        and accepted. Either way, invariant #2 holds: nothing here is an
        unvalidated free-LLM number. `breaks`/`projection` fall back to
        TEMPLATE_DEFAULT only when no corresponding gate ran at all (e.g.
        Gate 2 does not apply to bivariate/proportional-symbol maps).
        """
        breaks = resolved["breaks"]
        breaks_pv = (
            ProvenancedValue(breaks, "GATE_PRESCRIBED", "G2")
            if breaks is not None
            else ProvenancedValue(None, "TEMPLATE_DEFAULT")
        )
        projection_pv = ProvenancedValue(resolved["epsg"], "GATE_PRESCRIBED", "G4")
        palette_pv = ProvenancedValue(resolved["palette"], "GATE_PRESCRIBED", "G5")
        template_pv = ProvenancedValue(
            proposal.template_id or f"{proposal.map_type}_v1", "TEMPLATE_DEFAULT",
        )
        return RenderPlan(
            breaks=breaks_pv, projection=projection_pv,
            palette=palette_pv, template_id=template_pv,
        )

    @staticmethod
    def _resolve_palette(proposal: MapProposal, n_classes: int) -> List[str]:
        if isinstance(proposal.palette, list):
            return proposal.palette
        if proposal.map_type == "bivariate":
            return list(_BIVARIATE_DEFAULT_PALETTE)
        if proposal.map_type == "proportional_symbol":
            return list(_PROPORTIONAL_SYMBOL_DEFAULT_PALETTE)
        cmap_name = proposal.palette if isinstance(proposal.palette, str) else _DEFAULT_CHOROPLETH_CMAP
        return _sample_colormap_hex(cmap_name, n_classes)

    # ── Execution ─────────────────────────────────────────────────────────────

    def _build_exec_globals(self, dataset: Dataset, proposal: MapProposal) -> Dict[str, Any]:
        primary_var = proposal.variables[0]
        exec_globals: Dict[str, Any] = {"gdf": dataset.gdf}
        if proposal.map_type == "choropleth":
            gdf_with_col = dataset.gdf.copy()
            gdf_with_col["_autocarto_variable"] = dataset.variables[primary_var]
            exec_globals["gdf"] = gdf_with_col
            exec_globals["variable_column"] = "_autocarto_variable"
        elif proposal.map_type == "bivariate":
            x = dataset.variables[proposal.variables[0]]
            y = dataset.variables[proposal.variables[1]]
            exec_globals["bivariate_colors"] = self._bivariate_tertile_colors(x, y)
        elif proposal.map_type == "proportional_symbol":
            exec_globals["values"] = np.asarray(dataset.variables[primary_var], dtype=float)
        return exec_globals

    @staticmethod
    def _bivariate_tertile_colors(x: np.ndarray, y: np.ndarray) -> List[str]:
        def tertile_class(arr: np.ndarray) -> np.ndarray:
            q33, q67 = np.percentile(arr, [33.33, 66.67])
            cls = np.zeros(len(arr), dtype=int)
            cls[arr >= q33] = 1
            cls[arr >= q67] = 2
            return cls

        x_cls, y_cls = tertile_class(np.asarray(x, dtype=float)), tertile_class(np.asarray(y, dtype=float))
        grid = np.array(_BIVARIATE_DEFAULT_PALETTE).reshape(3, 3)
        return [grid[xc, yc] for xc, yc in zip(x_cls, y_cls)]

    @staticmethod
    def _execute_render(code: str, exec_globals: Dict[str, Any]) -> tuple:
        """Sanitize the generated code, then execute it with real data bound.

        SCOPE NOTE: full container-isolated execution with live-data
        injection is Phase 5 / TD-5 territory (Manual §10) and remains
        unbuilt — `SandboxExecutor`'s docker/`_DevOnlySandboxExecutor` path
        has no mechanism to bind a live GeoDataFrame into its exec globals
        (it accepts only a JSON-serializable `data_snapshot`, which
        `_execute_inprocess` does not consume). Because this code is
        template-derived (`codegen.py`) with only gate-validated constants
        substituted in — never free-form LLM logic — running it in-process
        after a clean sanitizer pass is a defensible boundary for this
        phase. This is *not* a claim that untrusted LLM-authored code is
        safely contained; that claim is scoped to gVisor container
        isolation alone (Manual §10), which this method does not provide.
        """
        is_safe, sanitized, violations = CodeSanitizer.sanitize(code)
        if not is_safe:
            return False, f"Generated code failed sanitizer: {violations}"
        try:
            import matplotlib
            matplotlib.use("Agg")
            exec(compile(sanitized, "<autocarto-generated>", "exec"), exec_globals)  # noqa: S102
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
        return True, None

    @staticmethod
    def _correlation_note(suite: GateSuiteResult) -> str:
        for r in suite.results:
            if r.gate_id == "G3b":
                d = r.diagnostics
                return (
                    f"I_xy={d.get('bivariate_morans_i', 0):+.3f}, "
                    f"rho={d.get('spearman_rho', 0):+.3f}, {r.decision}"
                )
        return ""

    @staticmethod
    def _resolve_citation(dataset: Dataset, variables: List[str]) -> str:
        """Build the citation actually printed on the map: `dataset.citation`
        (the always-true part, e.g. geometry provenance) plus only the
        per-variable fragments for variables this specific map uses.

        Without this, a dataset mixing sources (real_data.py's ACS income +
        CDC asthma) prints every source's citation on every map regardless
        of which variables that map actually shows -- confirmed: mapping
        income alone produced a footer citing CDC PLACES asthma data never
        used in that render. Found by a user comparing a rendered map
        against its own trace, not by this project's own testing.
        """
        if not dataset.citation_by_variable:
            return dataset.citation
        parts = [dataset.citation] if dataset.citation else []
        for v in variables:
            frag = dataset.citation_by_variable.get(v)
            if frag:
                parts.append(frag)
        return " ".join(parts)
