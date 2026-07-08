"""Gate 2: Classification Validity — Diagnostic Mode, Not Binary Gate.

This is the core intellectual contribution of AutoCarto-Agent.
The gate characterizes the distribution shape, computes Goodness of
Variance Fit, and issues prescriptive remedies with mandated break points.
The LLM is forced into a code-assembler role.

Diagnostic → Prescriptive Rejection Pipeline:
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
    def from_array(cls, x: np.ndarray) -> "DistributionProfile":
        """Compute full distribution profile from a 1D array."""
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

        # Shapiro-Wilk on sample (max 5000 for performance)
        sample = x_clean if n <= 5000 else np.random.choice(x_clean, 5000, replace=False)

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
            shapiro_w=float(scipy_stats.shapiro(sample).statistic),
            shapiro_p=float(scipy_stats.shapiro(sample).pvalue),
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

    def to_dict(self) -> Dict[str, Any]:
        """Serializable dict for execution trace JSON."""
        return {
            "gate": "G2",
            "diagnosis": self.diagnosis,
            "gvf": round(self.gvf, 4),
            "passed": self.passed,
            "prescribed_method": self.prescribed_method,
            "prescribed_breaks": self.prescribed_breaks,
            "instruction": self.instruction,
        }


class ClassificationDiagnosticEngine:
    """Characterizes distribution and prescribes classification remedies.

    This engine operates on a strict diagnostic → prescriptive pipeline.
    It never asks the LLM to "consider" alternatives; it mandates the
    exact method and break points required.
    """

    GVF_THRESHOLD = 0.6           # Minimum acceptable GVF
    ZERO_INFLATION_THRESHOLD = 0.40  # Fraction of zeros triggering zero-inflation
    OUTLIER_THRESHOLD = 0.10       # Fraction of outliers triggering head-tail
    DISCRETE_THRESHOLD = 10        # Max unique values for discrete ordinal
    MAX_ITERATIONS = 3

    def __init__(self):
        self.iteration_count = 0

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
        profile = DistributionProfile.from_array(values)

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
        if diagnosis == "well_behaved" and gvf >= self.GVF_THRESHOLD:
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
            return DiagnosticResult(
                diagnosis=diagnosis,
                gvf=gvf,
                passed=False,
                prescribed_method=prescribed["method"],
                prescribed_breaks=prescribed.get("breaks"),
                instruction=prescribed["instruction"],
                code_snippet=prescribed.get("code_snippet"),
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
        """Generate mandatory prescription based on diagnosis."""
        prescriptions = {
            "zero_inflated": self._prescribe_zero_inflated(values),
            "heavy_right_skew": self._prescribe_log_transform(values),
            "outlier_dominated": self._prescribe_head_tail(values),
            "discrete_ordinal": self._prescribe_unique_values(values),
            "insufficient_variance": self._prescribe_constant(values),
            "well_behaved": {"method": None, "breaks": None, "instruction": None},
        }
        return prescriptions.get(diagnosis, prescriptions["well_behaved"])

    def _prescribe_zero_inflated(self, values: np.ndarray) -> Dict[str, Any]:
        """Mandate manual break at zero with Fisher-Jenks for non-zero tail."""
        non_zero = values[values > 0]
        if len(non_zero) < 3 or not HAS_JENKSPY:
            breaks = [0.0, np.percentile(values, 50), np.percentile(values, 90), values.max()]
        else:
            tail_breaks = jenkspy.jenks_breaks(list(non_zero), n_classes=3)
            breaks = [0.0] + list(tail_breaks[1:])

        zero_pct = (values == 0).mean() * 100
        return {
            "method": "manual_break_at_zero_then_fisher_jenks",
            "breaks": [float(b) for b in breaks],
            "instruction": (
                f"Data is zero-inflated ({zero_pct:.1f}% zeros). "
                f"Mandate explicit break at 0, followed by Fisher-Jenks "
                f"classification for non-zero values. "
                f"DO NOT propose alternative methods. Use these exact breaks: {breaks}"
            ),
            "code_snippet": f"""
