"""Metric semantics for the offline router-ceiling analysis.

These lock the two mistakes that are easy to make in cost comparisons:
paying the small model inside an all-frontier baseline, and picking the
cheapest CPST regardless of how many tasks actually succeed.
"""
import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, _SRC)

from router_ceiling import best_at_matched_success, policy_metrics  # noqa: E402


def _rows():
    return [
        {"small_cost": 0.001, "frontier_cost": 0.010,
         "small_pass": 1, "frontier_pass": 1},
        {"small_cost": 0.001, "frontier_cost": 0.010,
         "small_pass": 0, "frontier_pass": 1},
        {"small_cost": 0.001, "frontier_cost": 0.010,
         "small_pass": 0, "frontier_pass": 0},
    ]


def test_all_frontier_baseline_does_not_pay_the_small_attempt():
    metrics = policy_metrics(_rows(), [True, True, True], include_small=False)

    assert metrics["total_cost_usd"] == 0.03
    assert metrics["success_rate"] == 2 / 3
    assert metrics["cpst_usd"] == 0.01


def test_cascade_pays_both_attempts_on_escalation():
    metrics = policy_metrics(_rows(), [False, True, False])

    # Rows: 0.001 + (0.001+0.010) + 0.001; success on rows 1 and 2.
    assert metrics["total_cost_usd"] == 0.013
    assert metrics["success_rate"] == 2 / 3
    assert metrics["cpst_usd"] == 0.006
    assert metrics["escalation_rate"] == 1 / 3


def test_cheapest_cpst_alone_would_pick_the_do_nothing_policy():
    """Escalating nothing has the lowest CPST, so success must gate the choice."""
    curve = [
        {"threshold": 0.05, "success_rate": 0.33, "cpst_usd": 0.001, "total_cost_usd": 0.003},
        {"threshold": 0.90, "success_rate": 0.67, "cpst_usd": 0.006, "total_cost_usd": 0.012},
    ]

    assert best_at_matched_success(curve, 0.67)["threshold"] == 0.90
    assert best_at_matched_success(curve, 0.99) is None
