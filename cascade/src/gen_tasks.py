"""
Deterministic synthetic task-flow generator (F1.5).

Builds ~100 tasks from data/templates/task_templates.json using the task mix
in cascade/configs/policy.yaml. Every task gets a unique task_id, a stable
created_at timestamp and a prompt with a serial marker, so two runs with the
same seed produce byte-identical JSONL.

Usage (repo root):
    python3 cascade/src/gen_tasks.py
    python3 cascade/src/gen_tasks.py --out data/synthetic/seed_tasks.jsonl --seed 20261107
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

from router import DEFAULT_POLICY_PATH, load_policy  # noqa: E402
from schema import validate_task  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
DEFAULT_TEMPLATES = os.path.join(REPO_ROOT, "data", "templates", "task_templates.json")
DEFAULT_OUT = os.path.join(REPO_ROOT, "data", "synthetic", "seed_tasks.jsonl")

DIFFICULTY_BY_KIND = {"simple": "low", "medium": "medium", "complex": "high"}


def load_templates(path: str = DEFAULT_TEMPLATES) -> Dict[str, List[Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8") as handle:
        templates = json.load(handle)
    for kind in ("simple", "medium", "complex"):
        if not templates.get(kind):
            raise ValueError(f"{path}: missing templates for kind '{kind}'")
    return templates


def _mix_counts(policy: Dict[str, Any], total: int) -> Dict[str, int]:
    """Scale the configured task mix so the counts sum exactly to ``total``."""
    mix = policy["task_mix"]
    base_total = sum(int(mix[kind]) for kind in ("simple", "medium", "complex"))
    counts = {
        kind: int(round(total * int(mix[kind]) / base_total))
        for kind in ("simple", "medium", "complex")
    }
    # Rounding can drift by a task or two; fix on the largest bucket.
    drift = total - sum(counts.values())
    counts["medium"] += drift
    return counts


def build_tasks(total: int = 100, seed: int = 20261107,
                policy_path: str = DEFAULT_POLICY_PATH,
                templates_path: str = DEFAULT_TEMPLATES) -> List[Dict[str, Any]]:
    policy = load_policy(policy_path)
    templates = load_templates(templates_path)
    rng = random.Random(seed)
    counts = _mix_counts(policy, total)

    kinds: List[str] = []
    for kind in ("simple", "medium", "complex"):
        kinds.extend([kind] * counts[kind])
    rng.shuffle(kinds)

    start = datetime(2026, 11, 4, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    tasks: List[Dict[str, Any]] = []
    template_cursor = {kind: 0 for kind in counts}
    for index, kind in enumerate(kinds, start=1):
        pool = templates[kind]
        template = pool[template_cursor[kind] % len(pool)]
        template_cursor[kind] += 1
        task = {
            "task_id": f"task_{index:04d}",
            "kind": kind,
            "prompt": f"{template['prompt']}（任务编号 {index:03d}）",
            "expected_difficulty": DIFFICULTY_BY_KIND[kind],
            "tags": list(template["tags"]),
            "created_at": (start + timedelta(minutes=index)).isoformat(),
        }
        result = validate_task(task)
        if not result.valid:
            raise ValueError(f"generated invalid task {task['task_id']}: {result.errors}")
        tasks.append(task)
    return tasks


def write_jsonl(path: str, items: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--total", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261107)
    args = parser.parse_args()

    tasks = build_tasks(total=args.total, seed=args.seed)
    write_jsonl(args.out, tasks)

    distribution: Dict[str, int] = {}
    for task in tasks:
        distribution[task["kind"]] = distribution.get(task["kind"], 0) + 1
    print(f"wrote {len(tasks)} tasks -> {os.path.relpath(args.out, REPO_ROOT)}")
    print(f"kind distribution: {distribution}")
    print(f"unique task ids: {len({t['task_id'] for t in tasks})}")


if __name__ == "__main__":
    main()
