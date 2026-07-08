"""AutoCarto-Agent command-line interface.

    autocarto demo [--out DIR]        deterministic demo harness
    autocarto benchmark [--out DIR]   mini-benchmark (naive-policy rejection rates)
"""

from __future__ import annotations

import sys
from typing import List

from autocarto import __version__


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__.strip())
        print(f"\nautocarto-agent {__version__}")
        return 0
    if argv[0] in {"-V", "--version"}:
        print(f"autocarto-agent {__version__}")
        return 0

    command, rest = argv[0], argv[1:]
    if command == "demo":
        from autocarto.demo import main as demo_main
        return demo_main(rest)
    if command == "benchmark":
        from autocarto.benchmark import main as benchmark_main
        return benchmark_main(rest)

    print(f"autocarto: unknown command {command!r} (expected 'demo' or 'benchmark')",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
