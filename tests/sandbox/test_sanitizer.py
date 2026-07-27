"""Sandbox sanitizer contracts: the 8 demo cases + V1 hardening additions.

The sanitizer is a cost-raiser, not the security boundary (that is the
container — Fable Review/01_OPERATING_MANUAL.md §10). These tests pin the
behavior we *do* claim: every attempted vector in this suite is blocked, and
benign scientific code (including docstrings mentioning scary words) passes.
"""

from __future__ import annotations

import pytest

from autocarto.demo import SANDBOX_TEST_CASES
from autocarto.execution.sandbox import (
    ALLOWED_IMPORTS,
    CodeSanitizer,
    SandboxExecutor,
    _DevOnlySandboxExecutor,
)


# ── The 8 demo cases, verbatim ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "case", SANDBOX_TEST_CASES, ids=[c["name"] for c in SANDBOX_TEST_CASES]
)
def test_demo_case_sanitization(case):
    is_safe, _message, violations = CodeSanitizer.sanitize(case["code"])
    assert is_safe == case["expect_sanitize_pass"], violations


def test_production_class_refuses_inprocess_backend():
    with pytest.raises(RuntimeError):
        SandboxExecutor(backend="inprocess")


def test_dev_executor_runs_safe_code():
    res = _DevOnlySandboxExecutor().execute("import numpy as np\nprint(np.sum([1, 2]))\n")
    assert res.success is True


# ── V1 hardening: exception/frame traversal escape family ────────────────────

TRACEBACK_ESCAPE = """
try:
    raise ValueError("x")
except ValueError as e:
    g = e.__traceback__.tb_frame.f_globals
    print(g)
"""

GENERATOR_FRAME_ESCAPE = """
def gen():
    yield 1
g = gen()
print(g.gi_frame.f_builtins)
"""


def test_traceback_frame_escape_blocked():
    is_safe, _msg, violations = CodeSanitizer.sanitize(TRACEBACK_ESCAPE)
    assert is_safe is False
    joined = " ".join(violations)
    assert "__traceback__" in joined or "tb_frame" in joined or "f_globals" in joined


def test_generator_frame_escape_blocked():
    is_safe, _msg, violations = CodeSanitizer.sanitize(GENERATOR_FRAME_ESCAPE)
    assert is_safe is False


def test_getattr_reflection_spelling_blocked():
    is_safe, _msg, _violations = CodeSanitizer.sanitize(
        "x = getattr((), '__class__')\n"
    )
    assert is_safe is False


def test_contextily_no_longer_whitelisted():
    """contextily fetches network tiles — removed from the dev whitelist (§10)."""
    assert "contextily" not in ALLOWED_IMPORTS
    is_safe, _msg, violations = CodeSanitizer.sanitize("import contextily\n")
    assert is_safe is False
    assert any("contextily" in v for v in violations)


def test_scientific_stack_still_whitelisted():
    for mod in ("numpy", "pandas", "geopandas", "matplotlib.pyplot", "scipy.stats"):
        is_safe, _msg, violations = CodeSanitizer.sanitize(f"import {mod}\n")
        assert is_safe, f"{mod} should be allowed: {violations}"


# ── Style-override blocking: TD-9's "code never controls style" contract ────
# Not a security boundary -- these don't enable any escape -- but runner-side
# style injection (sitecustomize.py / _resolve_runtime_style) is a plain
# rcParams mutation with nothing else preventing code from resetting it
# right back afterward.

@pytest.mark.parametrize("code", [
    "import matplotlib.pyplot as plt\nplt.style.use('default')\n",
    "import matplotlib\nmatplotlib.style.use('classic')\n",
    "import matplotlib.pyplot as plt\nplt.rcdefaults()\n",
    "from matplotlib import rcdefaults\nrcdefaults()\n",
], ids=["plt.style.use", "matplotlib.style.use", "plt.rcdefaults", "bare rcdefaults"])
def test_style_override_calls_blocked(code):
    is_safe, _msg, violations = CodeSanitizer.sanitize(code)
    assert is_safe is False, f"expected this to be blocked: {code!r}"
