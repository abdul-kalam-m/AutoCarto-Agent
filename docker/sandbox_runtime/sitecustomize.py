"""Auto-imported by the Python interpreter on startup (standard `site`
module behavior) for every invocation inside the sandbox image, including
the exact ``python /workspace/exec.py`` command sandbox.py's
``_execute_docker`` runs -- so this applies runner-side style without
``exec.py``'s text ever mentioning a style, matching the same "code never
controls style" contract _resolve_runtime_style documents for the
in-process dev path (TD-9).

Failure here must never break sandboxed code that has nothing to do with
styling: any error resolving or applying the style is swallowed, exactly
like the dev-path equivalent.
"""

import os


def _apply_runtime_style() -> None:
    style_path = os.environ.get("AUTOCARTO_MPLSTYLE_PATH")
    if not style_path:
        return
    try:
        import matplotlib.style
        matplotlib.style.use(style_path)
    except (ImportError, OSError, ValueError):
        pass


_apply_runtime_style()
