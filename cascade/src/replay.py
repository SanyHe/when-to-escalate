"""
Three-policy replay and ledger builder (F1.6 / M3 data source).

Runs the same synthetic task flow through all_frontier / cascade / all_small
using the deterministic mock backend, then writes:

  data/eval/mock_ledger.json     full traces + metrics (machine readable)
  data/eval/mock_ledger.md       comparison table (human readable)
  web/data/ledger.json           tasks + raw attempts for the static panel

The panel recomputes metrics client-side when price / threshold sliders move,
so the web payload includes the raw per-attempt results and never hides the
mock label.

Usage (repo root):
    python3 cascade/src/replay.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

from backends import mock_backends  # noqa: E402
from engine import CascadeEngine, aggregate  # noqa: E402
from pricing import load_pricing, savings_ratio  # noqa: E402
from router import load_policy, task_confidence  # noqa: E402
from schema import validate_route_decision, validate_task  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
DEFAULT_TASKS = os.path.join(REPO_ROOT, "data", "synthetic", "seed_tasks.jsonl")
DEFAULT_OUT = os.path.join(REPO_ROOT, "data", "eval", "mock_ledger.json")
DEFAULT_MD = os.path.join(REPO_ROOT, "data", "eval", "mock_ledger.md")
DEFAULT_WEB = os.path.join(REPO_ROOT, "web", "data", "ledger.json")

POLICIES = ("all_frontier", "cascade", "all_small")


def load_tasks(path: str = DEFAULT_TASKS) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        tasks = [json.loads(line) for line in handle if line.strip()]
    if not tasks:
        raise RuntimeError(f"empty task file: {path}")
    for task in tasks:
        result = validate_task(task)
        if not result.valid:
            raise RuntimeError(f"invalid task {task.get('task_id')}: {result.errors}")
    return tasks


def build_ledger(tasks: List[Dict[str, Any]], pricing: Dict[str, Any],
                 policy: Dict[str, Any]) -> Dict[str, Any]:
    traces: Dict[str, List[Dict[str, Any]]] = {}
    metrics: Dict[str, Dict[str, Any]] = {}
    for policy_name in POLICIES:
        engine = CascadeEngine(mock_backends(), pricing, policy, policy_name)
        traces[policy_name] = engine.run_policy(tasks)
        metrics[policy_name] = aggregate(traces[policy_name])

    frontier_cost = metrics["all_frontier"]["total_cost_usd"]
    for policy_name, summary in metrics.items():
        summary["savings_vs_frontier"] = savings_ratio(frontier_cost, summary["total_cost_usd"])

    # Raw attempts let the browser re-simulate policies when sliders move.
    probe = mock_backends()
    small_attempts = int(policy["max_attempts"]["all_small"])
    web_tasks = []
    for task in tasks:
        entry: Dict[str, Any] = {
            "task": task,
            "confidence": task_confidence(task, policy),
            "attempts": {
                "small": [probe["small"].complete(task, i) for i in range(1, small_attempts + 1)],
                "frontier": [probe["frontier"].complete(task, 1)],
            },
        }
        web_tasks.append(entry)

    return {
        "_meta": {
            "mode": "mock",
            "note": (
                "MOCK LEDGER: deterministic mock backend, not measured model "
                "output. Replace with real-backend evidence (F2.5) before "
                "quoting these numbers."
            ),
            "task_file": os.path.relpath(DEFAULT_TASKS, REPO_ROOT),
            "task_count": len(tasks),
            "policies": list(POLICIES),
            "pricing": pricing["models"],
            "pricing_note": "Illustrative example prices; verify before quoting.",
            "policy": {
                "confidence_threshold": policy["confidence_threshold"],
                "confidence_by_difficulty": policy["confidence_by_difficulty"],
                "max_attempts": policy["max_attempts"],
            },
            "kind_distribution": {
                kind: sum(1 for task in tasks if task["kind"] == kind)
                for kind in ("simple", "medium", "complex")
            },
        },
        "tasks": web_tasks,
        "traces": traces,
        "metrics": metrics,
    }


def render_markdown(ledger: Dict[str, Any]) -> str:
    lines = [
        "# Cascade Ledger (MOCK)",
        "",
        f"> {ledger['_meta']['note']}",
        f"> Prices: {ledger['_meta']['pricing_note']}",
        "",
        "| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
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
        "escalation spend is included.",
        "",
    ]
    return "\n".join(lines)


def _write_json(path: str, obj: Any, indent: int | None = 2) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=indent)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default=DEFAULT_TASKS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--md-out", default=DEFAULT_MD)
    parser.add_argument("--web-out", default=DEFAULT_WEB)
    args = parser.parse_args()

    tasks = load_tasks(args.tasks)
    ledger = build_ledger(tasks, load_pricing(), load_policy())
    _write_json(args.out, ledger)
    with open(args.md_out, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(ledger))
    _write_json(args.web_out, ledger, indent=None)

    print(f"tasks: {len(tasks)} | mode: MOCK")
    for policy_name in POLICIES:
        m = ledger["metrics"][policy_name]
        print(
            f"  {policy_name:<12} cost=${m['total_cost_usd']:.6f} "
            f"cpst=${m['cpst_usd']:.6f} success={m['success_rate']:.2%} "
            f"escalation={m['escalation_rate']:.2%} "
            f"savings={m['savings_vs_frontier']:.2%}"
        )
    print(f"ledger -> {args.out}")
    print(f"web    -> {args.web_out}")


if __name__ == "__main__":
    main()
