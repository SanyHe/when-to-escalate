import copy

import pytest

from schema import (
    validate_cost_record,
    validate_model_response,
    validate_route_decision,
    validate_task,
)

TASK = {
    "task_id": "task_0001",
    "kind": "simple",
    "prompt": "今天东莞天气怎么样？需要带伞吗？",
    "expected_difficulty": "low",
    "tags": ["weather", "entity_extraction"],
    "created_at": "2026-11-04T09:00:00+08:00",
}

ROUTE_CASCADE = {
    "task_id": "task_0001",
    "policy": "cascade",
    "selected_model": "small",
    "confidence": 0.93,
    "escalated": False,
    "reason": "cascade: start on the small model",
}

ROUTE_ESCALATED = {
    "task_id": "task_0001",
    "policy": "cascade",
    "selected_model": "frontier",
    "confidence": 1.0,
    "escalated": True,
    "reason": "fallback: the small model failed",
}

RESPONSE = {
    "task_id": "task_0001",
    "model": "small",
    "content": "今天多云有阵雨，建议带伞。",
    "success": True,
    "latency_ms": 180,
    "usage": {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60},
}

RECORD = {
    "task_id": "task_0001",
    "model": "small",
    "attempts": 1,
    "cost_usd": 0.0006,
    "latency_ms": 180,
    "success": True,
    "cost_per_successful_task_usd": 0.0006,
}


def test_valid_objects_pass():
    assert validate_task(TASK)
    assert validate_route_decision(ROUTE_CASCADE)
    assert validate_route_decision(ROUTE_ESCALATED)
    assert validate_model_response(RESPONSE)
    assert validate_cost_record(RECORD)


def test_task_rejects_missing_and_extra_fields():
    missing = copy.deepcopy(TASK)
    del missing["tags"]
    assert not validate_task(missing)

    extra = copy.deepcopy(TASK)
    extra["secret"] = "nope"
    assert not validate_task(extra)


def test_task_rejects_bad_enum_and_timestamp():
    bad_kind = copy.deepcopy(TASK)
    bad_kind["kind"] = "hard"
    assert not validate_task(bad_kind)

    bad_time = copy.deepcopy(TASK)
    bad_time["created_at"] = "2026-11-04 09:00:00"
    assert not validate_task(bad_time)


def test_route_policy_rules_are_enforced():
    wrong_frontier = copy.deepcopy(ROUTE_CASCADE)
    wrong_frontier["policy"] = "all_frontier"
    assert not validate_route_decision(wrong_frontier)

    wrong_small = copy.deepcopy(ROUTE_CASCADE)
    wrong_small["policy"] = "all_small"
    wrong_small["escalated"] = True
    wrong_small["selected_model"] = "frontier"
    assert not validate_route_decision(wrong_small)

    escalation_to_small = copy.deepcopy(ROUTE_ESCALATED)
    escalation_to_small["selected_model"] = "small"
    assert not validate_route_decision(escalation_to_small)


def test_route_confidence_bounds():
    too_high = copy.deepcopy(ROUTE_CASCADE)
    too_high["confidence"] = 1.5
    assert not validate_route_decision(too_high)


def test_model_response_accepts_optional_confidence_and_bounds_it():
    assert validate_model_response(dict(RESPONSE, confidence=0.86))

    assert not validate_model_response(dict(RESPONSE, confidence=1.5))
    assert not validate_model_response(dict(RESPONSE, confidence=-0.1))


def test_model_response_token_sum_is_checked():
    mismatch = copy.deepcopy(RESPONSE)
    mismatch["usage"]["total_tokens"] = 61
    result = validate_model_response(mismatch)
    assert not result
    assert "total_tokens" in result.errors[0]


def test_cost_record_failed_task_has_zero_cpst():
    failed = copy.deepcopy(RECORD)
    failed["success"] = False
    failed["cost_per_successful_task_usd"] = 0.0
    assert validate_cost_record(failed)

    failed_nonzero = copy.deepcopy(RECORD)
    failed_nonzero["success"] = False
    assert not validate_cost_record(failed_nonzero)


def test_cost_record_successful_task_cannot_zero_out_cpst():
    zeroed = copy.deepcopy(RECORD)
    zeroed["cost_per_successful_task_usd"] = 0.0
    result = validate_cost_record(zeroed)
    assert not result


@pytest.mark.parametrize("bad", [[], "task", None, 42])
def test_non_object_payloads_are_rejected(bad):
    assert not validate_task(bad)
