"""Gate 2: Classification Validity — Diagnostic Mode, Not Binary Gate.

This is the core intellectual contribution of AutoCarto-Agent.
The gate characterizes the distribution shape, computes Goodness of
Variance Fit, and issues prescriptive remedies with mandated break points.
The LLM is forced into a code-assembler role.

Diagnostic -> Prescriptive Rejection Pipeline:
    1. Characterize distribution (skewness, zero-inflation, outliers)
    2. Compute GVF for proposed classification
    3. If rejected, diagnose root cause and prescribe exact remedy
    4. HITL escape hatch after 3 failed iterations
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Literal
import numpy as np
from scipy import stats as scipy_stats
import warnings

# Attempt import; classification is not mandatory if only diagnostics needed
try:
    import jenkspy
    HAS_JENKSPY = True
except ImportError:
    HAS_JENKSPY = False


@dataclass
class DistributionProfile:
    """Complete statistical characterization of a variable."""
    n: int
    n_unique: int
    min_val: float
    max_val: float
    mean: float
    median: float
    std: float
    skewness: float
    kurtosis: float
    zero_fraction: float
    outlier_fraction: float  # IQR-based
    shapiro_w: float
    shapiro_p: float
    iqr: float

    @classmethod
    def from_array(cls, x: np.ndarray, random_state: int = 0) -> "DistributionProfile":
        """Compute full distribution profile from a 1D array.

        PATCH: ``random_state`` argument added so that Shapiro-Wilk sampling on
        n>5000 arrays is reproducible, matching the abstract's reproducibility
        claim ("fixed random seed").
        """
        x_clean = x[np.isfinite(x)]
        n = len(x_clean)

        if n < 4:
            return cls(
                n=n, n_unique=0, min_val=0, max_val=0, mean=0, median=0,
                std=0, skewness=0, kurtosis=0, zero_fraction=0,
                outlier_fraction=0, shapiro_w=1.0, shapiro_p=1.0, iqr=0
            )

        q1, q3 = np.percentile(x_clean, [25, 75])
        iqr_val = q3 - q1
        lower_fence = q1 - 1.5 * iqr_val
        upper_fence = q3 + 1.5 * iqr_val

        # Shapiro-Wilk on sample (max 5000 for performance).
        # PATCH: use a seeded Generator so the sample is reproducible.
        if n <= 5000:
            sample = x_clean
        else:
            rng = np.random.default_rng(random_state)
            sample = rng.choice(x_clean, 5000, replace=False)

        shapiro_res = scipy_stats.shapiro(sample)
        return cls(
            n=n,
            n_unique=len(np.unique(x_clean)),
            min_val=float(np.min(x_clean)),
            max_val=float(np.max(x_clean)),
            mean=float(np.mean(x_clean)),
            median=float(np.median(x_clean)),
            std=float(np.std(x_clean)),
            skewness=float(scipy_stats.skew(x_clean)),
            kurtosis=float(scipy_stats.kurtosis(x_clean)),
            zero_fraction=float(np.mean(x_clean == 0)),
            outlier_fraction=float(np.mean((x_clean < lower_fence) | (x_clean > upper_fence))),
            shapiro_w=float(shapiro_res.statistic),
            shapiro_p=float(shapiro_res.pvalue),
            iqr=float(iqr_val),
        )


@dataclass
class DiagnosticResult:
    """Output of the diagnostic pipeline."""
    diagnosis: Literal[
        "well_behaved", "zero_inflated", "heavy_right_skew",
        "outlier_dominated", "discrete_ordinal", "insufficient_variance"
    ]
    gvf: float
    passed: bool
    prescribed_method: Optional[str] = None
    prescribed_breaks: Optional[List[float]] = None
    instruction: Optional[str] = None
    code_snippet: Optional[str] = None
    profile: Optional[DistributionProfile] = None
    # True when the caller already supplied exactly what this gate would
    # prescribe, and it still misses GVF_THRESHOLD. Re-prescribing is then
    # futile -- the remedy IS the proposal -- so the result is reported as
    # the best achievable classification for this distribution rather than
    # as another rejection. `adapt_gate2` maps this to WARN, which does not
    # block execution but records the shortfall in the trace. See the
    # livelock note in `evaluate`.
    best_effort: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializable dict for execution trace JSON.

        `best_effort` is deliberately NOT emitted here. This dict is the
        blessed golden-trace schema for `autocarto demo`
        (output/traces/gate2_classification_trace.json, pinned by
        tests/test_determinism.py), and none of the demo's cases reach the
        best-effort branch -- so adding the key would break a blessed hash
        to record a constant `false`. The flag is not lost: the orchestrator
        path surfaces it through `GateResult.diagnostics["best_effort"]` and
        through the WARN decision itself, which is where it is actionable.
        """
        return {
            "gate": "G2",
            "diagnosis": self.diagnosis,
            "gvf": round(self.gvf, 4),
            "passed": self.passed,
            "prescribed_method": self.prescribed_method,
            "prescribed_breaks": self.prescribed_breaks,
            "instruction": self.instruction,
        }


