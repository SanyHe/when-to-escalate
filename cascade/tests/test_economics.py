"""The break-even inequality behind the cascade cost comparison.

A fail-then-escalate cascade wins exactly when the small model's cost ratio
falls below the share of frontier spend it avoids. These tests pin that rule
so a later lever (brevity, cheaper small model, task mix) cannot be claimed
without moving the right side of the inequality.
"""
import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, _SRC)

from economics import break_even, evaluate  # noqa: E402

PRICES = {
    "small": {"input": 1.0, "output": 2.0},
    "frontier": {"input": 10.0, "output": 20.0},
}


def _rows(small_completion: int = 100_000):
    """Two tasks with identical usage: one the small model passes, one not."""
    usage_small = {"prompt_tokens": 0, "completion_tokens": small_completion}
    usage_frontier = {"prompt_tokens": 100_000, "completion_tokens": 0}
    return [
        {"task_id": "a", "small_usage": usage_small, "frontier_usage": usage_frontier,
         "small_pass": True, "frontier_pass": True},
        {"task_id": "b", "small_usage": usage_small, "frontier_usage": usage_frontier,
         "small_pass": False, "frontier_pass": True},
    ]


def test_cascade_wins_when_cost_ratio_is_below_the_avoidable_share():
    metrics = evaluate(_rows(), PRICES)

    # Small 2 x $0.20, frontier 2 x $1.00, $1.00 avoidable on the passing task.
    assert metrics["cost_ratio"] == 0.2
    assert metrics["avoidable_share"] == 0.5
    assert metrics["cascade_total_usd"] == 1.4
    assert metrics["cascade_savings"] == 0.3
    assert metrics["success_rate"] == 1.0


def test_cascade_loses_when_the_small_attempt_costs_more_than_it_saves():
    metrics = evaluate(_rows(small_completion=300_000), PRICES)

    assert metrics["cost_ratio"] == 0.6
    assert metrics["cascade_total_usd"] == 2.2
    assert metrics["cascade_savings"] < 0


def test_brevity_lowers_only_the_output_side_of_the_ratio():
    metrics = evaluate(_rows(), PRICES, completion_scale=0.5)

    assert metrics["small_total_usd"] == 0.2
    assert metrics["frontier_total_usd"] == 2.0
    assert metrics["cost_ratio"] == 0.1
    assert metrics["cascade_savings"] == 0.4


def test_a_free_small_model_cannot_beat_the_avoidable_share():
    metrics = evaluate(_rows(), PRICES, price_factor=0.0)
    ceiling = break_even(_rows(), PRICES)["max_savings_at_zero_small_cost"]

    assert metrics["small_total_usd"] == 0.0
    assert metrics["cascade_savings"] == ceiling == 0.5
