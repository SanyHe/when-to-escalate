import pytest

from gen_tasks import build_tasks
from pricing import load_pricing, summarize_records
from replay import POLICIES, build_ledger
from router import load_policy


@pytest.fixture(scope="module")
def ledger():
    tasks = build_tasks(total=100, seed=20261107)
    return build_ledger(tasks, load_pricing(), load_policy())


def test_ledger_covers_all_three_policies(ledger):
    for policy_name in POLICIES:
        assert policy_name in ledger["metrics"]
        assert len(ledger["traces"][policy_name]) == 100


def test_cascade_is_cheaper_and_not_less_successful(ledger):
    frontier = ledger["metrics"]["all_frontier"]
    cascade = ledger["metrics"]["cascade"]
    assert cascade["total_cost_usd"] < frontier["total_cost_usd"]
    assert cascade["savings_vs_frontier"] >= 0.20
    assert cascade["success_rate"] >= frontier["success_rate"]


def test_cascade_escalates_some_tasks(ledger):
    cascade = ledger["metrics"]["cascade"]
    assert 0 < cascade["escalation_rate"] < 1


def test_all_small_is_cheapest_but_least_successful(ledger):
    frontier = ledger["metrics"]["all_frontier"]
    cascade = ledger["metrics"]["cascade"]
    small = ledger["metrics"]["all_small"]
    assert small["total_cost_usd"] < cascade["total_cost_usd"] < frontier["total_cost_usd"]
    assert small["success_rate"] < frontier["success_rate"]


def test_metrics_are_consistent_with_task_records(ledger):
    for policy_name in POLICIES:
        records = [t["cost_record"] for t in ledger["traces"][policy_name]]
        expected = summarize_records(records)
        actual = ledger["metrics"][policy_name]
        assert actual["total_cost_usd"] == pytest.approx(expected["total_cost_usd"])
        assert actual["cpst_usd"] == pytest.approx(expected["cpst_usd"])
        assert actual["success_rate"] == pytest.approx(expected["success_rate"])


def test_every_task_rolls_up_costs_from_all_attempts(ledger):
    for policy_name in POLICIES:
        for trace in ledger["traces"][policy_name]:
            record = trace["cost_record"]
            assert record["attempts"] == len(trace["responses"])
            assert record["cost_usd"] >= 0
            if record["success"]:
                assert record["cost_per_successful_task_usd"] == record["cost_usd"]
            else:
                assert record["cost_per_successful_task_usd"] == 0


def test_web_payload_contains_raw_attempts_for_recomputation(ledger):
    assert len(ledger["tasks"]) == 100
    for entry in ledger["tasks"]:
        assert 0 <= entry["confidence"] <= 1
        assert len(entry["attempts"]["small"]) >= 2
        assert len(entry["attempts"]["frontier"]) == 1
    assert ledger["_meta"]["mode"] == "mock"
