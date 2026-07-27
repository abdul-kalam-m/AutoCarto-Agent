"""Curated .mplstyle templates — Blueprint §3 / TD-9.

Five templates, one per render context: ``choropleth``, ``bivariate``,
``proportional_symbol`` (Gate 3a's mandated alternative encoding),
``presentation`` (poster/screen viewing distance), ``print_report`` (dense
policy-report layout). All are minimalist, high-data-ink-ratio styles —
this is what backs the abstract's "publication-quality" claim and the
"deterministic stylesheet injection" line (Abstract_revised.txt).

Style application happens *runner-side*: ``SandboxExecutor`` calls
``matplotlib.style.use(...)`` itself before executing sanitized code
(``execution/sandbox.py`` ``_resolve_runtime_style`` /
``_execute_inprocess``). The LLM never sees or controls a stylesheet path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

STYLE_DIR = Path(__file__).resolve().parent

AVAILABLE_STYLES: Dict[str, Path] = {
    p.stem: p for p in sorted(STYLE_DIR.glob("*.mplstyle"))
}


def resolve_style(name: str) -> str:
    """Resolve a curated style name to an absolute ``.mplstyle`` path.

    Falls back to returning ``name`` unchanged when it is not one of the
    curated templates, so a matplotlib built-in ("default", "seaborn-v0_8",
    ...) or an already-absolute path passes through untouched.
    """
    path = AVAILABLE_STYLES.get(name)
    return str(path) if path is not None else name


__all__ = ["STYLE_DIR", "AVAILABLE_STYLES", "resolve_style"]
