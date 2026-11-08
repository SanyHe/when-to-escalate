import pytest

from pricing import (
    PricingError,
    call_cost,
    cpst_from_records,
    expected_attempts,
    load_pricing,
    retry_premium,
    savings_ratio,
    summarize_records,
)

USAGE = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}

RECORDS = [
    {"success": True, "cost_usd": 0.004, "attempts": 1},
    {"success": True, "cost_usd": 0.006, "attempts": 2},
    {"success": False, "cost_usd": 0.002, "attempts": 2},
]


def test_cost_matches_hand_calculation():
    pricing = load_pricing()
    # small: 1000 * 0.15/1M + 500 * 0.60/1M = 0.00015 + 0.00030
    assert call_cost(USAGE, "small", pricing) == pytest.approx(0.00045)
    # frontier: 1000 * 3/1M + 500 * 12/1M = 0.003 + 0.006
    assert call_cost(USAGE, "frontier", pricing) == pytest.approx(0.009)


def test_zero_usage_costs_zero():
    pricing = load_pricing()
    zero = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    assert call_cost(zero, "frontier", pricing) == 0.0


def test_unknown_model_pricing_raises():
    pricing = load_pricing()
    with pytest.raises(PricingError):
        call_cost(USAGE, "large", pricing)


def test_retry_premium_for_p_070():
    assert expected_attempts(0.70) == pytest.approx(1.428571, rel=1e-4)
    assert retry_premium(0.70) == pytest.approx(0.428571, rel=1e-4)
    # 43% premium is the figure derived in docs/02-method.md section 4.
    assert round(retry_premium(0.70) * 100) == 43


def test_retry_premium_edge_cases():
    assert expected_attempts(1.0) == 1.0
    assert retry_premium(1.0) == 0.0
    assert expected_attempts(0.0) == float("inf")


def test_cpst_counts_only_successful_tasks():
    assert cpst_from_records(RECORDS) == pytest.approx((0.004 + 0.006) / 2)
    assert cpst_from_records([]) == 0.0


def test_summarize_records_includes_failed_spend():
    summary = summarize_records(RECORDS)
    assert summary["tasks"] == 3
    assert summary["total_cost_usd"] == pytest.approx(0.012)
    assert summary["failed_cost_usd"] == pytest.approx(0.002)
    assert summary["success_rate"] == pytest.approx(2 / 3, rel=1e-5)
    assert summary["avg_attempts"] == pytest.approx(5 / 3, rel=1e-4)


def test_savings_ratio():
    assert savings_ratio(0.25, 0.06) == pytest.approx(0.76)
    assert savings_ratio(0, 0.06) == 0.0
