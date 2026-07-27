"""`autocarto run` — drive the Propose-Verify-Execute orchestrator end to end.

    autocarto run "<prompt>" [--out DIR] [--seed N] [--max-iter N]
                             [--llm {mock,nvidia}] [--model NAME]
                             [--data {synthetic,real}]

By default uses the offline Atlanta demo dataset (real TIGER geometry, SAR
synthetic variables) and MockLLM — zero network, zero API keys (Manual §11
P2 acceptance criterion). Opt into the real open-source LLM tier with
``--llm nvidia`` (reads NVIDIA_API_KEY from the environment or .env), and
into real ACS+CDC data with ``--data real``. Writes the full iteration
trace as JSON and, on success, the rendered figure as PNG, to ``--out``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List


def _build_llm(kind: str, model: str | None):
    if kind == "mock":
        from autocarto.semantic.llm_client import MockLLM
        return MockLLM(), "mock", "deterministic-rule-based"
    if kind == "nvidia":
        from autocarto.semantic.nvidia_llm import NvidiaLLM
        llm = NvidiaLLM(model=model) if model else NvidiaLLM()
        return llm, "nvidia", llm.model
    raise ValueError(f"unknown --llm {kind!r} (expected 'mock' or 'nvidia')")


def _load_dataset(kind: str):
    if kind == "synthetic":
        from autocarto.demo_data import load_atlanta_dataset
        return load_atlanta_dataset()
    if kind == "real":
        from autocarto.real_data import load_real_atlanta_dataset
        return load_real_atlanta_dataset()
    raise ValueError(f"unknown --data {kind!r} (expected 'synthetic' or 'real')")


def main(argv: List[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="autocarto run",
        description="Run the Propose-Verify-Execute orchestrator end to end.",
    )
    parser.add_argument("prompt", type=str, help="Natural-language mapping request")
    parser.add_argument("--out", type=Path, default=Path("output") / "run",
                        help="Output directory (default: ./output/run)")
    parser.add_argument("--seed", type=int, default=0, help="Random seed (default: 0)")
    parser.add_argument("--max-iter", type=int, default=3, help="Max mandate iterations (default: 3)")
    parser.add_argument("--llm", choices=["mock", "nvidia"], default="mock",
                        help="LLM backend (default: mock — offline, no key)")
    parser.add_argument("--model", type=str, default=None,
                        help="Model id for --llm nvidia (default: meta/llama-3.1-70b-instruct)")
    parser.add_argument("--data", choices=["synthetic", "real"], default="synthetic",
                        help="Atlanta dataset: synthetic SAR (default) or real ACS+CDC")
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from autocarto.orchestrator import Orchestrator
        llm, provider, model_id = _build_llm(args.llm, args.model)
        dataset = _load_dataset(args.data)
    except (RuntimeError, ValueError) as exc:
        print(f"autocarto run: {exc}", file=sys.stderr)
        return 1

    print("AutoCarto-Agent orchestrator run")
    print(f"  prompt:   {args.prompt!r}")
    print(f"  llm:      {provider} ({model_id})")
    print(f"  data:     {args.data}")
    print(f"  seed:     {args.seed}   max_iter: {args.max_iter}")

    t0 = time.time()
    print(f"  dataset:  {dataset.description}")

    orchestrator = Orchestrator(llm=llm, max_iter=args.max_iter, seed=args.seed)
    result = orchestrator.run(args.prompt, dataset)
    elapsed_ms = (time.time() - t0) * 1000

    # Record run provenance in the trace header (llm provider/model/data source).
    result.trace["llm_provider"] = provider
    result.trace["llm_model"] = model_id
    result.trace["data_source"] = args.data

    print()
    for it in result.trace["iterations"]:
        gs = it["gate_suite"]
        print(f"  iteration {it['iteration']}: {gs['decision']} "
              f"(map_type={it['proposal']['map_type']}, "
              f"method={it['proposal']['classification_method']}, "
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
