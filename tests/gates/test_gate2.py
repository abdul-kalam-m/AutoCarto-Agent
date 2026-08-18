"""Gate 2 behavioral contracts.

Exact numeric regression lives in tests/test_determinism.py (golden traces);
these tests pin the *behavioral* spec from Fable Review/01_OPERATING_MANUAL.md
§4.1 so refactors cannot silently change diagnosis or prescription semantics.
"""

from __future__ import annotations

import numpy as np
import pytest

from autocarto.execution.gates.gate2_classification import (
    ClassificationDiagnosticEngine,
    DistributionProfile,
    _dedupe_breaks,
)


def _naive_breaks(values: np.ndarray) -> list[float]:
    return _dedupe_breaks(
        [float(np.percentile(values, p)) for p in (0, 20, 40, 60, 80, 100)]
    )


def _evaluate(values: np.ndarray):
    engine = ClassificationDiagnosticEngine(random_state=0)
    return engine.evaluate(values, proposed_method="jenks",
                           proposed_breaks=_naive_breaks(values))


# ── Diagnosis regimes (one per row of the Manual §4.1 table) ──────────────────

def test_well_behaved_passes():
    values = np.random.default_rng(1).normal(50, 12, 243).clip(0, 100)
    res = _evaluate(values)
    assert res.diagnosis == "well_behaved"
    assert res.passed is True
    assert res.gvf >= ClassificationDiagnosticEngine.GVF_THRESHOLD


def test_zero_inflated_rejected_with_break_at_zero():
    rng = np.random.default_rng(2)
    values = np.concatenate([np.zeros(121), rng.pareto(2.0, 122) * 5 + 1])
    rng.shuffle(values)
    res = _evaluate(values)
    assert res.diagnosis == "zero_inflated"
    assert res.passed is False
    assert res.prescribed_method == "manual_break_at_zero_then_fisher_jenks"
    assert res.prescribed_breaks[0] == 0.0


def test_heavy_right_skew_prescribes_log_jenks():
    values = np.random.default_rng(3).lognormal(10, 1.2, 243)
    res = _evaluate(values)
    assert res.diagnosis == "heavy_right_skew"
    assert res.prescribed_method == "log_transform_then_jenks"


def test_negative_support_prescribes_arcsinh_not_log():
    # Reviewer patch R2-1: log1p is invalid for negatives; arcsinh mandated.
    values = np.random.default_rng(99).chisquare(df=2, size=243) - 0.8
    assert values.min() < 0
    res = _evaluate(values)
    assert res.diagnosis == "heavy_right_skew"
    assert res.prescribed_method == "arcsinh_transform_then_jenks"
    assert "arcsinh" in res.instruction.lower()


def test_discrete_ordinal_prescribes_unique_values():
    values = np.random.default_rng(4).choice(
        [1, 2, 3, 4, 5], size=243, p=[0.3, 0.3, 0.2, 0.15, 0.05]
    ).astype(float)
    res = _evaluate(values)
    assert res.diagnosis == "discrete_ordinal"
    assert res.prescribed_method == "unique_values"
    assert res.prescribed_breaks == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_insufficient_variance_single_class():
    values = np.full(243, 7.0)
    values[0] = 7.0 + 1e-12
    res = _evaluate(values)
    assert res.diagnosis in {"insufficient_variance", "discrete_ordinal"}
    assert res.passed is False


# ── Diagnosis precedence (order is load-bearing — Manual §4.1) ────────────────

def test_zero_inflation_takes_precedence_over_skew():
    """A zero-inflated variable is also skewed; zero-inflation must win."""
    rng = np.random.default_rng(5)
    values = np.concatenate([np.zeros(150), rng.lognormal(10, 1.2, 93)])
    rng.shuffle(values)
    res = _evaluate(values)
    assert res.diagnosis == "zero_inflated"


def test_discrete_takes_precedence_over_zero_inflation():
    """≤10 unique values wins even when mostly zeros."""
    rng = np.random.default_rng(6)
    values = rng.choice([0.0, 1.0, 2.0], size=243, p=[0.6, 0.3, 0.1])
    res = _evaluate(values)
    assert res.diagnosis == "discrete_ordinal"


# ── Prescription usability invariants ─────────────────────────────────────────

@pytest.mark.parametrize("seed", [11, 12, 13])
def test_rejections_always_carry_actionable_prescription(seed):
    """REJECT ⇒ prescription present, breaks strictly monotonic, range-covering."""
    rng = np.random.default_rng(seed)
    values = rng.lognormal(9, 1.5, 300)
    res = _evaluate(values)
    if not res.passed:
        assert res.prescribed_method is not None
        assert res.instruction
        breaks = res.prescribed_breaks
        assert breaks is not None and len(breaks) >= 2
        assert all(b2 > b1 for b1, b2 in zip(breaks, breaks[1:])), "breaks not monotonic"


def test_gvf_prescribed_beats_naive_on_skewed_data():
    """The poster's classification-fit claim, as an invariant (0.75→0.83 class)."""
    values = np.random.default_rng(7).lognormal(10, 1.2, 500)
    res = _evaluate(values)
    presc = _dedupe_breaks([float(b) for b in res.prescribed_breaks])
    naive = _naive_breaks(values)
    gvf_presc = ClassificationDiagnosticEngine._compute_gvf(values, presc)
    gvf_naive = ClassificationDiagnosticEngine._compute_gvf(values, naive)
    assert gvf_presc > gvf_naive


