"""Air-gapped execution sandbox for LLM-generated code.

Supports two backends:
    1. Pyodide (WASM) - for browser-side or local development
    2. gVisor (Docker + runsc) - for production server deployment

In both modes:
    - Network access is physically disabled
    - Filesystem is read-only or virtual
    - Memory is capped at 512MB
    - Execution is time-limited to 30 seconds
    - Only whitelisted imports are permitted
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set, Tuple
import ast
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import json
from pathlib import Path


# Whitelisted modules - everything else is blocked
# V1 HARDENING: contextily removed — it performs network tile fetches, which
# contradicts the air-gap contract when code runs under _DevOnlySandboxExecutor
# (no network namespace isolation in dev mode). Re-add only inside the
# network-less production container. See Fable Review/01_OPERATING_MANUAL.md §10.
ALLOWED_IMPORTS: Set[str] = {
    "matplotlib", "matplotlib.pyplot",
    "geopandas", "pandas", "numpy", "scipy", "scipy.stats",
    "jenkspy", "pyogrio", "shapely", "shapely.geometry",
    "cartopy", "cartopy.crs",
    "pyproj", "PIL", "io", "base64",
    "typing", "dataclasses",
    "json", "math", "statistics",
    "collections", "itertools", "functools",
}

# PATCH: dunder attributes that enable reflection-based sandbox escapes
# (``().__class__.__mro__[1].__subclasses__()`` etc.). Surface-level audit
# only; the trusted control here is the AST-walking attribute blocker below.
DANGEROUS_ATTRIBUTES: Set[str] = {
    "__class__", "__bases__", "__mro__", "__subclasses__",
    "__globals__", "__builtins__", "__dict__", "__getattribute__",
    "__reduce__", "__reduce_ex__", "__import__", "__loader__",
    "__spec__", "__code__", "__closure__",
    # V1 HARDENING: exception/frame traversal escape family —
    # ``except Exception as e: e.__traceback__.tb_frame.f_globals`` reaches the
    # importing module's globals without touching __class__/__mro__.
    "__traceback__", "tb_frame", "tb_next",
    "f_globals", "f_locals", "f_builtins", "f_back",
    # generator/coroutine frame access, same family
    "gi_frame", "cr_frame",
}

# Blocked patterns indicating malicious or dangerous code (AST-confirmed below).
BLOCKED_PATTERNS: List[re.Pattern] = [
    re.compile(r"__import__\s*\("),
    re.compile(r"\bimportlib\b"),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bcompile\s*\("),
    re.compile(r"\bsubprocess\b"),
    re.compile(r"\bos\.system\b"),
    re.compile(r"\bos\.popen\b"),
    re.compile(r"\bos\.remove\b"),
    re.compile(r"\bos\.unlink\b"),
    re.compile(r"\bos\.rmdir\b"),
    re.compile(r"\bshutil\."),
    re.compile(r"\bsocket\."),
    re.compile(r"\brequests\."),
    re.compile(r"\burllib\b"),
    re.compile(r"\bbase64\.b64decode\b"),
]

# PATCH: AST-level checks for writeable open() calls. Regex on the source is
# bypassable (keyword args, dynamic mode strings); we walk the AST instead.
_WRITE_MODE_CHARS = {"w", "a", "x", "+"}


@dataclass
class SandboxResult:
    """Output from sandboxed execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    figure_data: Optional[bytes] = None  # Serialized matplotlib figure
    error_type: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout_preview": self.stdout[:500] if self.stdout else "",
            "stderr_preview": self.stderr[:500] if self.stderr else "",
            "has_figure": self.figure_data is not None,
            "error_type": self.error_type,
            "execution_time_ms": round(self.execution_time_ms, 3),
        }


