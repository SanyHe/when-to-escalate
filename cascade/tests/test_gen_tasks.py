import json

from gen_tasks import build_tasks
from schema import validate_task


def test_seed_flow_has_expected_class_and_kind_mix():
    tasks = build_tasks(total=100, seed=20261107)
    assert len(tasks) == 100

    class_distribution = {
        task_class: sum(1 for task in tasks if task["task_class"] == task_class)
        for task_class in ("should_refuse", "small_sufficient", "frontier_required")
    }
    assert class_distribution == {
        "should_refuse": 20,
        "small_sufficient": 50,
        "frontier_required": 30,
    }

    kind_distribution = {
        kind: sum(1 for task in tasks if task["kind"] == kind)
        for kind in ("simple", "medium", "complex")
    }
    assert kind_distribution == {"simple": 50, "medium": 30, "complex": 20}


def test_all_tasks_are_valid_and_unique():
    tasks = build_tasks(total=100, seed=20261107)
    assert len({task["task_id"] for task in tasks}) == 100
    assert len({task["prompt"] for task in tasks}) == 100
    for task in tasks:
        assert validate_task(task)
        assert task["verification"]["type"] in {
            "exact_match", "field_match", "regex", "json_schema",
            "refusal", "llm_judge",
        }


def test_should_refuse_tasks_use_the_refusal_verifier():
    tasks = build_tasks()
    refusing = [task for task in tasks if task["task_class"] == "should_refuse"]
    assert refusing
    assert all(task["verification"]["type"] == "refusal" for task in refusing)


def test_small_sufficient_tasks_have_a_deterministic_verifier():
    tasks = build_tasks()
    solvable = [task for task in tasks if task["task_class"] == "small_sufficient"]
    assert solvable
    deterministic = {
        "exact_match", "field_match", "regex", "json_schema",
    }
    assert all(task["verification"]["type"] in deterministic for task in solvable)


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