# ── Prescription self-consistency (livelock guard) ────────────────────────────
#
# The invariant these pin is the same one tests/gates/test_gate5.py enforces
# for palettes: a gate must never reject a proposal that IS its own
# prescription. Gate 5 had that test; Gate 2 did not, and the gap was found
# on real Atlanta population density (n=519, skew 5.95), where the prescribed
# log1p transform genuinely works (skew -> -0.03) but the resulting Jenks
# classification scores GVF=0.5991 against a 0.60 floor. Gate 2 re-issued the
# identical prescription every iteration and the run never converged.


def _heavy_tailed_below_gvf_floor() -> np.ndarray:
    """A distribution whose own prescribed remedy still misses GVF_THRESHOLD.

    Reproduces the real population-density case. The prescribed breaks are
    optimal in log space but GVF is scored against the RAW values, where the
    surviving tail dominates the variance -- so a correct transform can still
    land under the floor (here GVF ~= 0.36 against a 0.60 target).

    Parameters found by sweeping sigma x seed and keeping a combination that
    actually reaches the best-effort branch; an arbitrary log-normal does not
    (most score GVF > 0.9 and pass cleanly, which is why the first version of
    this fixture silently skipped the test it was written to exercise).
    """
    return np.exp(np.random.default_rng(1).normal(3.0, 1.8, 520))


def test_gate2_does_not_reject_its_own_prescription():
    """Feeding Gate 2 exactly what it prescribed must not reject again.

    Without this guard the orchestrator loops to its iteration cap and
    escalates to a human, even though the classification on the table is the
    best the gate knows how to produce.
    """
    values = _heavy_tailed_below_gvf_floor()

    first = ClassificationDiagnosticEngine().evaluate(values, proposed_method="jenks")
    assert first.passed is False
    assert first.prescribed_method is not None

    # Transcribe the mandate exactly, as the LLM tier is required to do.
    second = ClassificationDiagnosticEngine().evaluate(
        values,
        proposed_method=first.prescribed_method,
        proposed_breaks=first.prescribed_breaks,
    )
    assert second.passed is True, (
        "Gate 2 rejected its own prescription -- this is the livelock: the "
        "next iteration would recompute the identical GVF and reject again."
    )


def test_best_effort_is_flagged_not_silently_passed():
    """A sub-threshold pass must be distinguishable from a clean pass.

    Passing silently would hide a real shortfall; the WARN tier exists to
    carry exactly this case with the number recorded.
    """
    from autocarto.contracts import adapt_gate2

    values = _heavy_tailed_below_gvf_floor()
    engine = ClassificationDiagnosticEngine()
    first = engine.evaluate(values, proposed_method="jenks")
    second = ClassificationDiagnosticEngine().evaluate(
        values,
        proposed_method=first.prescribed_method,
        proposed_breaks=first.prescribed_breaks,
    )

    if second.gvf >= ClassificationDiagnosticEngine.GVF_THRESHOLD:
        pytest.skip("fixture cleared the GVF floor; best-effort path not exercised")

    assert second.best_effort is True
    assert adapt_gate2(second).decision == "WARN"
    assert "below the" in (second.instruction or "")
    # Surfaced through the orchestrator-facing contract, not through
    # DiagnosticResult.to_dict() -- that dict is the blessed golden-trace
    # schema and is deliberately left unchanged (see its docstring).
    assert adapt_gate2(second).diagnostics["best_effort"] is True
    assert "best_effort" not in second.to_dict()


def test_guard_does_not_mask_a_genuinely_different_proposal():
    """The guard must fire only for self-prescriptions.

    A caller proposing something else entirely still gets a real rejection --
    otherwise the guard would quietly disable Gate 2.
    """
    values = _heavy_tailed_below_gvf_floor()

    # A method the gate did not mandate is still rejected outright at the
    # method-mismatch step, and must never be reported as best-effort.
    other = ClassificationDiagnosticEngine().evaluate(
        values, proposed_method="equal_interval"
    )
    assert other.passed is False
    assert other.best_effort is False
    assert other.prescribed_method is not None


def test_prescription_match_tolerates_trace_rounding():
    """Breaks round-trip through the trace at 6 significant figures.

    An exact float comparison would report "different" and reopen the
    livelock, so the guard compares with a relative tolerance.
    """
    values = _heavy_tailed_below_gvf_floor()
    first = ClassificationDiagnosticEngine().evaluate(values, proposed_method="jenks")
    assert first.prescribed_breaks

    rounded = [float(f"{b:.6g}") for b in first.prescribed_breaks]
    second = ClassificationDiagnosticEngine().evaluate(
        values, proposed_method=first.prescribed_method, proposed_breaks=rounded
    )
    assert second.passed is True


# ── Helpers ───────────────────────────────────────────────────────────────────

def test_dedupe_breaks_collapses_duplicates_preserving_order():
    assert _dedupe_breaks([0.0, 0.0, 1.0, 1.0, 2.0]) == [0.0, 1.0, 2.0]
    assert _dedupe_breaks([3.0]) == [3.0]


def test_gvf_bounds():
    values = np.random.default_rng(8).normal(0, 1, 200)
    breaks = _naive_breaks(values)
    gvf = ClassificationDiagnosticEngine._compute_gvf(values, breaks)
    assert 0.0 <= gvf <= 1.0


def test_profile_is_seed_deterministic():
    values = np.random.default_rng(9).normal(0, 1, 10_000)  # triggers subsampling
    p1 = DistributionProfile.from_array(values, random_state=0)
    p2 = DistributionProfile.from_array(values, random_state=0)
    assert p1 == p2
