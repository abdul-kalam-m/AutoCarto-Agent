"""`autocarto run` CLI tests — Manual §11 P2 acceptance criterion:
"autocarto run '...' --llm mock produces a validated map + trace offline"."""

from __future__ import annotations

import json

import pytest

geopandas = pytest.importorskip("geopandas")
libpysal = pytest.importorskip("libpysal")

from autocarto.demo_data import SNAPSHOT_PATH
from autocarto.run_cli import main as run_main

pytestmark = pytest.mark.skipif(
    not SNAPSHOT_PATH.exists(), reason="pinned Atlanta TIGER snapshot not present"
)


def test_run_cli_produces_trace_and_figure(tmp_path):
    out_dir = tmp_path / "run_out"
    exit_code = run_main([
        "Map tree canopy loss vs asthma rate in Atlanta",
        "--out", str(out_dir),
        "--seed", "0",
    ])

    assert exit_code == 0
    trace_path = out_dir / "trace.json"
    fig_path = out_dir / "map.png"
    assert trace_path.exists()
    assert fig_path.exists()
    assert fig_path.stat().st_size > 10_000  # a real rendered PNG, not a stub

    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["prompt"] == "Map tree canopy loss vs asthma rate in Atlanta"
    assert trace["dataset_id"] == "atlanta-fulton-dekalb"
    assert trace["render_success"] is True
    assert trace["gate6"]["decision"] == "PASS"
    final_gates = trace["iterations"][-1]["gate_suite"]
    assert final_gates["decision"] != "REJECT"


def test_run_cli_is_deterministic_across_runs(tmp_path):
    out1, out2 = tmp_path / "run1", tmp_path / "run2"
    for out in (out1, out2):
        code = run_main(["Map tree canopy loss vs asthma rate", "--out", str(out), "--seed", "0"])
        assert code == 0

    t1 = json.loads((out1 / "trace.json").read_text(encoding="utf-8"))
    t2 = json.loads((out2 / "trace.json").read_text(encoding="utf-8"))
    # Gate diagnostics (the statistical content) must match exactly, seed-for-seed.
    assert t1["iterations"][-1]["gate_suite"] == t2["iterations"][-1]["gate_suite"]
    assert t1["code_hash"] == t2["code_hash"]


def test_run_cli_missing_prompt_errors():
    with pytest.raises(SystemExit):
        run_main([])