def _same_prescription(
    proposed_method: Optional[str],
    proposed_breaks: Optional[List[float]],
    prescribed_method: Optional[str],
    prescribed_breaks: Optional[List[float]],
) -> bool:
    """True when the proposal already *is* the prescription.

    Break values make a round trip through the LLM tier and the JSON trace
    (where they are rounded to 6 significant figures for cross-platform CI
    stability), so an exact float comparison would spuriously report
    "different" and reopen the livelock this guard exists to close. The
    tolerance is relative, because break magnitudes span orders of
    magnitude across variables -- dollars, percentages, people per km².

    A prescription with no break values is compared on method alone; that
    is the honest reading, since there is nothing else to transcribe.
    """
    if prescribed_method is None or proposed_method != prescribed_method:
        return False
    if not prescribed_breaks:
        return True
    if not proposed_breaks or len(proposed_breaks) != len(prescribed_breaks):
        return False
    return all(
        # rtol=1e-6 comfortably covers 6-significant-figure rounding while
        # still separating genuinely different break sets.
        abs(a - b) <= 1e-6 * max(1.0, abs(b))
        for a, b in zip(proposed_breaks, prescribed_breaks)
    )


def _dedupe_breaks(breaks: List[float]) -> List[float]:
    """PATCH: collapse adjacent duplicate breaks while preserving order.

    Zero-inflated and constant-tail distributions can produce break sequences
    like ``[0.0, 0.0, 12.3, 50.0]`` which make ``np.digitize`` produce an empty
    interior class and break GVF accounting. We dedupe to keep monotonically
    increasing breakpoints.
    """
    deduped: List[float] = []
    for b in breaks:
        if not deduped or b > deduped[-1]:
            deduped.append(float(b))
    return deduped


def _fmt_breaks(breaks: List[float], sig_figs: int = 6) -> str:
    """Render a break list for the natural-language `instruction` text only.

    Rounds to a fixed number of significant figures rather than embedding
    Python's full-precision float repr. jenkspy/numpy can produce results
    that agree to ~14 significant digits but differ in the last one or two
    across platforms/BLAS builds (harmless, expected float drift) -- at
    full repr precision that drift shows up as a visible text diff in the
    golden-trace comparison, even though `assert_json_equivalent` already
    tolerates it for the numeric `breaks` field itself.

    Do NOT use this for `code_snippet`: test_mandated_code_snippet_is_
    executable_shape asserts the snippet contains prescribed_breaks'
    exact repr, since the snippet is meant to be a faithful, standalone-
    executable reproduction of the real breaks, not just illustrative text.
    """
    return "[" + ", ".join(f"{b:.{sig_figs}g}" for b in breaks) + "]"


