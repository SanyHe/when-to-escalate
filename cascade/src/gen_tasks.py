"""
Deterministic synthetic task-flow generator (F1.5 / F2.5).

Builds ~100 tasks from data/templates/task_templates.json using the class mix
in cascade/configs/policy.yaml. Every task carries a ``task_class`` and a
``verification`` spec so the evaluator can grade it deterministically (or fall
back to an LLM judge where no deterministic check exists).

Every task gets a unique task_id, a stable created_at timestamp and a prompt
with a serial marker, so two runs with the same seed produce byte-identical
JSONL.

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
from schema import TASK_CLASSES, validate_task  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
DEFAULT_TEMPLATES = os.path.join(REPO_ROOT, "data", "templates", "task_templates.json")
DEFAULT_OUT = os.path.join(REPO_ROOT, "data", "synthetic", "seed_tasks.jsonl")

DIFFICULTY_BY_KIND = {"simple": "low", "medium": "medium", "complex": "high"}
KIND_ORDER = ("simple", "medium", "complex")


def load_templates(path: str = DEFAULT_TEMPLATES) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        templates = json.load(handle)
    classes = templates.get("classes")
    if not isinstance(classes, dict):
        raise ValueError(f"{path}: missing 'classes' object")
    for task_class in TASK_CLASSES:
        pools = classes.get(task_class)
        if not isinstance(pools, dict):
            raise ValueError(f"{path}: missing class '{task_class}'")
        for kind in KIND_ORDER:
            pool = pools.get(kind)
            if not pool:
                # A class does not have to span every kind, but a configured
                # (class, kind) pair must have at least one template.
                continue
            for entry in pool:
                for key in ("prompt", "tags", "verification"):
                    if key not in entry:
                        raise ValueError(
                            f"{path}: {task_class}/{kind} template missing '{key}'"
                        )
    return templates


def _scale_mix(weights: Dict[str, int], total: int) -> Dict[str, int]:
    """Scale weights so the counts sum exactly to ``total`` (largest remainder)."""
    base = sum(int(value) for value in weights.values())
    if base <= 0:
        raise ValueError(f"mix weights must be positive: {weights}")
    order = list(weights)
    raw = {key: total * int(weights[key]) / base for key in order}
    counts = {key: int(raw[key]) for key in order}
    drift = total - sum(counts.values())
    for key in sorted(order, key=lambda k: (-(raw[k] - counts[k]), order.index(k))):
        if drift <= 0:
            break
        counts[key] += 1
        drift -= 1
    return counts


def build_tasks(total: int = 100, seed: int = 20261107,
                policy_path: str = DEFAULT_POLICY_PATH,
                templates_path: str = DEFAULT_TEMPLATES) -> List[Dict[str, Any]]:
    policy = load_policy(policy_path)
    templates = load_templates(templates_path)
    rng = random.Random(seed)

    class_counts = _scale_mix(policy["task_class_mix"], total)
    slots: List[tuple] = []
    for task_class in TASK_CLASSES:
        class_total = class_counts.get(task_class, 0)
        if class_total <= 0:
            continue
        kind_weights = policy["task_class_kind_mix"][task_class]
        kind_counts = _scale_mix(kind_weights, class_total)
        for kind in KIND_ORDER:
            slots.extend([(task_class, kind)] * kind_counts.get(kind, 0))
    rng.shuffle(slots)

    start = datetime(2026, 11, 4, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    tasks: List[Dict[str, Any]] = []
    cursors: Dict[tuple, int] = {}
    for index, (task_class, kind) in enumerate(slots, start=1):
        pool = templates["classes"][task_class].get(kind) or []
        if not pool:
            raise ValueError(
                f"{templates_path}: no templates for {task_class}/{kind}"
            )
        cursor = cursors.get((task_class, kind), 0)
        template = pool[cursor % len(pool)]
        cursors[(task_class, kind)] = cursor + 1
        task = {
            "task_id": f"task_{index:04d}",
            "kind": kind,
            "task_class": task_class,
            "prompt": f"{template['prompt']}（任务编号 {index:03d}）",
            "expected_difficulty": DIFFICULTY_BY_KIND[kind],
            "tags": list(template["tags"]),
            "verification": template["verification"],
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

    class_distribution: Dict[str, int] = {}
    kind_distribution: Dict[str, int] = {}
    verification_distribution: Dict[str, int] = {}
    for task in tasks:
        class_distribution[task["task_class"]] = (
            class_distribution.get(task["task_class"], 0) + 1
        )
        kind_distribution[task["kind"]] = kind_distribution.get(task["kind"], 0) + 1
        vtype = task["verification"]["type"]
        verification_distribution[vtype] = (
            verification_distribution.get(vtype, 0) + 1
        )
    print(f"wrote {len(tasks)} tasks -> {os.path.relpath(args.out, REPO_ROOT)}")
    print(f"task_class distribution: {class_distribution}")
    print(f"kind distribution: {kind_distribution}")
    print(f"verification distribution: {verification_distribution}")
    print(f"unique task ids: {len({t['task_id'] for t in tasks})}")


if __name__ == "__main__":
    main()
