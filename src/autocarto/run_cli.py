"""`autocarto run` — drive the Propose-Verify-Execute orchestrator end to end.

    autocarto run "<prompt>" [--out DIR] [--seed N] [--max-iter N]

Uses the built-in offline Atlanta demo dataset (real TIGER geometry, SAR
synthetic variables — see `demo_data.py`) and `MockLLM` by default, so this
runs with zero network calls and zero API keys (Manual §11 P2 acceptance
criterion). Writes the full iteration trace as JSON and, on success, the
rendered figure as PNG, to `--out` (default: ./output/run).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List


def main(argv: List[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="autocarto run",
        description="Run the Propose-Verify-Execute orchestrator end to end.",
    )
    parser.add_argument("prompt", type=str, help="Natural-language mapping request")
    parser.add_argument(
        "--out", type=Path, default=Path("output") / "run",
        help="Output directory (default: ./output/run)",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed (default: 0)")
    parser.add_argument("--max-iter", type=int, default=3, help="Max mandate iterations (default: 3)")
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from autocarto.demo_data import load_atlanta_dataset
        from autocarto.orchestrator import Orchestrator
        from autocarto.semantic.llm_client import MockLLM
    except RuntimeError as exc:
        print(f"autocarto run: {exc}", file=sys.stderr)
        return 1

    print("AutoCarto-Agent orchestrator run")
    print(f"  prompt:   {args.prompt!r}")
    print(f"  seed:     {args.seed}")
    print(f"  max_iter: {args.max_iter}")

    t0 = time.time()
    dataset = load_atlanta_dataset()
    print(f"  dataset:  {dataset.description}")

    orchestrator = Orchestrator(llm=MockLLM(), max_iter=args.max_iter, seed=args.seed)
    result = orchestrator.run(args.prompt, dataset)
    elapsed_ms = (time.time() - t0) * 1000

    print()
    for it in result.trace["iterations"]:
        gs = it["gate_suite"]
        marker = "REJECT" if gs["decision"] == "REJECT" else gs["decision"]
        print(f"  iteration {it['iteration']}: {marker} "
              f"(method={it['proposal']['classification_method']}, "
              f"rejections={gs['rejection_count']})")

    trace_path = out_dir / "trace.json"
    trace_path.write_text(result.trace_json(), encoding="utf-8")
    print(f"\nTrace written: {trace_path}")

    if result.success:
        fig_path = out_dir / "map.png"
        result.figure.savefig(fig_path, dpi=200, bbox_inches="tight", facecolor="white")
        print(f"Figure written: {fig_path}")
        print(f"Gate 6 (completeness): {result.trace['gate6']['decision']}")
        print(f"\nTotal wall-clock: {elapsed_ms:.1f} ms")
        return 0

    if result.human_review:
        print(f"\nHUMAN REVIEW REQUIRED: {result.insufficiency_report}")
    else:
        print(f"\nRender failed: {result.trace.get('render_error') or result.trace.get('execution_error')}")
    print(f"\nTotal wall-clock: {elapsed_ms:.1f} ms")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