class CodeSanitizer:
    """Pre-flight code sanitization using AST analysis and regex scanning."""

    @classmethod
    def sanitize(cls, code: str) -> Tuple[bool, str, List[str]]:
        """
        Returns:
            (is_safe, sanitized_code_or_message, list_of_violations)
        """
        violations: List[str] = []

        # PATCH: strip string and comment content before regex scanning so that
        # legitimate docstrings mentioning "subprocess" or "os.system" do not
        # trigger false positives, while still catching the real call sites.
        scrub = cls._strip_strings_and_comments(code)
        for pattern in BLOCKED_PATTERNS:
            matches = pattern.findall(scrub)
            if matches:
                violations.append(f"Blocked pattern detected: {pattern.pattern} -> {matches}")

        # AST analysis for imports + attribute access + write-mode open()
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error in generated code: {e}", [str(e)]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not cls._is_allowed_import(alias.name):
                        violations.append(f"Blocked import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and not cls._is_allowed_import(node.module):
                    violations.append(f"Blocked import from: {node.module}")
            elif isinstance(node, ast.Attribute):
                # PATCH: block dunder reflection chains regardless of indentation.
                if node.attr in DANGEROUS_ATTRIBUTES:
                    violations.append(f"Blocked attribute access: .{node.attr}")
            elif isinstance(node, ast.Call):
                bad = cls._inspect_call(node)
                if bad:
                    violations.append(bad)

        if violations:
            return False, "CODE SANITIZATION FAILED:\n" + "\n".join(violations), violations

        return True, code, []

    @classmethod
    def _is_allowed_import(cls, module_name: str) -> bool:
        """Check if a module or its parent is in the whitelist."""
        parts = module_name.split(".")
        for i in range(len(parts), 0, -1):
            if ".".join(parts[:i]) in ALLOWED_IMPORTS:
                return True
        return False

    @staticmethod
    def _strip_strings_and_comments(code: str) -> str:
        """Best-effort scrub of string literals and comments for regex pass."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        spans: List[Tuple[int, int]] = []
        lines = code.splitlines(keepends=True)
        line_offsets = [0]
        for ln in lines:
            line_offsets.append(line_offsets[-1] + len(ln))

        def _abs(lineno: int, col: int) -> int:
            return line_offsets[lineno - 1] + col

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if (
                    node.lineno is None or node.col_offset is None
                    or node.end_lineno is None or node.end_col_offset is None
                ):
                    continue
                spans.append((_abs(node.lineno, node.col_offset),
                              _abs(node.end_lineno, node.end_col_offset)))

        scrubbed = list(code)
        for start, end in spans:
            for i in range(start, min(end, len(scrubbed))):
                if scrubbed[i] not in ("\n", "\r"):
                    scrubbed[i] = " "
        cleaned = "".join(scrubbed)
        # Drop comments line by line.
        return "\n".join(line.split("#", 1)[0] for line in cleaned.splitlines())

    @classmethod
    def _inspect_call(cls, node: ast.Call) -> Optional[str]:
        """Inspect a call site for forbidden patterns."""
        func = node.func
        # open(path, mode) write/append/exclusive detection
        if isinstance(func, ast.Name) and func.id == "open":
            mode = cls._extract_open_mode(node)
            if mode and any(ch in _WRITE_MODE_CHARS for ch in mode):
                return f"Blocked open() with write-capable mode: {mode!r}"
        # getattr(obj, '__class__'...)
        if isinstance(func, ast.Name) and func.id == "getattr" and node.args:
            second = node.args[1] if len(node.args) > 1 else None
            if isinstance(second, ast.Constant) and second.value in DANGEROUS_ATTRIBUTES:
                return f"Blocked getattr() targeting {second.value}"
        return None

    @staticmethod
    def _extract_open_mode(node: ast.Call) -> Optional[str]:
        # positional arg index 1
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            val = node.args[1].value
            if isinstance(val, str):
                return val
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                val = kw.value.value
                if isinstance(val, str):
                    return val
        return None


class SandboxExecutor:
    """Execute code in an air-gapped sandbox."""

    TIMEOUT_SECONDS = 30
    MEMORY_LIMIT_MB = 512

    # PATCH: configurable so callers can point at a stylesheet that actually
    # exists. Default falls back to matplotlib's built-in "default" so the
    # injection cannot crash a clean run.
    DEFAULT_STYLE: str = "default"

    def __init__(self, backend: str = "docker", style: Optional[str] = None):
        """
        Args:
            backend: "docker" for gVisor (production) or
                     "pyodide" for WASM (future).
                     The string "inprocess" is no longer accepted here; it was
                     removed in response to reviewer issue 5 — see
                     _execute_inprocess docstring.
            style: matplotlib stylesheet name or absolute path. Falls back to
                the matplotlib default style when None.
        """
        if backend == "inprocess":
            raise RuntimeError(
                "backend='inprocess' is not permitted in SandboxExecutor. "
                "Use _DevOnlySandboxExecutor for local testing. "
                "See CHANGES.md §sandbox.py issue 5."
            )
        self.backend = backend
        self.sanitizer = CodeSanitizer()
        self.style = style or self.DEFAULT_STYLE

    def execute(self, code: str, data_snapshot: Optional[Dict[str, Any]] = None) -> SandboxResult:
        """Execute sanitized code in isolated environment.

        Args:
            code: LLM-generated Python code
            data_snapshot: Pre-loaded data passed into sandbox (JSON-serializable)

        Returns:
            SandboxResult with output, figure, and telemetry
        """
        import time
        start = time.time()

        # Pre-flight sanitization
        is_safe, sanitized, violations = self.sanitizer.sanitize(code)
        if not is_safe:
            return SandboxResult(
                success=False,
                stderr=sanitized,
                error_type="sanitization_failure",
                execution_time_ms=(time.time() - start) * 1000,
            )

        if self.backend == "docker":
            return self._execute_docker(sanitized, data_snapshot)
        if self.backend == "pyodide":
            raise NotImplementedError("Pyodide backend not implemented in this build")
        # Any other backend string is an unsupported value; fail loudly.
        raise RuntimeError(
            f"Unsupported backend {self.backend!r}. "
            "Only 'docker' and 'pyodide' are valid for SandboxExecutor. "
            "If Docker is unavailable, the pipeline must not fall back to "
            "in-process exec(); raise this error to the caller instead."
        )

    def _resolve_runtime_style(self) -> str:
        """Resolve ``self.style`` to a path/name ``matplotlib.style.use`` accepts.

        FIX (TD-9): style used to be applied by splicing a
        ``plt.style.use(...)`` call into the *text* of LLM-generated code
        (see git history / CHANGES.md) — fragile (misses aliased pyplot
        imports, breaks on code that never imports pyplot itself but still
        renders via ``GeoDataFrame.plot()``) and conceptually wrong: style
        is a rendering concern, and the LLM tier should not be the one
        applying it (Manual §6.2-3, "the code never controls style").

        The fix moves style application to the *runner*: the sandbox
        executor calls ``matplotlib.style.use(...)`` itself, in the
        process/container that will run the sanitized code, before that
        code executes. The code text is never touched.
        """
        from autocarto.styles import resolve_style
        return resolve_style(self.style)

    # ------------------------------------------------------------------
    # Docker backend
    # ------------------------------------------------------------------
    def _execute_docker(
        self, code: str, data_snapshot: Optional[Dict[str, Any]] = None
    ) -> SandboxResult:
        """Execute in gVisor-isolated Docker container."""
        import time
        start = time.time()

        with tempfile.TemporaryDirectory() as tmpdir:
            code_path = Path(tmpdir) / "exec.py"
            code_path.write_text(code, encoding="utf-8")

            if data_snapshot:
                data_path = Path(tmpdir) / "data.json"
                data_path.write_text(json.dumps(data_snapshot), encoding="utf-8")

            cmd = [
                "docker", "run",
                "--runtime=runsc",
                "--network=none",
                "--memory=512m",
                "--memory-swap=512m",
                "--read-only",
                "--tmpfs", "/tmp:size=100m,noexec",
                "--security-opt=no-new-privileges",
                "--cap-drop=ALL",
                "--rm",
                # TD-9: style is applied runner-side via an env var the
                # container entrypoint reads and passes to
                # matplotlib.style.use(...) before running exec.py — the
                # code in exec.py never sets its own style. NOTE: this env
                # var is unconsumed today because no container image or
                # entrypoint script exists yet (Manual TD-5, still open);
                # wiring it here documents the intended contract for when
                # Dockerfile.sandbox ships, it does not itself make Docker
                # execution work.
                "-e", f"AUTOCARTO_MPLSTYLE_PATH={self._resolve_runtime_style()}",
                "-v", f"{tmpdir}:/workspace:ro",
                "autocarto-sandbox:latest",
                "python", "/workspace/exec.py",
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.TIMEOUT_SECONDS + 5,
                )
                elapsed = (time.time() - start) * 1000
                return SandboxResult(
                    success=result.returncode == 0,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time_ms=elapsed,
                )
            except subprocess.TimeoutExpired:
                return SandboxResult(
                    success=False,
                    stderr=f"Execution timed out after {self.TIMEOUT_SECONDS}s",
                    error_type="timeout",
                    execution_time_ms=self.TIMEOUT_SECONDS * 1000,
                )
            except FileNotFoundError:
                return SandboxResult(
                    success=False,
                    stderr="docker binary not found on PATH",
                    error_type="backend_unavailable",
                    execution_time_ms=(time.time() - start) * 1000,
                )

    # ------------------------------------------------------------------
    # In-process backend — REMOVED from production executor
    # ------------------------------------------------------------------
    def _execute_inprocess(self, code: str) -> SandboxResult:
        """PATCH (reviewer issue 5): this method previously contained a
        threading-based exec() fallback. It has been removed from the
        production class because restricted builtins and AST-level checks
        provide only an *illusion* of security. Any LLM that knows CPython
        internals can still escape via:

            ().__class__.__bases__[0].__subclasses__()

        or equivalent chains that do not touch the explicitly banned attrs.
        There is no safe in-process fallback; the only correct answer is a
        genuine process-isolation boundary (gVisor, Firecracker, Pyodide WASM).

        If gVisor/Docker is unavailable the pipeline MUST surface this error
        rather than silently downgrading security.

        For local unit-testing, use _DevOnlySandboxExecutor (below), which
        inherits this method and is clearly labelled NOT for production.
        """
        raise RuntimeError(
            "Secure execution backend unavailable. "
            "The Docker/gVisor backend must be configured before running the DEE. "
            "In-process exec() is not permitted in SandboxExecutor. "
            "For local test harnesses only, use _DevOnlySandboxExecutor explicitly."
        )

    def _build_safe_builtins(self) -> Dict[str, Any]:
        """Restricted builtins. ``getattr``/``hasattr`` removed by default."""
        safe = {
            "print": print,
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "min": min,
            "max": max,
            "sum": sum,
            "abs": abs,
            "round": round,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "isinstance": isinstance,
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "ImportError": ImportError,
            "TimeoutError": TimeoutError,
            "True": True,
            "False": False,
            "None": None,
            "__import__": self._safe_import,
        }
        return safe

    @staticmethod
    def _safe_import(name, *args, **kwargs):
        """Restricted __import__ that only permits whitelisted modules."""
        if name in ALLOWED_IMPORTS or any(
            name.startswith(allowed + ".") for allowed in ALLOWED_IMPORTS
        ):
            return __import__(name, *args, **kwargs)
        raise ImportError(f"Module '{name}' is not in the allowed import whitelist.")


# ---------------------------------------------------------------------------
# Development-only executor — NOT for production use
# ---------------------------------------------------------------------------
class _DevOnlySandboxExecutor(SandboxExecutor):
    """Subclass that re-enables the in-process exec() path for local testing.

    PATCH (reviewer issue 5): this class exists ONLY so the demo harness and
    unit tests can exercise the sanitiser and builtins logic on machines where
    Docker/gVisor is unavailable. It must never be imported or instantiated
    in the production DEE codebase.

    The class deliberately carries a leading underscore and a conspicuous name
    to prevent accidental production use. CI should enforce that no non-test
    file imports ``_DevOnlySandboxExecutor``.
    """

    def __init__(self, style: Optional[str] = None):
        # Bypass the parent __init__ guard that rejects "inprocess".
        # We do NOT call super().__init__("inprocess") — we construct manually.
        self.backend = "inprocess"
        self.sanitizer = CodeSanitizer()
        self.style = style or self.DEFAULT_STYLE

    def _execute_inprocess(self, code: str) -> SandboxResult:  # type: ignore[override]
        """Thread-based exec() with cross-platform timeout. Development only."""
        import time
        start = time.time()

        try:
            import resource  # type: ignore[import-not-found]
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.MEMORY_LIMIT_MB * 1024 * 1024, self.MEMORY_LIMIT_MB * 1024 * 1024),
            )
        except (ImportError, ValueError):
            pass

        # TD-9: apply style runner-side, in this process, before the user
        # code runs — matplotlib rcParams are process-global, so this takes
        # effect for any plt/GeoDataFrame.plot() call the executed code
        # makes, without the code text ever mentioning a style at all.
        try:
            import matplotlib.style
            matplotlib.style.use(self._resolve_runtime_style())
        except (ImportError, OSError, ValueError):
            pass  # style unavailable; execution proceeds with whatever rcParams are active

        safe_builtins = self._build_safe_builtins()
        exec_globals: Dict[str, Any] = {"__builtins__": safe_builtins, "__name__": "sandbox"}
        result: Dict[str, Any] = {"error": None}

        def _target():
            try:
                exec(compile(code, "<sandbox>", "exec"), exec_globals)  # noqa: S102
            except BaseException as exc:  # noqa: BLE001
                result["error"] = exc

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(self.TIMEOUT_SECONDS)
        elapsed_ms = (time.time() - start) * 1000

        if thread.is_alive():
            return SandboxResult(
                success=False,
                stderr=f"Execution exceeded {self.TIMEOUT_SECONDS}s (thread still running)",
                error_type="timeout",
                execution_time_ms=elapsed_ms,
            )
        err = result["error"]
        if err is not None:
            return SandboxResult(
                success=False,
                stderr=f"{type(err).__name__}: {err}",
                error_type=type(err).__name__,
                execution_time_ms=elapsed_ms,
            )
        return SandboxResult(success=True, execution_time_ms=elapsed_ms)

    def execute(self, code: str, data_snapshot: Optional[Dict[str, Any]] = None) -> SandboxResult:
        """Route directly to _execute_inprocess, bypassing Docker dispatch."""
        import time
        start = time.time()
        is_safe, sanitized, violations = self.sanitizer.sanitize(code)
        if not is_safe:
            return SandboxResult(
                success=False,
                stderr=sanitized,
                error_type="sanitization_failure",
                execution_time_ms=(time.time() - start) * 1000,
            )
        return self._execute_inprocess(sanitized)
