import pytest

from personal_policy import (
    PersonalPolicyError,
    assign_bucket,
    bucket_is_routable,
    check_promotion,
    load_personal_policy,
)

CONFIG = load_personal_policy()


def decision(**overrides):
    base = {"consequence": "read", "latency": "interactive", "load": "single_tool"}
    base.update(overrides)
    return base


def test_base_bucket_mapping():
    assert assign_bucket(decision(load="sensing"), CONFIG)["bucket"] == "B0_sense"
    assert assign_bucket(decision(), CONFIG)["bucket"] == "B1_read"
    assert assign_bucket(decision(consequence="suggest"), CONFIG)["bucket"] == "B2_draft"
    assert (
        assign_bucket(decision(consequence="write_reversible"), CONFIG)["bucket"]
        == "B3_act_reversible"
    )
    assert (
        assign_bucket(decision(consequence="write_irreversible"), CONFIG)["bucket"]
        == "B4_act_irreversible"
    )
    assert (
        assign_bucket(decision(latency="background"), CONFIG)["bucket"]
        == "B5_background"
    )


def test_low_consequence_confidence_steps_up():
    result = assign_bucket(
        decision(consequence="read", consequence_confidence=0.5), CONFIG
    )
    assert result["bucket"] == "B2_draft"
    assert result["requested_bucket"] == "B2_draft"


def test_absent_user_queues_irreversible_action():
    result = assign_bucket(
        decision(consequence="write_irreversible", user_present=False), CONFIG
    )
    assert result["queue_for_confirmation"] is True
    assert result["confirmation"] == "required"
    assert "presence:absent" in result["overrides"]


def test_local_only_uses_local_model_without_escalation():
    result = assign_bucket(
        decision(consequence="suggest", sensitivity="local_only"), CONFIG
    )
    assert result["model"] == "local"
    assert result["escalate"] is False
    assert "sensitivity:local_only" in result["overrides"]


def test_missing_local_model_queues_the_decision():
    result = assign_bucket(
        decision(
            consequence="suggest",
            sensitivity="local_only",
            local_model_available=False,
        ),
        CONFIG,
    )
    assert result["queue_for_confirmation"] is True
    assert result["deferred"] is True


def test_exhausted_budget_defers_irreversible_action():
    result = assign_bucket(
        decision(consequence="write_irreversible", budget_exhausted=True), CONFIG
    )
    assert result["deferred"] is True
    assert result["bucket"] == "B4_act_irreversible"
    assert "budget:exhausted" in result["overrides"]


def test_exhausted_budget_keeps_cheap_draft():
    result = assign_bucket(
        decision(consequence="suggest", budget_exhausted=True), CONFIG
    )
    assert result["deferred"] is False


def test_degraded_device_defers_paid_work_to_background():
    result = assign_bucket(decision(device="low_battery"), CONFIG)
    assert result["bucket"] == "B5_background"
    assert result["deferred"] is True
    assert "device:low_battery" in result["overrides"]


def test_degraded_device_keeps_rule_based_sensing():
    result = assign_bucket(decision(load="sensing", device="weak_network"), CONFIG)
    assert result["bucket"] == "B0_sense"
    assert result["deferred"] is False


def test_invalid_decision_is_rejected():
    with pytest.raises(PersonalPolicyError):
        assign_bucket({"consequence": "unknown", "latency": "interactive",
                       "load": "single_tool"}, CONFIG)


def test_only_enabled_buckets_are_routable():
    assert bucket_is_routable("B2_draft", CONFIG) is True
    assert bucket_is_routable("B3_act_reversible", CONFIG) is True
    assert bucket_is_routable("B1_read", CONFIG) is False
    assert bucket_is_routable("B4_act_irreversible", CONFIG) is False


def test_promotion_requires_every_gate():
    passing = {
        "decisions": 320,
        "verifier_coverage": 0.92,
        "small_accept_rate": 0.85,
        "cost_reduction": 0.12,
        "error_rate_ratio": 1.1,
    }
    assert check_promotion(passing, CONFIG)["eligible"] is True

    failing = dict(passing, small_accept_rate=0.7)
    result = check_promotion(failing, CONFIG)
    assert result["eligible"] is False
    assert result["checks"]["small_accept_rate"]["passed"] is False
