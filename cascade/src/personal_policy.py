"""
Decision bucketing and hard constraints for an always-on personal agent.

This module answers one question before any model call: which policy applies to
this decision point? It is independent of the cascade engine and never calls a
model, so bucket assignment stays deterministic and testable.

Resolution order (first match wins):
  1. Hard constraints: privacy, device state, budget.
  2. Consequence: irreversible write > reversible write > suggestion > read.
  3. Latency: background work falls back to the batch bucket.
  4. Low classifier confidence steps the consequence up one bucket.

Usage (repo root):
    python3 cascade/src/personal_policy.py     # prints a self-check
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_PERSONAL_POLICY_PATH = os.path.join(
    REPO_ROOT, "cascade", "configs", "personal_policy.yaml"
)

CONSEQUENCES = ("read", "suggest", "write_reversible", "write_irreversible")
LATENCIES = ("interactive", "near_real_time", "background")
LOADS = ("sensing", "single_tool", "multi_step", "synthesis")
SENSITIVITIES = ("cloud_ok", "local_only")
DEVICES = ("normal", "low_battery", "weak_network")
MODELS = ("none", "small", "frontier", "local")
CONFIRMATIONS = ("none", "inline", "after_the_fact", "required")
VERIFIERS = ("none", "rule", "schema", "tool_result", "sample", "human")

_BUCKET_FIELDS = (
    "description",
    "model",
    "confirmation",
    "verifier",
    "escalate",
    "max_tokens",
    "latency_slo_ms",
    "batch",
    "retry",
)


class PersonalPolicyError(ValueError):
    """Raised when the bucket config or a decision payload is malformed."""


def load_personal_policy(path: str = DEFAULT_PERSONAL_POLICY_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    _check_config(config, path)
    return config


def _check_config(config: Any, source: str = "<memory>") -> None:
    if not isinstance(config, dict):
        raise PersonalPolicyError(f"{source}: config must be a mapping")

    floor = config.get("consequence_confidence_floor")
    if not isinstance(floor, (int, float)) or not 0 <= floor <= 1:
        raise PersonalPolicyError(
            f"{source}: consequence_confidence_floor must be in [0, 1]"
        )

    buckets = config.get("buckets")
    if not isinstance(buckets, dict) or not buckets:
        raise PersonalPolicyError(f"{source}: missing 'buckets'")
    for name, bucket in buckets.items():
        if not isinstance(bucket, dict):
            raise PersonalPolicyError(f"{source}: bucket {name} must be a mapping")
        missing = [field for field in _BUCKET_FIELDS if field not in bucket]
        if missing:
            raise PersonalPolicyError(
                f"{source}: bucket {name} missing fields: {', '.join(missing)}"
            )
        if bucket["model"] not in MODELS:
            raise PersonalPolicyError(f"{source}: bucket {name} has unknown model")
        if bucket["confirmation"] not in CONFIRMATIONS:
            raise PersonalPolicyError(
                f"{source}: bucket {name} has unknown confirmation mode"
            )
        if bucket["verifier"] not in VERIFIERS:
            raise PersonalPolicyError(f"{source}: bucket {name} has unknown verifier")
        if bucket["escalate"] not in (False, "on_failure"):
            raise PersonalPolicyError(
                f"{source}: bucket {name} escalate must be false or on_failure"
            )
        for field in ("max_tokens", "latency_slo_ms", "retry"):
            value = bucket[field]
            if not isinstance(value, int) or value < 0:
                raise PersonalPolicyError(
                    f"{source}: bucket {name}.{field} must be a non-negative int"
                )
        if not isinstance(bucket["batch"], bool):
            raise PersonalPolicyError(f"{source}: bucket {name}.batch must be a bool")

    routing = config.get("routing")
    if not isinstance(routing, dict):
        raise PersonalPolicyError(f"{source}: missing 'routing'")
    enabled = routing.get("enabled_buckets")
    if not isinstance(enabled, list):
        raise PersonalPolicyError(f"{source}: routing.enabled_buckets must be a list")
    unknown = [name for name in enabled if name not in buckets]
    if unknown:
        raise PersonalPolicyError(
            f"{source}: routing.enabled_buckets has unknown buckets: {', '.join(unknown)}"
        )
    promotion = routing.get("promotion")
    if not isinstance(promotion, dict):
        raise PersonalPolicyError(f"{source}: missing routing.promotion")
    for field in (
        "min_decisions",
        "min_verifier_coverage",
        "min_small_accept_rate",
        "min_cost_reduction",
        "max_error_rate_ratio",
    ):
        value = promotion.get(field)
        if not isinstance(value, (int, float)) or value < 0:
            raise PersonalPolicyError(
                f"{source}: routing.promotion.{field} must be a non-negative number"
            )

    constraints = config.get("hard_constraints")
    if not isinstance(constraints, dict):
        raise PersonalPolicyError(f"{source}: missing 'hard_constraints'")
    for section in ("local_only", "user_absent_irreversible", "degraded_device",
                    "budget_exhausted"):
        if not isinstance(constraints.get(section), dict):
            raise PersonalPolicyError(
                f"{source}: missing hard_constraints.{section}"
            )
    allowed = constraints["budget_exhausted"].get("allowed_buckets")
    if not isinstance(allowed, list):
        raise PersonalPolicyError(
            f"{source}: hard_constraints.budget_exhausted.allowed_buckets must be a list"
        )
    unknown = [name for name in allowed if name not in buckets]
    if unknown:
        raise PersonalPolicyError(
            f"{source}: budget_exhausted has unknown buckets: {', '.join(unknown)}"
        )


def _check_decision(decision: Any) -> None:
    if not isinstance(decision, dict):
        raise PersonalPolicyError("decision must be a mapping")
    for field, allowed in (
        ("consequence", CONSEQUENCES),
        ("latency", LATENCIES),
        ("load", LOADS),
    ):
        value = decision.get(field)
        if value not in allowed:
            raise PersonalPolicyError(
                f"decision.{field} must be one of {', '.join(allowed)}"
            )
    sensitivity = decision.get("sensitivity", "cloud_ok")
    if sensitivity not in SENSITIVITIES:
        raise PersonalPolicyError(
            f"decision.sensitivity must be one of {', '.join(SENSITIVITIES)}"
        )
    device = decision.get("device", "normal")
    if device not in DEVICES:
        raise PersonalPolicyError(
            f"decision.device must be one of {', '.join(DEVICES)}"
        )
    confidence = decision.get("consequence_confidence")
    if confidence is not None and (
        not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1
    ):
        raise PersonalPolicyError("decision.consequence_confidence must be in [0, 1]")


def _step_up(consequence: str) -> str:
    order = list(CONSEQUENCES)
    index = order.index(consequence)
    return order[min(index + 1, len(order) - 1)]


def _base_bucket(consequence: str, latency: str, load: str) -> str:
    if load == "sensing":
        return "B0_sense"
    if consequence == "write_irreversible":
        return "B4_act_irreversible"
    if consequence == "write_reversible":
        return "B3_act_reversible"
    if latency == "background":
        return "B5_background"
    if consequence == "suggest":
        return "B2_draft"
    return "B1_read"


def assign_bucket(decision: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the bucket and effective policy for one decision point."""
    _check_decision(decision)
    constraints = config["hard_constraints"]

    consequence = decision["consequence"]
    confidence = decision.get("consequence_confidence")
    floor = float(config["consequence_confidence_floor"])
    if confidence is not None and confidence < floor:
        consequence = _step_up(consequence)

    requested = _base_bucket(consequence, decision["latency"], decision["load"])
    bucket = requested
    policy = dict(config["buckets"][bucket])

    overrides: List[str] = []
    deferred = False
    queued = False

    # Budget: keep only cheap, non-destructive buckets.
    if decision.get("budget_exhausted"):
        allowed = constraints["budget_exhausted"]["allowed_buckets"]
        if bucket not in allowed:
            deferred = True
            overrides.append("budget:exhausted")

    # Device: defer paid work while preserving cheap sensing.
    triggers = constraints["degraded_device"]["triggers"]
    if decision.get("device", "normal") in triggers and bucket != "B0_sense":
        bucket = "B5_background"
        policy = dict(config["buckets"][bucket])
        deferred = True
        overrides.append(f"device:{decision['device']}")

    # Privacy: local-only data never leaves the device and never escalates.
    if decision.get("sensitivity", "cloud_ok") == "local_only":
        policy["model"] = constraints["local_only"]["model"]
        policy["escalate"] = False
        overrides.append("sensitivity:local_only")
        if decision.get("local_model_available", True) is False:
            queued = True
            deferred = True
            overrides.append("local_model:unavailable")

    # Irreversible work waits for the user when they are away.
    if (
        consequence == "write_irreversible"
        and decision.get("user_present", True) is False
    ):
        queued = True
        overrides.append("presence:absent")

    confirmation = policy["confirmation"]
    if queued:
        confirmation = "required"

    return {
        "bucket": bucket,
        "requested_bucket": requested,
        "model": policy["model"],
        "confirmation": confirmation,
        "verifier": policy["verifier"],
        "escalate": policy["escalate"],
        "max_tokens": policy["max_tokens"],
        "latency_slo_ms": policy["latency_slo_ms"],
        "batch": policy["batch"],
        "retry": policy["retry"],
        "deferred": deferred,
        "queue_for_confirmation": queued,
        "overrides": overrides,
        "reason": _reason(bucket, requested, overrides, deferred, queued),
    }


