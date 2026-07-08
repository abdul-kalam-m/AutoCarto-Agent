"""Flow-conservation regression for the F-NEW-3 rejection Sankey.

The Sankey is driven by autocarto.benchmark.build_report(); these tests pin the
aggregation invariants the diagram draws, so a change to the benchmark that
would silently invalidate the figure fails here instead. Core deps only.
"""

from __future__ import annotations

from collections import Counter

from autocarto.benchmark import build_report

VALID_G2_METHODS = {
    "manual_break_at_zero_then_fisher_jenks",
    "log_transform_then_jenks",
    "arcsinh_transform_then_jenks",
    "unique_values",
}


def _agg():
    S = build_report()["scenarios"]
    g2 = [s for s in S if s["gate"] == "G2"]
    g3b = [s for s in S if s["gate"] == "G3b"]
    return S, g2, g3b


def test_columns_conserve_mass():
    """Every Sankey column must sum to the same scenario total."""
    S, g2, g3b = _agg()
    n = len(S)
    # proposal column
    assert len(g2) + len(g3b) == n
    # verdict column
    g2_pass = sum(s["outcome"] == "PASS" for s in g2)
    g2_rej = sum(s["outcome"] == "REJECT" for s in g2)
    g3b_acc = sum(s["outcome"] in ("APPROVE", "WARN") for s in g3b)
    g3b_rej = sum(s["outcome"] == "REJECT" for s in g3b)
    assert g2_pass + g2_rej == len(g2)
    assert g3b_acc + g3b_rej == len(g3b)
    # mandated-outcome column (remedies) must also sum to n
    remedy_total = g2_pass + g2_rej + g3b_acc + g3b_rej
    assert remedy_total == n


def test_gate2_rejections_route_to_known_remedies():
    _, g2, _ = _agg()
    methods = Counter(s["prescribed_method"] for s in g2 if s["outcome"] == "REJECT")
    assert set(methods) <= VALID_G2_METHODS
    # every rejected G2 proposal carries a prescription (no silent rejects)
    assert all(s["prescribed_method"] for s in g2 if s["outcome"] == "REJECT")


def test_no_gate2_pass_carries_a_prescription():
    _, g2, _ = _agg()
    for s in g2:
        if s["outcome"] == "PASS":
            assert s["prescribed_method"] is None
