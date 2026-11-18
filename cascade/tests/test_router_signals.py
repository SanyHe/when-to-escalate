"""Semantics of the offline routing-signal comparison.

These lock the two decisions that dominate the result: accepting a small
answer only when the deterministic verifier passes, and comparing policies
only at (or above) the frontier's success rate.
"""
import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, _SRC)

from router_signals import (  # noqa: E402
    _strip_task_number,
    best_at_matched_success,
    decide_confidence,
    decide_refusal_gate,
    decide_verifier,
    summarize,
)


def _row(**overrides):
    row = {
        "task_id": "t1",
        "task_class": "small_sufficient",
        "verification_type": "exact_match",
        "verifiable": True,
        "verifier_status": "passed",
        "small_cost": 0.001,
        "frontier_cost": 0.010,
        "small_pass": True,
        "frontier_pass": True,
        "confidence": 0.90,
        "confidence_missing": False,
    }
    row.update(overrides)
    return row


def test_escalation_pays_both_attempts_and_keeps_the_frontier_verdict():
    rows = [
        _row(small_pass=False, frontier_pass=True, verifier_status="failed"),
        _row(small_pass=False, frontier_pass=False, verifier_status="failed"),
    ]
    metrics = summarize(rows, ["escalate", "small"])

    # 0.011 for the escalated task, 0.001 for the task kept on small.
    assert metrics["total_cost_usd"] == 0.012
    assert metrics["passed"] == 1
    assert metrics["success_rate"] == 0.5
    assert metrics["escalation_rate"] == 0.5


def test_direct_frontier_decision_does_not_pay_the_small_attempt():
    metrics = summarize([_row()], ["frontier"])

    assert metrics["total_cost_usd"] == 0.010
    assert metrics["frontier_rate"] == 1.0
    assert metrics["escalation_rate"] == 0.0


def test_verifier_gate_accepts_a_pass_and_escalates_a_fail():
    assert decide_verifier(_row(verifier_status="passed"), 0.85) == "small"
    assert decide_verifier(_row(verifier_status="failed"), 0.85) == "escalate"


def test_verifier_gate_falls_back_to_confidence_when_unverifiable():
    low = _row(verifiable=False, verifier_status="needs_judge", confidence=0.70)

    assert decide_verifier(low, 0.85) == "escalate"
    assert decide_verifier(_row(verifiable=False, verifier_status="needs_judge",
                                confidence=0.95), 0.85) == "small"
    # Missing confidence is treated as no evidence and escalates.
    assert decide_verifier(_row(verifiable=False, verifier_status="needs_judge",
                                confidence=0.0, confidence_missing=True), 0.85) == "escalate"


def test_strict_verifier_gate_escalates_every_unverifiable_task():
    row = _row(verifiable=False, verifier_status="needs_judge", confidence=0.99)

    assert decide_verifier(row, 0.0, strict=True) == "escalate"


def test_refusal_gate_does_not_apply_gold_verifiers():
    # A failed exact_match check with high confidence stays on the small model:
    # the refusal-only policy does not trust gold comparisons.
    gold = _row(verification_type="exact_match", verifier_status="failed",
                confidence=0.95)
    assert decide_refusal_gate(gold, 0.85) == "small"
    # A failed refusal check escalates, and a passed one is accepted.
    refused = _row(verification_type="refusal", verifier_status="failed",
                   confidence=0.95)
    accepted = _row(verification_type="refusal", verifier_status="passed",
                    confidence=0.95)
    assert decide_refusal_gate(refused, 0.85) == "escalate"
    assert decide_refusal_gate(accepted, 0.85) == "small"


def test_confidence_gate_escalates_below_the_threshold():
    assert decide_confidence(_row(confidence=0.80), 0.85) == "escalate"
    assert decide_confidence(_row(confidence=0.90), 0.85) == "small"


def test_matched_success_rejects_cheap_low_success_points():
    curve = [
        {"parameter": 0.1, "success_rate": 0.50, "total_cost_usd": 0.002},
        {"parameter": 0.9, "success_rate": 0.90, "total_cost_usd": 0.006},
        {"parameter": 1.0, "success_rate": 0.95, "total_cost_usd": 0.009},
    ]

    assert best_at_matched_success(curve, 0.90)["parameter"] == 0.9
    assert best_at_matched_success(curve, 0.99) is None


def test_task_number_suffix_is_stripped_before_text_features():
    assert _strip_task_number("计算 128 乘以 24（任务编号 001）") == "计算 128 乘以 24"
