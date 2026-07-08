"""Shared fixtures for the AutoCarto-Agent test suite."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BLESSED_TRACES = REPO_ROOT / "output" / "traces"

# Wall-clock fields are the only legitimately non-deterministic trace content.
TIMING_KEYS = {
    "retrieval_time_ms",
    "spatial_filter_time_ms",
    "semantic_search_time_ms",
    "execution_time_ms",
}


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def blessed_traces_dir() -> Path:
    assert BLESSED_TRACES.is_dir(), "blessed traces missing from output/traces"
    return BLESSED_TRACES


def strip_timing(obj):
    """Recursively zero out wall-clock fields so traces compare stably."""
    if isinstance(obj, dict):
        return {
            k: (0.0 if k in TIMING_KEYS else strip_timing(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [strip_timing(v) for v in obj]
    return obj


def assert_json_equivalent(actual, expected, path="$", rel_tol=1e-6, abs_tol=1e-9):
    """Structural JSON comparison: exact for str/int/bool/None, tolerant for
    floats (guards against last-bit drift on other scipy/numpy builds while
    remaining exact-in-practice on the pinned environment)."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: type mismatch"
        assert actual.keys() == expected.keys(), (
            f"{path}: key mismatch {sorted(actual.keys() ^ expected.keys())}"
        )
        for k in expected:
            assert_json_equivalent(actual[k], expected[k], f"{path}.{k}",
                                   rel_tol, abs_tol)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), (
            f"{path}: list length {len(actual)} != {len(expected)}"
        )
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_json_equivalent(a, e, f"{path}[{i}]", rel_tol, abs_tol)
    elif isinstance(expected, bool) or expected is None or isinstance(expected, str):
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"
    elif isinstance(expected, (int, float)):
        assert isinstance(actual, (int, float)), f"{path}: type mismatch"
        assert math.isclose(float(actual), float(expected),
                            rel_tol=rel_tol, abs_tol=abs_tol), (
            f"{path}: {actual} !~ {expected}"
        )
    else:  # pragma: no cover
        raise AssertionError(f"{path}: unhandled type {type(expected)}")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