class ClassificationDiagnosticEngine:
    """Characterizes distribution and prescribes classification remedies.

    This engine operates on a strict diagnostic -> prescriptive pipeline.
    It never asks the LLM to "consider" alternatives; it mandates the
    exact method and break points required.
    """

    GVF_THRESHOLD = 0.6           # Minimum acceptable GVF
    ZERO_INFLATION_THRESHOLD = 0.40  # Fraction of zeros triggering zero-inflation
    OUTLIER_THRESHOLD = 0.10       # Fraction of outliers triggering head-tail
    DISCRETE_THRESHOLD = 10        # Max unique values for discrete ordinal
    MAX_ITERATIONS = 3

    def __init__(self, random_state: int = 0):
        # PATCH: per-engine seed so distribution sampling is deterministic.
        self.iteration_count = 0
        self.random_state = random_state

    def evaluate(
        self,
        values: np.ndarray,
        proposed_method: str,
        proposed_breaks: Optional[List[float]] = None,
    ) -> DiagnosticResult:
        """Full diagnostic evaluation of a classification proposal.

        Args:
            values: 1D array of variable values
            proposed_method: LLM's proposed method (e.g., "jenks", "quantile")
            proposed_breaks: LLM's proposed break points (if any)

        Returns:
            DiagnosticResult with pass/fail, diagnosis, and prescription
        """
        self.iteration_count += 1
        profile = DistributionProfile.from_array(values, random_state=self.random_state)

        # Step 1: Diagnose the distribution
        diagnosis = self._diagnose(profile)

        # Step 2: If distribution has a mandatory method, reject LLM's choice
        prescribed = self._get_prescription(diagnosis, profile, values)

        if prescribed["method"] and prescribed["method"] != proposed_method:
            return DiagnosticResult(
                diagnosis=diagnosis,
                gvf=0.0,
                passed=False,
                prescribed_method=prescribed["method"],
                prescribed_breaks=prescribed.get("breaks"),
                instruction=prescribed["instruction"],
                code_snippet=prescribed.get("code_snippet"),
                profile=profile,
            )

        # Step 3: Compute GVF for the proposed classification
        if proposed_breaks and len(proposed_breaks) > 1:
            gvf = self._compute_gvf(values, proposed_breaks)
        else:
            gvf = 0.0

        # Step 4: Decision
        #
        # PATCH (orchestrator integration, P2): the pass condition used to
        # require `diagnosis == "well_behaved"` in addition to a good GVF.
        # That is stricter than it needs to be: by this point, Step 2 has
        # already enforced `proposed_method == prescribed["method"]` for
        # every non-well-behaved diagnosis (a mismatch returns early). So
        # for any diagnosis, reaching Step 4 means the method is already
        # correct — the only remaining question is fit quality (GVF).
        #
        # The old, stricter condition meant a classification that exactly
        # transcribed the mandated method AND mandated breaks (GVF=0.97 in
        # the discovered case) was rejected forever, because the diagnosis
        # label ("heavy_right_skew" etc.) describes the *raw distribution*,
        # not the classification quality, and never becomes "well_behaved"
        # just because a good classification was supplied. This produced
        # an unwinnable loop for the LLM with no action that could ever
        # pass Gate 2 — undiscovered until Orchestrator.run() actually
        # drove a second iteration with a correctly-transcribed proposal
        # (see tests/test_orchestrator.py); no prior test exercised that
        # scenario.
        if gvf >= self.GVF_THRESHOLD:
            return DiagnosticResult(
                diagnosis=diagnosis,
                gvf=gvf,
                passed=True,
                profile=profile,
            )
        elif self.iteration_count >= self.MAX_ITERATIONS:
            # HITL escape hatch
            return DiagnosticResult(
                diagnosis=diagnosis,
                gvf=gvf,
                passed=False,
                prescribed_method="manual_review",
                instruction=(
                    f"Automated classification failed after {self.MAX_ITERATIONS} "
                    f"iterations. Distribution diagnosed as '{diagnosis}' with "
                    f"GVF={gvf:.3f}. Manual break specification required. "
                    f"Returning best-effort map with diagnostic overlay."
                ),
                profile=profile,
            )
        else:
            # PATCH: when the diagnosis is well_behaved but the proposed breaks
            # were absent or below threshold, prescription dict is empty.
            # Synthesise a default quantile recommendation so the LLM always
            # receives an actionable instruction.
            method = prescribed["method"]
            breaks = prescribed.get("breaks")
            instruction = prescribed["instruction"]
            code_snippet = prescribed.get("code_snippet")

            # LIVELOCK GUARD (found 2026-08-11 on real Atlanta population
            # density, skew 5.95). If the caller already supplied exactly
            # what we are about to prescribe, prescribing it again cannot
            # change anything: the next iteration recomputes the identical
            # GVF and lands here again. The loop then runs until the
            # orchestrator's iteration cap and escalates to a human, even
            # though the classification on the table is the best this gate
            # knows how to produce.
            #
            # The pre-existing `iteration_count >= MAX_ITERATIONS` hatch
            # above cannot catch this: Orchestrator._run_gate_suite builds a
            # FRESH engine per iteration (TD-10), so iteration_count is
            # always 1 there. A counter-based guard only works for a caller
            # that reuses one engine; this check is stateless and therefore
            # holds for both callers.
            #
            # Concrete case: density diagnoses heavy_right_skew, the
            # prescribed log1p transform genuinely works (skew 5.95 ->
            # -0.03), but the resulting Jenks classification scores
            # GVF=0.5991 against a 0.60 floor. The remedy is correct and
            # simply cannot clear the bar on this distribution.
            if method is not None and _same_prescription(
                proposed_method, proposed_breaks, method, breaks
            ):
                return DiagnosticResult(
                    diagnosis=diagnosis,
                    gvf=gvf,
                    passed=True,
                    best_effort=True,
                    prescribed_method=method,
                    prescribed_breaks=breaks,
                    instruction=(
                        f"Best achievable classification for this distribution: "
                        f"'{method}' yields GVF={gvf:.4f}, below the "
                        f"{self.GVF_THRESHOLD} target. This IS the gate's own "
                        f"prescription, so no further correction exists -- "
                        f"proceeding with the shortfall recorded rather than "
                        f"rejecting a remedy the gate itself mandated."
                    ),
                    profile=profile,
                )

            if method is None:
                quantile_breaks = [float(np.percentile(values, p)) for p in (0, 20, 40, 60, 80, 100)]
                quantile_breaks = _dedupe_breaks(quantile_breaks)
                method = "quantile"
                breaks = quantile_breaks
                instruction = (
                    f"Proposed classification fails GVF (GVF={gvf:.3f} < "
                    f"{self.GVF_THRESHOLD}). Fall back to quantile breaks: {quantile_breaks}"
                )

            return DiagnosticResult(
                diagnosis=diagnosis,
                gvf=gvf,
                passed=False,
                prescribed_method=method,
                prescribed_breaks=breaks,
                instruction=instruction,
                code_snippet=code_snippet,
                profile=profile,
            )

    def _diagnose(self, profile: DistributionProfile) -> str:
        """Classify the distribution pattern."""
        if profile.n_unique <= self.DISCRETE_THRESHOLD:
            return "discrete_ordinal"
        if profile.zero_fraction >= self.ZERO_INFLATION_THRESHOLD:
            return "zero_inflated"
        if profile.outlier_fraction >= self.OUTLIER_THRESHOLD:
            return "outlier_dominated"
        if profile.skewness > 1.5 and profile.shapiro_p < 0.01:
            return "heavy_right_skew"
        if profile.std < 1e-10:
            return "insufficient_variance"
        return "well_behaved"

    def _get_prescription(
        self,
        diagnosis: str,
        profile: DistributionProfile,
        values: np.ndarray,
    ) -> Dict[str, Any]:
        """Generate mandatory prescription based on diagnosis.

        Dispatch is lazy: only the prescription for the actual diagnosis is
        computed. The prior eager-dict form evaluated every branch, so a
        low-cardinality input diagnosed as ``discrete_ordinal`` would still
        crash inside ``_prescribe_zero_inflated`` (Fisher-Jenks needs enough
        unique values in the tail). Lazy dispatch also avoids the wasted work.
        """
        dispatch = {
            "zero_inflated": self._prescribe_zero_inflated,
            "heavy_right_skew": self._prescribe_log_transform,
            "outlier_dominated": self._prescribe_head_tail,
            "discrete_ordinal": self._prescribe_unique_values,
            "insufficient_variance": self._prescribe_constant,
        }
        prescribe = dispatch.get(diagnosis)
        if prescribe is None:  # well_behaved (or any unmapped diagnosis)
            return {"method": None, "breaks": None, "instruction": None}
        return prescribe(values)

    def _prescribe_zero_inflated(self, values: np.ndarray) -> Dict[str, Any]:
        """Mandate manual break at zero with Fisher-Jenks for non-zero tail."""
        non_zero = values[values > 0]
        # Fisher-Jenks requires at least n_classes distinct values; guard on the
        # unique count, not just the length, or a low-cardinality tail raises.
        if np.unique(non_zero).size < 4 or not HAS_JENKSPY:
            # PATCH: dedupe breaks; >40% zeros means median may also be 0.
            breaks_raw = [0.0, float(np.percentile(values, 50)), float(np.percentile(values, 90)), float(values.max())]
            breaks = _dedupe_breaks(breaks_raw)
        else:
            tail_breaks = jenkspy.jenks_breaks(list(non_zero), n_classes=3)
            breaks = _dedupe_breaks([0.0] + [float(b) for b in tail_breaks[1:]])

        zero_pct = (values == 0).mean() * 100
        return {
            "method": "manual_break_at_zero_then_fisher_jenks",
            "breaks": [float(b) for b in breaks],
            "instruction": (
                f"Data is zero-inflated ({zero_pct:.1f}% zeros). "
                f"Mandate explicit break at 0, followed by Fisher-Jenks "
                f"classification for non-zero values. "
                f"DO NOT propose alternative methods. Use these exact breaks: {_fmt_breaks(breaks)}"
            ),
            "code_snippet": f"""
# MANDATED CLASSIFICATION - DO NOT MODIFY
import numpy as np
breaks = {breaks}
labels = ['No cases'] + [f'{{breaks[i]:.1f}}-{{breaks[i+1]:.1f}}' for i in range(1, len(breaks)-1)]
classified = np.digitize(values, bins=breaks, right=True)
""",
        }

    def _prescribe_log_transform(self, values: np.ndarray) -> Dict[str, Any]:
        """Mandate a monotone transform + Jenks for right-skewed distributions.

        PATCH (reviewer issue 2): the original code applied ``np.maximum(values, 0)``
        before log1p, silently clamping every negative value to zero. For variables
        such as population change or net migration, this fabricates a zero-inflated
        distribution that Gate 2 will then *mis-diagnose*.

        Decision tree:
        - Any negative values present → mandate arcsinh (Inverse Hyperbolic Sine),
          which is defined for all reals and behaves like log for large |x|.
        - All values >= 0 → log1p (origin-preserving, exact at 0).
        """
        has_negatives = float(np.min(values)) < 0

        if has_negatives:
            # arcsinh is mathematically valid for all reals. Back-transform via sinh.
            transformed = np.arcsinh(values)
            if HAS_JENKSPY and np.unique(transformed).size >= 6:
                breaks_t = jenkspy.jenks_breaks(list(transformed), n_classes=5)
                breaks_original = _dedupe_breaks([float(np.sinh(b)) for b in breaks_t])
            else:
                breaks_original = _dedupe_breaks(
                    [float(np.percentile(values, p)) for p in [0, 20, 40, 60, 80, 100]]
                )
            breaks_t_list = [float(np.arcsinh(b)) for b in breaks_original]
            return {
                "method": "arcsinh_transform_then_jenks",
                "breaks": breaks_original,
                "instruction": (
                    f"Data contains negative values (min={float(np.min(values)):.2f}) and is "
                    f"right-skewed (g1={float(scipy_stats.skew(values)):.2f}). "
                    f"Log transform is INVALID for negative inputs. "
                    f"Mandate Inverse Hyperbolic Sine (arcsinh) transform, which handles "
                    f"negative, zero, and positive values symmetrically. "
                    f"Use these exact back-transformed breaks: {_fmt_breaks(breaks_original)}"
                ),
                "code_snippet": f"""
# MANDATED CLASSIFICATION - DO NOT MODIFY
import numpy as np
transformed = np.arcsinh(values)
breaks_transformed = {breaks_t_list}
classified = np.digitize(transformed, bins=breaks_transformed, right=True)
""",
            }
        else:
            # All values non-negative: log1p is safe and origin-preserving.
            transformed = np.log1p(values)
            if HAS_JENKSPY and np.unique(transformed).size >= 6:
                breaks_t = jenkspy.jenks_breaks(list(transformed), n_classes=5)
                breaks_original = _dedupe_breaks([float(np.expm1(b)) for b in breaks_t])
            else:
                breaks_original = _dedupe_breaks(
                    [float(np.percentile(values, p)) for p in [0, 20, 40, 60, 80, 100]]
                )
            breaks_t_list = [float(np.log1p(b)) for b in breaks_original]
            return {
                "method": "log_transform_then_jenks",
                "breaks": breaks_original,
                "instruction": (
                    f"Data is heavily right-skewed (g1={float(scipy_stats.skew(values)):.2f}). "
                    f"Apply log1p transform before classification. "
                    f"Use these exact back-transformed breaks: {_fmt_breaks(breaks_original)}"
                ),
                "code_snippet": f"""
# MANDATED CLASSIFICATION - DO NOT MODIFY
import numpy as np
transformed = np.log1p(values)  # values confirmed >= 0 by Gate 2
breaks_transformed = {breaks_t_list}
classified = np.digitize(transformed, bins=breaks_transformed, right=True)
""",
            }

    def _prescribe_head_tail(self, values: np.ndarray) -> Dict[str, Any]:
        """Mandate head-tail breaks for heavy-tailed distributions."""
        breaks = self._compute_head_tail_breaks(values)
        outlier_pct = DistributionProfile.from_array(values, random_state=self.random_state).outlier_fraction * 100
        return {
            "method": "head_tail_breaks",
            "breaks": [float(b) for b in breaks],
            "instruction": (
                f"Distribution has {outlier_pct:.1f}% outliers. "
                f"Head-tail breaks are designed for heavy-tailed data. "
                f"Use these breaks: {_fmt_breaks(breaks)}"
            ),
            "code_snippet": f"""
# MANDATED CLASSIFICATION - DO NOT MODIFY
breaks = {breaks}
classified = np.digitize(values, bins=breaks, right=True)
""",
        }

    def _prescribe_unique_values(self, values: np.ndarray) -> Dict[str, Any]:
        """Mandate unique-value classification for discrete/ordinal data."""
        # PATCH: drop NaN/Inf before unique(); the original ``> -inf`` filter
        # silently kept NaNs as a spurious class because NaN comparisons are False.
        finite = values[np.isfinite(values)]
        unique = sorted(np.unique(finite).tolist())
        return {
            "method": "unique_values",
            "breaks": [float(u) for u in unique],
            "instruction": (
                f"Variable is discrete ordinal with {len(unique)} unique values. "
                f"Use unique-value classification. Do not apply continuous breaks."
            ),
            "code_snippet": f"""
# MANDATED CLASSIFICATION - DO NOT MODIFY
unique_values = {unique}
""",
        }

    def _prescribe_constant(self, values: np.ndarray) -> Dict[str, Any]:
        """Handle near-constant variable."""
        return {
            "method": "single_class",
            "breaks": [float(values.min()), float(values.max())],
            "instruction": (
                "Variable exhibits negligible variance. Map as single-class "
                "with annotation explaining near-constant spatial distribution."
            ),
        }

    @staticmethod
    def _compute_gvf(values: np.ndarray, breaks: List[float]) -> float:
        """Goodness of Variance Fit for a classification scheme.

        GVF = 1 - (sum of within-class variances) / (total variance)

        GVF > 0.8: Excellent fit
        GVF 0.6-0.8: Acceptable
        GVF < 0.6: Poor fit - reject
        """
        total_var = np.var(values)
        if total_var == 0:
            return 1.0

        # PATCH: deduplicate and clip user-supplied breaks before digitize so
        # accidental duplicates do not produce empty classes.
        bins = _dedupe_breaks(sorted(float(b) for b in breaks))
        if len(bins) < 2:
            return 0.0
        classes = np.digitize(values, bins=bins, right=True)
        within_var = 0.0
        for c in np.unique(classes):
            mask = classes == c
            if mask.sum() > 1:
                within_var += mask.sum() * np.var(values[mask])

        return 1.0 - (within_var / (len(values) * total_var))

    @staticmethod
    def _compute_head_tail_breaks(values: np.ndarray) -> List[float]:
        """Compute head-tail breaks for heavy-tailed distributions."""
        data = np.sort(values[values > 0])
        if len(data) < 4:
            return [float(np.min(values)), float(np.max(values))]

        breaks = [float(np.min(data))]
        remaining = data
        # PATCH: explicit iteration cap to avoid pathological loops on
        # adversarial input shapes (e.g. exponentially tied values).
        for _ in range(64):
            if len(remaining) <= 1:
                break
            mean_val = float(np.mean(remaining))
            head = remaining[remaining > mean_val]
            if len(head) == 0 or len(head) == len(remaining):
                breaks.append(float(np.max(remaining)))
                break
            breaks.append(mean_val)
            remaining = head

        if breaks[-1] != float(np.max(values)):
            breaks.append(float(np.max(values)))
        return _dedupe_breaks(sorted(set(breaks)))

    def reset(self):
        """Reset iteration counter for new evaluation."""
        self.iteration_count = 0


# Standalone diagnostic function for use in other gates
def characterize_distribution(values: np.ndarray, random_state: int = 0) -> DistributionProfile:
    """Quick distribution profile without the full diagnostic pipeline."""
    return DistributionProfile.from_array(values, random_state=random_state)