# MANDATED CLASSIFICATION — DO NOT MODIFY
import numpy as np
breaks = {breaks}
labels = ['No cases'] + [f'{{breaks[i]:.1f}}–{{breaks[i+1]:.1f}}' for i in range(1, len(breaks)-1)]
classified = np.digitize(values, bins=breaks, right=True)
""",
        }

    def _prescribe_log_transform(self, values: np.ndarray) -> Dict[str, Any]:
        """Mandate log1p transform before Jenks classification."""
        transformed = np.log1p(values[values >= 0])
        if HAS_JENKSPY and len(transformed) >= 3:
            breaks_transformed = jenkspy.jenks_breaks(list(transformed), n_classes=5)
            breaks_original = [float(np.expm1(b)) for b in breaks_transformed]
        else:
            breaks_original = [float(np.percentile(values, p)) for p in [0, 20, 40, 60, 80, 100]]

        return {
            "method": "log_transform_then_jenks",
            "breaks": breaks_original,
            "instruction": (
                f"Data is heavily right-skewed (g1={scipy_stats.skew(values):.2f}). "
                f"Apply log1p transform before classification. "
                f"Use these exact back-transformed breaks: {breaks_original}"
            ),
            "code_snippet": f"""
# MANDATED CLASSIFICATION — DO NOT MODIFY
import numpy as np
transformed = np.log1p(np.maximum(values, 0))
breaks_transformed = {[float(np.log1p(max(b, 0))) for b in breaks_original]}
classified = np.digitize(transformed, bins=breaks_transformed, right=True)
""",
        }

    def _prescribe_head_tail(self, values: np.ndarray) -> Dict[str, Any]:
        """Mandate head-tail breaks for heavy-tailed distributions."""
        breaks = self._compute_head_tail_breaks(values)
        outlier_pct = DistributionProfile.from_array(values).outlier_fraction * 100
        return {
            "method": "head_tail_breaks",
            "breaks": [float(b) for b in breaks],
            "instruction": (
                f"Distribution has {outlier_pct:.1f}% outliers. "
                f"Head-tail breaks are designed for heavy-tailed data. "
                f"Use these breaks: {breaks}"
            ),
            "code_snippet": f"""
# MANDATED CLASSIFICATION — DO NOT MODIFY
breaks = {breaks}
classified = np.digitize(values, bins=breaks, right=True)
""",
        }

    def _prescribe_unique_values(self, values: np.ndarray) -> Dict[str, Any]:
        """Mandate unique-value classification for discrete/ordinal data."""
        unique = sorted(np.unique(values[values > -np.inf]))
        return {
            "method": "unique_values",
            "breaks": [float(u) for u in unique],
            "instruction": (
                f"Variable is discrete ordinal with {len(unique)} unique values. "
                f"Use unique-value classification. Do not apply continuous breaks."
            ),
            "code_snippet": f"""
# MANDATED CLASSIFICATION — DO NOT MODIFY
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
        GVF 0.6–0.8: Acceptable
        GVF < 0.6: Poor fit — reject
        """
        total_var = np.var(values)
        if total_var == 0:
            return 1.0

        classes = np.digitize(values, bins=breaks, right=True)
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
        while len(remaining) > 1:
            mean_val = np.mean(remaining)
            head = remaining[remaining > mean_val]
            if len(head) == 0 or len(head) == len(remaining):
                breaks.append(float(np.max(remaining)))
                break
            breaks.append(float(mean_val))
            remaining = head

        if breaks[-1] != float(np.max(values)):
            breaks.append(float(np.max(values)))
        return sorted(set(breaks))

    def reset(self):
        """Reset iteration counter for new evaluation."""
        self.iteration_count = 0


# Standalone diagnostic function for use in other gates
def characterize_distribution(values: np.ndarray) -> DistributionProfile:
    """Quick distribution profile without the full diagnostic pipeline."""
    return DistributionProfile.from_array(values)