"""Gate 3b: Bivariate Spatial Cross-Correlation.

Activated exclusively for bivariate map proposals. Prevents the generation
of cognitively overloaded bivariate maps when the two variables lack
meaningful spatial cross-correlation.

Decision matrix:
    |I_xy| > 0.15 AND |ρ| > 0.20 → APPROVE
    |I_xy| > 0.08 AND |ρ| > 0.10 → WARN (proceed with annotation)
    Otherwise → REJECT (force side-by-side univariate)
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, Literal
import numpy as np
from scipy.stats import spearmanr


@dataclass
class BivariateCorrelationResult:
    """Complete bivariate correlation assessment."""
    bivariate_morans_i: float
    bivariate_morans_p: float
    spearman_rho: float
    spearman_p: float
    decision: Literal["APPROVE", "WARN", "REJECT"]
    instruction: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": "G3b",
            "bivariate_morans_i": round(self.bivariate_morans_i, 4),
            "bivariate_morans_p": round(self.bivariate_morans_p, 4),
            "spearman_rho": round(self.spearman_rho, 4),
            "spearman_p": round(self.spearman_p, 4),
            "decision": self.decision,
            "instruction": self.instruction,
        }


class BivariateCorrelationGate:
    """Validates spatial cross-correlation for bivariate map proposals."""

    # Thresholds calibrated for typical census-tract-scale social/environmental data
    APPROVE_I_THRESHOLD = 0.15
    APPROVE_RHO_THRESHOLD = 0.20
    WARN_I_THRESHOLD = 0.08
    WARN_RHO_THRESHOLD = 0.10

    def evaluate(
        self,
        x: np.ndarray,
        y: np.ndarray,
        weights_matrix: np.ndarray,
        standardized: bool = True,
    ) -> BivariateCorrelationResult:
        """Full bivariate spatial cross-correlation evaluation.

        Args:
            x: First variable (1D array)
            y: Second variable (1D array)
            weights_matrix: Spatial weights (N × N, row-standardized)
            standardized: Whether x and y are already z-scored

        Returns:
            BivariateCorrelationResult with decision and instructions
        """
        # Clean data: remove NaNs and infinities from both arrays
        mask = np.isfinite(x) & np.isfinite(y)
        x_clean = x[mask]
        y_clean = y[mask]

        if len(x_clean) < 20:
            return BivariateCorrelationResult(
                bivariate_morans_i=0.0,
                bivariate_morans_p=1.0,
                spearman_rho=0.0,
                spearman_p=1.0,
                decision="REJECT",
                instruction="Insufficient valid observations for bivariate correlation assessment.",
            )

        # Standardize if needed
        if not standardized:
            x_std = (x_clean - np.mean(x_clean)) / np.std(x_clean)
            y_std = (y_clean - np.mean(y_clean)) / np.std(y_clean)
        else:
            x_std = x_clean
            y_std = y_clean

        # Subset weights matrix to valid observations
        valid_indices = np.where(mask)[0]
        W = weights_matrix[np.ix_(valid_indices, valid_indices)]

        # Bivariate Moran's I
        # I_xy = (N / W_sum) * (z_x' W z_y) / sqrt((z_x' z_x) * (z_y' z_y))
        N = len(x_std)
        W_sum = np.sum(W)
        if W_sum == 0:
            return BivariateCorrelationResult(
                bivariate_morans_i=0.0, bivariate_morans_p=1.0,
                spearman_rho=0.0, spearman_p=1.0,
                decision="REJECT",
                instruction="Weights matrix has zero sum; spatial structure undetectable.",
            )

        numerator = x_std @ W @ y_std
        denominator = np.sqrt((x_std @ x_std) * (y_std @ y_std))
        if denominator == 0:
            I_xy = 0.0
        else:
            I_xy = (N / W_sum) * (numerator / denominator)

        # Spearman's rank correlation
        rho, spearman_p = spearmanr(x_clean, y_clean)

        # Decision logic
        decision, instruction = self._decide(I_xy, rho)

        return BivariateCorrelationResult(
            bivariate_morans_i=float(I_xy),
            bivariate_morans_p=0.0,  # Permutation test omitted for brevity
            spearman_rho=float(rho),
            spearman_p=float(spearman_p),
            decision=decision,
            instruction=instruction,
        )

    def _decide(self, I_xy: float, rho: float) -> tuple:
        """Apply the three-tier decision matrix."""
        abs_I = abs(I_xy)
        abs_rho = abs(rho)

        if abs_I > self.APPROVE_I_THRESHOLD and abs_rho > self.APPROVE_RHO_THRESHOLD:
            return "APPROVE", (
                f"Variables exhibit sufficient spatial cross-correlation "
                f"(I_xy={I_xy:.3f}, ρ={rho:.3f}) to justify bivariate representation."
            )
        elif abs_I > self.WARN_I_THRESHOLD and abs_rho > self.WARN_RHO_THRESHOLD:
            return "WARN", (
                f"Weak spatial cross-correlation detected "
                f"(I_xy={I_xy:.3f}, ρ={rho:.3f}). "
                f"Bivariate map approved with mandatory interpretive annotation. "
                f"Class outlines and correlation statistic must be displayed."
            )
        else:
            return "REJECT", (
                f"Variables exhibit no meaningful spatial cross-correlation "
                f"(I_xy={I_xy:.3f}, ρ={rho:.3f}). "
                f"MANDATED ALTERNATIVE: Generate side-by-side univariate "
                f"choropleth maps. Do not produce a bivariate map."
            )