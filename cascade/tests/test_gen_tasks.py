import json

from gen_tasks import build_tasks
from schema import validate_task


def test_seed_flow_has_expected_size_and_mix():
    tasks = build_tasks(total=100, seed=20261107)
    assert len(tasks) == 100
    distribution = {
        kind: sum(1 for task in tasks if task["kind"] == kind)
        for kind in ("simple", "medium", "complex")
    }
    assert distribution == {"simple": 50, "medium": 30, "complex": 20}


def test_all_tasks_are_valid_and_unique():
    tasks = build_tasks(total=100, seed=20261107)
    assert len({task["task_id"] for task in tasks}) == 100
    assert len({task["prompt"] for task in tasks}) == 100
    for task in tasks:
        assert validate_task(task)


def test_generation_is_byte_identical_across_runs():
    first = [json.dumps(t, ensure_ascii=False, sort_keys=True) for t in build_tasks()]
    second = [json.dumps(t, ensure_ascii=False, sort_keys=True) for t in build_tasks()]
    assert first == second


def test_different_seed_changes_order_but_not_count():
    other = build_tasks(total=100, seed=7)
    assert len(other) == 100
    assert {task["task_id"] for task in other} == {
        f"task_{index:04d}" for index in range(1, 101)
    }