def _reason(
    bucket: str,
    requested: str,
    overrides: List[str],
    deferred: bool,
    queued: bool,
) -> str:
    if overrides:
        suffix = "; deferred" if deferred else ""
        suffix += "; queued for confirmation" if queued else ""
        return f"bucket {requested} -> {bucket} ({', '.join(overrides)}){suffix}"
    return f"bucket {bucket}"


def bucket_is_routable(bucket: str, config: Dict[str, Any]) -> bool:
    return bucket in config["routing"]["enabled_buckets"]


def check_promotion(stats: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Check whether a bucket meets the quality-routing promotion gates."""
    promotion = config["routing"]["promotion"]
    checks = {
        "decisions": (
            stats.get("decisions", 0),
            promotion["min_decisions"],
            stats.get("decisions", 0) >= promotion["min_decisions"],
        ),
        "verifier_coverage": (
            stats.get("verifier_coverage", 0.0),
            promotion["min_verifier_coverage"],
            stats.get("verifier_coverage", 0.0) >= promotion["min_verifier_coverage"],
        ),
        "small_accept_rate": (
            stats.get("small_accept_rate", 0.0),
            promotion["min_small_accept_rate"],
            stats.get("small_accept_rate", 0.0) >= promotion["min_small_accept_rate"],
        ),
        "cost_reduction": (
            stats.get("cost_reduction", 0.0),
            promotion["min_cost_reduction"],
            stats.get("cost_reduction", 0.0) >= promotion["min_cost_reduction"],
        ),
        "error_rate_ratio": (
            stats.get("error_rate_ratio", 0.0),
            promotion["max_error_rate_ratio"],
            stats.get("error_rate_ratio", 0.0) <= promotion["max_error_rate_ratio"],
        ),
    }
    return {
        "eligible": all(check[2] for check in checks.values()),
        "checks": {
            name: {"value": value, "threshold": threshold, "passed": passed}
            for name, (value, threshold, passed) in checks.items()
        },
    }


def _self_check() -> None:
    config = load_personal_policy()
    sample = {
        "consequence": "write_irreversible",
        "latency": "interactive",
        "load": "single_tool",
        "user_present": False,
    }
    print(assign_bucket(sample, config))


if __name__ == "__main__":
    _self_check()
