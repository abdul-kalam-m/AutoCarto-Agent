"""Content regression for the F-NEW-2 trace-excerpt figure.

The figure quotes a Gate-2 REJECT verbatim. These tests pin exactly what it
shows, so it can never drift from the shipped trace. Core deps only (no [geo]).
"""

from __future__ import annotations

import json
import os

import numpy as np

import autocarto.demo as demo
from autocarto.execution.gates.gate2_classification import (
    ClassificationDiagnosticEngine, _dedupe_breaks,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reproduce_zero_inflated_reject():
    """Exact reproduction of the demo's zero-inflated case (RNG order matters)."""
    demo.RNG = np.random.default_rng(42)
    _ = demo.make_well_behaved()          # advance RNG as the demo does
    zi = demo.make_zero_inflated()
    naive = _dedupe_breaks([float(np.percentile(zi, p)) for p in (0, 20, 40, 60, 80, 100)])
    res = ClassificationDiagnosticEngine(random_state=0).evaluate(
        zi, proposed_method="jenks", proposed_breaks=naive)
    return zi, res


def test_reject_matches_committed_trace():
    _, res = _reproduce_zero_inflated_reject()
    committed = json.load(open(
        os.path.join(REPO_ROOT, "output", "traces", "gate2_classification_trace.json")
    ))["cases"]["zero_inflated"]
    assert res.diagnosis == committed["diagnosis"] == "zero_inflated"
    assert res.passed is False and committed["passed"] is False
    assert res.prescribed_method == committed["prescribed_method"]
    assert [round(b, 9) for b in res.prescribed_breaks] == \
           [round(b, 9) for b in committed["prescribed_breaks"]]


def test_instruction_carries_the_hard_mandate():
    _, res = _reproduce_zero_inflated_reject()
    assert "DO NOT propose alternative methods" in res.instruction


def test_mandated_code_snippet_is_executable_shape():
    _, res = _reproduce_zero_inflated_reject()
    snip = res.code_snippet
    assert "np.digitize" in snip
    assert "DO NOT MODIFY" in snip
    # the exact prescribed breaks are embedded in the mandated code
    assert str(res.prescribed_breaks[1]) in snip


def test_zero_fraction_is_reported_value():
    zi, _ = _reproduce_zero_inflated_reject()
    assert abs(float(np.mean(zi == 0)) * 100 - 49.8) < 0.1
