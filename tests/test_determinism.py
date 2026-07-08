"""Determinism and golden-trace regression — the project's crown-jewel property.

Two independent guarantees (Fable Review/01_OPERATING_MANUAL.md §12.4):

1. **Run-to-run determinism** (platform-independent claim): two demo runs in
   this environment produce byte-identical gate2/gate3b traces, and identical
   retrieval/sandbox traces once wall-clock fields are zeroed.

2. **Golden parity**: today's run matches the blessed traces committed in
   output/traces/ — exact on the pinned environment, tolerance-guarded
   (rel 1e-6) so other scipy/numpy builds only fail on real regressions.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import assert_json_equivalent, load_json, strip_timing

STATISTICAL_TRACES = ["gate2_classification_trace.json", "gate3b_bivariate_trace.json"]
TELEMETRY_TRACES = ["hybrid_retrieval_trace.json", "sandbox_trace.json"]
ALL_TRACES = STATISTICAL_TRACES + TELEMETRY_TRACES


def _run_demo(out_dir: Path) -> None:
    # Explicit pipes + DEVNULL stdin: under pytest's output capture the parent's
    # std handles are not inheritable, so `capture_output` alone raises
    # "WinError 6: The handle is invalid" on Windows. Detaching stdin fixes it.
    proc = subprocess.run(
        [sys.executable, "-m", "autocarto.demo", "--out", str(out_dir)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"demo failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.fixture(scope="module")
def two_demo_runs(tmp_path_factory) -> tuple[Path, Path]:
    a = tmp_path_factory.mktemp("demo_a")
    b = tmp_path_factory.mktemp("demo_b")
    _run_demo(a)
    _run_demo(b)
    return a, b


@pytest.mark.parametrize("trace", STATISTICAL_TRACES)
def test_statistical_traces_byte_identical_across_runs(two_demo_runs, trace):
    a, b = two_demo_runs
    assert (a / "traces" / trace).read_bytes() == (b / "traces" / trace).read_bytes()


@pytest.mark.parametrize("trace", TELEMETRY_TRACES)
def test_telemetry_traces_identical_modulo_timing(two_demo_runs, trace):
    a, b = two_demo_runs
    ja = strip_timing(load_json(a / "traces" / trace))
    jb = strip_timing(load_json(b / "traces" / trace))
    assert ja == jb


@pytest.mark.parametrize("trace", ALL_TRACES)
def test_golden_parity_with_blessed_traces(two_demo_runs, blessed_traces_dir, trace):
    a, _ = two_demo_runs
    actual = strip_timing(load_json(a / "traces" / trace))
    blessed = strip_timing(load_json(blessed_traces_dir / trace))
    assert_json_equivalent(actual, blessed)


def test_demo_emits_expected_artifacts(two_demo_runs):
    a, _ = two_demo_runs
    for rel in [
        "figures/gate2_distribution_diagnostics.png",
        "figures/gate3b_bivariate_scenarios.png",
        "figures/gate3b_bivariate_map_approve.png",
        "logs/run.log",
        "RUN_SUMMARY.json",
    ]:
        assert (a / rel).exists(), f"missing artifact: {rel}"


def test_benchmark_report_is_deterministic(tmp_path):
    from autocarto.benchmark import build_report

    r1 = build_report()
    r2 = build_report()
    assert r1 == r2
    assert r1["summary"]["total_scenarios"] == (
        r1["corpus"]["gate2_scenarios"] + r1["corpus"]["gate3b_scenarios"]
    )
