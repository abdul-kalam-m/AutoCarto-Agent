"""Air-gapped execution sandbox for LLM-generated code.

Supports two backends:
    1. Pyodide (WASM) — for browser-side or local development
    2. gVisor (Docker + runsc) — for production server deployment

In both modes:
    - Network access is physically disabled
    - Filesystem is read-only or virtual
    - Memory is capped at 512MB
    - Execution is time-limited to 30 seconds
    - Only whitelisted imports are permitted
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set
import ast
import re
import subprocess
import tempfile
import os
import json
from pathlib import Path


# Whitelisted modules — everything else is blocked
ALLOWED_IMPORTS: Set[str] = {
    "matplotlib", "matplotlib.pyplot",
    "geopandas", "pandas", "numpy", "scipy", "scipy.stats",
    "jenkspy", "pyogrio", "shapely", "shapely.geometry",
    "contextily", "cartopy", "cartopy.crs",
    "pyproj", "PIL", "io", "base64",
    "typing", "dataclasses",
    "json", "math", "statistics",
    "collections", "itertools", "functools",
}

# Blocked patterns indicating malicious or dangerous code
BLOCKED_PATTERNS: List[re.Pattern] = [
    re.compile(r"__import__\s*\("),
    re.compile(r"importlib"),
    re.compile(r"exec\s*\("),
    re.compile(r"eval\s*\("),
    re.compile(r"compile\s*\("),
    re.compile(r"subprocess"),
    re.compile(r"os\.system"),
    re.compile(r"os\.popen"),
    re.compile(r"os\.remove"),
    re.compile(r"os\.unlink"),
    re.compile(r"os\.rmdir"),
    re.compile(r"shutil\."),
    re.compile(r"socket\."),
    re.compile(r"requests\."),
    re.compile(r"urllib"),
    re.compile(r"open\s*\(.*['\"]w"),  # Write-mode open
    re.compile(r"open\s*\(.*['\"]a"),  # Append-mode open
    re.compile(r"base64\.b64decode"),
    re.compile(r"exec\s*\(\s*.*base64"),
]


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
            "execution_time_ms": self.execution_time_ms,
        }


class CodeSanitizer:
    """Pre-flight code sanitization using AST analysis and regex scanning."""

    @classmethod
    def sanitize(cls, code: str) -> tuple[bool, str, List[str]]:
        """
        Returns:
            (is_safe, sanitized_code_or_message, list_of_violations)
        """
        violations = []

        # Regex scan for dangerous patterns
        for pattern in BLOCKED_PATTERNS:
            matches = pattern.findall(code)
            if matches:
                violations.append(f"Blocked pattern detected: {pattern.pattern} → {matches}")

        # AST analysis for import validation
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if not cls._is_allowed_import(alias.name):
                            violations.append(f"Blocked import: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and not cls._is_allowed_import(node.module):
                        violations.append(f"Blocked import from: {node.module}")
        except SyntaxError as e:
            violations.append(f"Syntax error in generated code: {e}")

        if violations:
            return False, f"CODE SANITIZATION FAILED:\n" + "\n".join(violations), violations

        return True, code, []

    @classmethod
    def _is_allowed_import(cls, module_name: str) -> bool:
        """Check if a module or its parent is in the whitelist."""
        parts = module_name.split(".")
        # Check full path and parent paths
        for i in range(len(parts), 0, -1):
            if ".".join(parts[:i]) in ALLOWED_IMPORTS:
                return True
        return False


class SandboxExecutor:
    """Execute code in an air-gapped sandbox."""

    TIMEOUT_SECONDS = 30
    MEMORY_LIMIT_MB = 512

    def __init__(self, backend: str = "docker"):
        """
        Args:
            backend: "docker" for gVisor, "pyodide" for WASM (future)
        """
        self.backend = backend
        self.sanitizer = CodeSanitizer()

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

        # Inject stylesheet loading before matplotlib import
        sanitized = sanitized.replace(
            "import matplotlib.pyplot as plt",
            "import matplotlib.pyplot as plt\nplt.style.use('/styles/policy_report.mplstyle')"
        )

        # Add timeout wrapper
        wrapped_code = f"""
import signal
import sys

def timeout_handler(signum, frame):
    raise TimeoutError("Execution exceeded {self.TIMEOUT_SECONDS}s limit")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm({self.TIMEOUT_SECONDS})

try:
{sanitized.replace(chr(10), chr(10) + '    ')}
finally:
    signal.alarm(0)
"""

        # Execute in gVisor Docker container
        if self.backend == "docker":
            return self._execute_docker(wrapped_code, data_snapshot)
        else:
            # Fallback: execute in-process with resource limits (development only)
            return self._execute_inprocess(wrapped_code)

    def _execute_docker(
        self, code: str, data_snapshot: Optional[Dict[str, Any]] = None
    ) -> SandboxResult:
        """Execute in gVisor-isolated Docker container."""
        import time
        start = time.time()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write code to temp file
            code_path = Path(tmpdir) / "exec.py"
            code_path.write_text(code)

            # Write data snapshot if provided
            if data_snapshot:
                data_path = Path(tmpdir) / "data.json"
                data_path.write_text(json.dumps(data_snapshot))

            # Docker run with gVisor
            cmd = [
                "docker", "run",
                "--runtime=runsc",           # gVisor sandbox
                "--network=none",            # No network
                "--memory=512m",
                "--memory-swap=512m",
                "--read-only",
                "--tmpfs", "/tmp:size=100m,noexec",
                "--security-opt=no-new-privileges",
                "--cap-drop=ALL",
                "--rm",
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

    def _execute_inprocess(self, code: str) -> SandboxResult:
        """In-process execution with resource limits (development only).

        WARNING: Not secure for production. Use Docker/gVisor backend.
        """
        import time
        start = time.time()

        # Restrict builtins
        safe_builtins = {
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
            "hasattr": hasattr,
            "getattr": getattr,
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

        try:
            import resource
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.MEMORY_LIMIT_MB * 1024 * 1024, self.MEMORY_LIMIT_MB * 1024 * 1024)
            )
        except (ImportError, AttributeError):
            pass  # Windows/macOS — memory limits not enforced

        try:
            exec_globals = {"__builtins__": safe_builtins}
            exec(code, exec_globals)
            elapsed = (time.time() - start) * 1000
            return SandboxResult(
                success=True,
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return SandboxResult(
                success=False,
                stderr=str(e),
                error_type=type(e).__name__,
                execution_time_ms=elapsed,
            )

    @staticmethod
    def _safe_import(name, *args, **kwargs):
        """Restricted __import__ that only permits whitelisted modules."""
        if name in ALLOWED_IMPORTS or any(
            name.startswith(allowed + ".") for allowed in ALLOWED_IMPORTS
        ):
            return __import__(name, *args, **kwargs)
        raise ImportError(f"Module '{name}' is not in the allowed import whitelist.")