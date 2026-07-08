"""Gate 3b: Bivariate Spatial Cross-Correlation.

Activated exclusively for bivariate map proposals. Prevents the generation
of cognitively overloaded bivariate maps when the two variables lack
meaningful spatial cross-correlation.

Decision matrix:
    |I_xy| > 0.15 AND |rho| > 0.20 -> APPROVE
    |I_xy| > 0.08 AND |rho| > 0.10 -> WARN (proceed with annotation)
    Otherwise                       -> REJECT (force side-by-side univariate)
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

    # PATCH: permutation parameters; abstract claims significance testing on I_xy.
    DEFAULT_PERMUTATIONS = 199
    DEFAULT_SEED = 0

    def evaluate(
        self,
        x: np.ndarray,
        y: np.ndarray,
        weights_matrix: np.ndarray,
        standardized: bool = False,
        permutations: int = DEFAULT_PERMUTATIONS,
        random_state: int = DEFAULT_SEED,
    ) -> BivariateCorrelationResult:
        """Full bivariate spatial cross-correlation evaluation.

        Args:
            x: First variable (1D array)
            y: Second variable (1D array)
            weights_matrix: Spatial weights (N x N, ideally row-standardized)
            standardized: True if x and y are already z-scored
            permutations: Number of random permutations for I_xy significance
            random_state: Seed controlling the permutation generator

        Returns:
            BivariateCorrelationResult with decision and instructions
        """
        # PATCH: defensive coercion. NumPy scalars caused json.dumps to fail
        # downstream because numpy.float64 is not JSON-serialisable.
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        W = np.asarray(weights_matrix, dtype=float)

        # PATCH (reviewer issue 4): enforce strict row-standardisation.
        # The bivariate Moran's I formula I_xy = (N/W_sum) * (z' W z) / sqrt(...)
        # produces inflated or deflated statistics when W is a raw contiguity
        # matrix (row sums equal the neighbour count, typically 4-8 for a grid)
        # or a distance-decay matrix with arbitrary row sums. The upstream Compute
        # Router or caller MUST row-standardise before calling Gate 3b.
        #
        # We check with a tight tolerance and raise immediately so the error
        # surfaces at integration time rather than silently corrupting the
        # significance decision. Use W / W.sum(axis=1, keepdims=True) to fix.
        row_sums = W.sum(axis=1)
        if W.shape[0] > 0 and not np.allclose(row_sums, 1.0, atol=1e-6):
            bad_min, bad_max = float(row_sums.min()), float(row_sums.max())
            raise ValueError(
                f"Gate 3b requires a row-standardized weights matrix "
                f"(every row sum must equal 1.0 ± 1e-6). "
                f"Received row sums in [{bad_min:.4f}, {bad_max:.4f}]. "
                f"Fix: W_std = W / W.sum(axis=1, keepdims=True)"
            )

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

        # PATCH: standardise defensively to avoid division-by-zero when a
        # variable is constant. ``np.std`` of a constant is zero; guard with
        # an epsilon-fallback that yields zeroed z-scores and a clean reject.
        def _zscore(v: np.ndarray) -> Optional[np.ndarray]:
            mu = float(np.mean(v))
            sigma = float(np.std(v))
            if sigma < 1e-12:
                return None
            return (v - mu) / sigma

        if not standardized:
            x_std = _zscore(x_clean)
            y_std = _zscore(y_clean)
            if x_std is None or y_std is None:
                return BivariateCorrelationResult(
                    bivariate_morans_i=0.0, bivariate_morans_p=1.0,
                    spearman_rho=0.0, spearman_p=1.0,
                    decision="REJECT",
                    instruction="At least one variable is constant; cross-correlation is undefined.",
                )
        else:
            x_std = x_clean
            y_std = y_clean

        # Subset weights matrix to valid observations
        valid_indices = np.where(mask)[0]
        W_sub = W[np.ix_(valid_indices, valid_indices)]

        # Bivariate Moran's I
        # I_xy = (N / W_sum) * (z_x' W z_y) / sqrt((z_x' z_x) * (z_y' z_y))
        N = len(x_std)
        W_sum = float(np.sum(W_sub))
        if W_sum == 0:
            return BivariateCorrelationResult(
                bivariate_morans_i=0.0, bivariate_morans_p=1.0,
                spearman_rho=0.0, spearman_p=1.0,
                decision="REJECT",
                instruction="Weights matrix has zero sum; spatial structure undetectable.",
            )

        I_xy = self._bivariate_morans_i(x_std, y_std, W_sub, N, W_sum)

        # PATCH: actual permutation-based p-value. The abstract claims Gate 3b
        # "calculates bivariate Moran's I"; reporting p=0.0 is misleading.
        # We permute the y vector under the null of no spatial cross-association.
        p_value = self._permutation_pvalue(
            x_std, y_std, W_sub, I_xy, N, W_sum, permutations, random_state
        )

        # Spearman's rank correlation
        rho, spearman_p = spearmanr(x_clean, y_clean)

        # Decision logic
        decision, instruction = self._decide(I_xy, float(rho))

        return BivariateCorrelationResult(
            bivariate_morans_i=float(I_xy),
            bivariate_morans_p=float(p_value),
            spearman_rho=float(rho),
            spearman_p=float(spearman_p),
            decision=decision,
            instruction=instruction,
        )

    @staticmethod
    def _bivariate_morans_i(
        x_std: np.ndarray,
        y_std: np.ndarray,
        W: np.ndarray,
        N: int,
        W_sum: float,
    ) -> float:
        numerator = float(x_std @ W @ y_std)
        denominator = float(np.sqrt((x_std @ x_std) * (y_std @ y_std)))
        if denominator == 0:
            return 0.0
        return (N / W_sum) * (numerator / denominator)

    @classmethod
    def _permutation_pvalue(
        cls,
        x_std: np.ndarray,
        y_std: np.ndarray,
        W: np.ndarray,
        observed: float,
        N: int,
        W_sum: float,
        permutations: int,
        random_state: int,
    ) -> float:
        """Two-sided permutation p-value via random reshuffling of y_std."""
        if permutations <= 0:
            return 1.0
        rng = np.random.default_rng(random_state)
        observed_abs = abs(observed)
        count = 0
        y_perm = y_std.copy()
        for _ in range(permutations):
            rng.shuffle(y_perm)
            stat = cls._bivariate_morans_i(x_std, y_perm, W, N, W_sum)
            if abs(stat) >= observed_abs:
                count += 1
        # Pseudo p-value: (M+1) / (R+1)
        return (count + 1) / (permutations + 1)

    def _decide(self, I_xy: float, rho: float) -> tuple:
        """Apply the three-tier decision matrix."""
        abs_I = abs(I_xy)
        abs_rho = abs(rho)

        if abs_I > self.APPROVE_I_THRESHOLD and abs_rho > self.APPROVE_RHO_THRESHOLD:
            return "APPROVE", (
                f"Variables exhibit sufficient spatial cross-correlation "
                f"(I_xy={I_xy:.3f}, rho={rho:.3f}) to justify bivariate representation."
            )
        elif abs_I > self.WARN_I_THRESHOLD and abs_rho > self.WARN_RHO_THRESHOLD:
            return "WARN", (
                f"Weak spatial cross-correlation detected "
                f"(I_xy={I_xy:.3f}, rho={rho:.3f}). "
                f"Bivariate map approved with mandatory interpretive annotation. "
                f"Class outlines and correlation statistic must be displayed."
            )
        else:
            return "REJECT", (
                f"Variables exhibit no meaningful spatial cross-correlation "
                f"(I_xy={I_xy:.3f}, rho={rho:.3f}). "
                f"MANDATED ALTERNATIVE: Generate side-by-side univariate "
                f"choropleth maps. Do not produce a bivariate map."
            )
