"""Gate 3a: Univariate Spatial Structure (global Moran's I).

A choropleth's entire message is its spatial pattern. If a variable has no
detectable spatial autocorrelation, a choropleth of it is visual noise
dressed as a map — the reader will perceive clusters that are not there
(the eye is a very good, very wrong spatial-pattern detector). Gate 3a
rejects that proposal and prescribes a non-spatial encoding instead
(proportional symbol / dot density), which does not imply false structure.

Formula (identical in spirit to Gate 3b's bivariate statistic, y := x):

    I = (N / W_sum) * (z' W z) / (z' z),   z = x - mean(x)

Significance is assessed by conditional permutation (shuffle the attribute
vector, hold W fixed, recompute I) with a seeded generator — the same
pattern as ``gate3b_bivariate_correlation._permutation_pvalue``, kept
independent here rather than imported so this gate has no runtime
dependency on Gate 3b's module.

Negative autocorrelation (checkerboard/dispersion) is real spatial
structure, not noise, so the significance test is two-sided and the
decision rule keys on |I|, not sign — a strongly dispersed pattern PASSES
just as a strongly clustered one does; only weak-or-nonsignificant |I|
(near the -1/(N-1) value expected under complete spatial randomness)
rejects.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from autocarto.config import THRESHOLDS
from autocarto.contracts import GateResult, Prescription


class SpatialStructureGate:
    """Gate 3a: rejects choropleth proposals lacking spatial structure."""

    def evaluate(
        self,
        values: np.ndarray,
        weights_matrix: np.ndarray,
        permutations: int = THRESHOLDS.gate3a.permutations,
        random_state: int = 0,
    ) -> GateResult:
        x = np.asarray(values, dtype=float)
        W = np.asarray(weights_matrix, dtype=float)

        row_sums = W.sum(axis=1)
        if W.shape[0] > 0 and not np.allclose(row_sums, 1.0, atol=1e-6):
            bad_min, bad_max = float(row_sums.min()), float(row_sums.max())
            raise ValueError(
                f"Gate 3a requires a row-standardized weights matrix "
                f"(every row sum must equal 1.0 +/- 1e-6). "
                f"Received row sums in [{bad_min:.4f}, {bad_max:.4f}]. "
                f"Fix: W_std = W / W.sum(axis=1, keepdims=True)"
            )

        mask = np.isfinite(x)
        x_clean = x[mask]
        diagnostics: Dict[str, Any] = {"n": int(len(x_clean))}

        if len(x_clean) < 20:
            return self._reject(
                diagnostics,
                morans_i=0.0, p_value=1.0,
                reason="Insufficient valid observations for spatial-structure assessment.",
            )

        valid_idx = np.where(mask)[0]
        W_sub = W[np.ix_(valid_idx, valid_idx)]
        N = len(x_clean)
        W_sum = float(np.sum(W_sub))

        z = x_clean - float(np.mean(x_clean))
        zz = float(z @ z)

        if W_sum == 0 or zz < 1e-12:
            return self._reject(
                diagnostics,
                morans_i=0.0, p_value=1.0,
                reason="Zero-sum weights matrix or constant variable; spatial structure undefined.",
            )

        I = self._morans_i(z, W_sub, N, W_sum)
        p_value = self._permutation_pvalue(z, W_sub, I, N, W_sum, permutations, random_state)
        expected_i = -1.0 / (N - 1)

        diagnostics.update({
            "morans_i": round(I, 4),
            "expected_i": round(expected_i, 4),
            "p_value": round(p_value, 4),
            "pattern": "clustered_positive" if I > 0 else ("dispersed_negative" if I < 0 else "random"),
        })

        significant = p_value < THRESHOLDS.gate3a.significance_alpha
        weak = abs(I) < THRESHOLDS.gate3a.reject_below_abs_i

        if weak or not significant:
            return self._reject(
                diagnostics,
                morans_i=I, p_value=p_value,
                reason=(
                    f"No statistically meaningful spatial structure detected "
                    f"(I={I:.3f}, p={p_value:.4f}, threshold |I|>"
                    f"{THRESHOLDS.gate3a.reject_below_abs_i}). A choropleth's message "
                    f"is its spatial pattern; without one, the map implies clusters "
                    f"that are not statistically present."
                ),
            )

        note = ""
        if I < 0:
            note = (
                " Pattern is a statistically significant DISPERSED (checkerboard-like) "
                "arrangement, not clustering — this is real spatial structure and the "
                "choropleth is justified; consider noting the dispersion in the legend."
            )
        return GateResult(
            gate_id="G3a",
            decision="PASS",
            diagnostics=diagnostics,
            instruction=(
                f"Spatial structure confirmed (I={I:.3f}, p={p_value:.4f})."
                f"{note}"
            ),
        )

    def _reject(self, diagnostics: Dict[str, Any], *, morans_i: float, p_value: float, reason: str) -> GateResult:
        diagnostics = {**diagnostics, "morans_i": round(morans_i, 4), "p_value": round(p_value, 4)}
        return GateResult(
            gate_id="G3a",
            decision="REJECT",
            diagnostics=diagnostics,
            instruction=reason,
            prescription=Prescription(
                method="proportional_symbol",
                instruction=(
                    f"{reason} MANDATED ALTERNATIVE: encode this variable with "
                    f"proportional symbols (or dot density) at feature centroids "
                    f"rather than a choropleth fill — this does not visually imply "
                    f"spatial clustering the data does not support."
                ),
                params={"morans_i": morans_i, "p_value": p_value},
            ),
        )

    @staticmethod
    def _morans_i(z: np.ndarray, W: np.ndarray, N: int, W_sum: float) -> float:
        numerator = float(z @ W @ z)
        denominator = float(z @ z)
        if denominator == 0:
            return 0.0
        return (N / W_sum) * (numerator / denominator)

    @classmethod
    def _permutation_pvalue(
        cls, z: np.ndarray, W: np.ndarray, observed: float, N: int, W_sum: float,
        permutations: int, random_state: int,
    ) -> float:
        """Two-sided conditional-permutation p-value (attribute shuffled, W fixed)."""
        if permutations <= 0:
            return 1.0
        rng = np.random.default_rng(random_state)
        observed_abs = abs(observed)
        count = 0
        z_perm = z.copy()
        for _ in range(permutations):
            rng.shuffle(z_perm)
            stat = cls._morans_i(z_perm, W, N, W_sum)
            if abs(stat) >= observed_abs:
                count += 1
        return (count + 1) / (permutations + 1)
