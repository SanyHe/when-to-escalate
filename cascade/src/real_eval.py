"""
Real-backend three-policy evaluation (F2.5).

Runs the same deterministic task sample through all_frontier / cascade /
all_small against real OpenAI-compatible backends, then writes a ledger that
is kept separate from the mock ledger:

  data/eval/real_ledger.json     full traces + metrics (machine readable)
  data/eval/real_ledger.md       comparison table (human readable)

Credentials and endpoints come from environment variables only (see
docs/02-method.md section 7). Nothing is written back to the mock ledger or
the web panel, so mock and real numbers never mix.

Usage (repo root):
    DASHSCOPE_API_KEY=... CASCADE_SMALL_MODEL=qwen-plus \
        python3 cascade/src/real_eval.py --limit 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

from backends import backends_from_env, bailian_backends  # noqa: E402
from engine import CascadeEngine, aggregate  # noqa: E402
from pricing import load_pricing, savings_ratio  # noqa: E402
from replay import load_tasks, _write_json  # noqa: E402
from router import load_policy  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
DEFAULT_TASKS = os.path.join(REPO_ROOT, "data", "synthetic", "seed_tasks.jsonl")
DEFAULT_OUT = os.path.join(REPO_ROOT, "data", "eval", "real_ledger.json")
DEFAULT_MD = os.path.join(REPO_ROOT, "data", "eval", "real_ledger.md")
DEFAULT_PRICING = os.path.join(REPO_ROOT, "cascade", "configs", "pricing.yaml")

POLICIES = ("all_frontier", "cascade", "all_small")


def sample_tasks(tasks: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Pick ``limit`` tasks spread across the full flow.

    Even spacing keeps the simple/medium/complex mix closer to the full
    distribution than simply taking the first N tasks.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if limit >= len(tasks):
        return list(tasks)
    step = len(tasks) / float(limit)
    return [tasks[int(index * step)] for index in range(limit)]


def build_backends(timeout_s: float) -> Dict[str, Any]:
    """Build real backends from environment; never accept hard-coded keys."""
    if os.environ.get("CASCADE_SMALL_BASE_URL"):
        backends = backends_from_env()
    elif os.environ.get("DASHSCOPE_API_KEY"):
        backends = bailian_backends(timeout_s=timeout_s)
    else:
        raise RuntimeError(
            "Set DASHSCOPE_API_KEY (Bailian) or CASCADE_SMALL_BASE_URL "
            "plus CASCADE_FRONTIER_BASE_URL (self-hosted) before running."
        )
    for backend in backends.values():
        backend.timeout_s = timeout_s
    return backends


def build_ledger(tasks: List[Dict[str, Any]], pricing: Dict[str, Any],
                 policy: Dict[str, Any], backends: Dict[str, Any],
                 limit: int, sleep_s: float,
                 pricing_path: str = "cascade/configs/pricing.yaml",
                 max_tokens: int | None = None) -> Dict[str, Any]:
    subset = sample_tasks(tasks, limit)
    traces: Dict[str, List[Dict[str, Any]]] = {}
    metrics: Dict[str, Dict[str, Any]] = {}

    for policy_name in POLICIES:
        engine = CascadeEngine(backends, pricing, policy, policy_name)
        traces[policy_name] = []
        print(f"[{policy_name}] {len(subset)} tasks", flush=True)
        for index, task in enumerate(subset, 1):
            traces[policy_name].append(engine.run_task(task))
            print(
                f"  {index}/{len(subset)} {task['task_id']} "
                f"({task['kind']}/{task['expected_difficulty']})",
                flush=True,
            )
            if sleep_s:
                time.sleep(sleep_s)
        metrics[policy_name] = aggregate(traces[policy_name])

    frontier_cost = metrics["all_frontier"]["total_cost_usd"]
    for summary in metrics.values():
        summary["savings_vs_frontier"] = savings_ratio(
            frontier_cost, summary["total_cost_usd"]
        )

    return {
        "_meta": {
            "mode": "real",
            "note": (
                "REAL LEDGER: measured against live OpenAI-compatible backends. "
                "Do not compare or merge with mock_ledger.json."
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task_file": os.path.relpath(DEFAULT_TASKS, REPO_ROOT),
            "task_count": len(subset),
            "sampled_task_ids": [task["task_id"] for task in subset],
            "max_tokens": max_tokens,
            "policies": list(POLICIES),
            "backends": {
                "small": os.environ.get("CASCADE_SMALL_MODEL", "qwen-turbo"),
                "frontier": os.environ.get("CASCADE_FRONTIER_MODEL", "qwen-max"),
            },
            "pricing": pricing["models"],
            "pricing_file": pricing_path,
            "pricing_note": (
                "Prices come from the file named in pricing_file. Verify the "
                "FX assumption and official prices before quoting cost."
            ),
            "policy": {
                "confidence_threshold": policy["confidence_threshold"],
                "confidence_by_difficulty": policy["confidence_by_difficulty"],
                "max_attempts": policy["max_attempts"],
            },
        },
        "traces": traces,
        "metrics": metrics,
    }


def render_markdown(ledger: Dict[str, Any]) -> str:
    meta = ledger["_meta"]
    lines = [
        "# Cascade Ledger (REAL)",
        "",
        f"> {meta['note']}",
        f"> Backends: `{meta['backends']['small']}` -> `{meta['backends']['frontier']}`",
        f"> Sample: {meta['task_count']} tasks, generated at {meta['generated_at']}",
        f"> Prices: {meta['pricing_note']} (`{meta['pricing_file']}`)",
        "",
        "| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    if meta.get("max_tokens"):
        lines.insert(
            6,
            f"> Output budget: {meta['max_tokens']} completion tokens per call "
            "(same for both roles)",
        )
    for policy_name in POLICIES:
        m = ledger["metrics"][policy_name]
        lines.append(
            f"| {policy_name} | {m['tasks']} | ${m['total_cost_usd']:.6f} | "
            f"${m['cpst_usd']:.6f} | {m['success_rate']:.2%} | "
            f"{m['escalation_rate']:.2%} | {m['avg_latency_ms']:.0f} ms | "
            f"{m['avg_attempts']:.3f} | {m['savings_vs_frontier']:.2%} |"
        )
    lines += [
        "",
        "> CPST = total cost of successful tasks / successful tasks; retry and "
        "escalation spend is included. Real-model cost figures depend on the "
        "prices configured in `cascade/configs/pricing.yaml`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default=DEFAULT_TASKS)
    parser.add_argument("--limit", type=int, default=10,
                        help="number of tasks per policy (spread across the flow)")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="seconds between calls to avoid provider rate limits")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="per-request timeout in seconds")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--md-out", default=DEFAULT_MD)
    parser.add_argument("--pricing", default=DEFAULT_PRICING,
                        help="pricing file; use pricing.qwen.yaml for real quotes")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="shared completion budget for both roles; keeps the "
                             "cost comparison from being driven by verbosity")
    args = parser.parse_args()

    tasks = load_tasks(args.tasks)
    pricing = load_pricing(args.pricing)
    policy = load_policy()
    backends = build_backends(args.timeout)
    if args.max_tokens is not None:
        for backend in backends.values():
            backend.max_tokens = args.max_tokens
    ledger = build_ledger(
        tasks, pricing, policy, backends, args.limit, args.sleep,
        pricing_path=os.path.relpath(args.pricing, REPO_ROOT),
        max_tokens=args.max_tokens,
    )

    _write_json(args.out, ledger)
    with open(args.md_out, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(ledger))

    print(f"\ntasks: {ledger['_meta']['task_count']} | mode: REAL")
    for policy_name in POLICIES:
        m = ledger["metrics"][policy_name]
        print(
            f"  {policy_name:<12} cost=${m['total_cost_usd']:.6f} "
            f"cpst=${m['cpst_usd']:.6f} success={m['success_rate']:.2%} "
            f"escalation={m['escalation_rate']:.2%} "
            f"savings={m['savings_vs_frontier']:.2%}"
        )
    print(f"ledger -> {args.out}")
    print(f"table  -> {args.md_out}")


if __name__ == "__main__":
    main()
