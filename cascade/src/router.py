"""
Deterministic rule router for the cascade demo.

The router is intentionally rule-based and reproducible: the same task and
policy always produce the same decision. It emits a deterministic confidence
prior from task metadata; when a backend reports token log-probability
confidence, the engine replaces that prior before deciding whether to escalate.

Routing rules (docs/02-method.md section 5):
  all_frontier -> frontier for every task
  all_small    -> small for every task
  cascade      -> small first; escalate when the small model fails, or when
                  its confidence is below the configured threshold
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Dict

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_POLICY_PATH = os.path.join(REPO_ROOT, "cascade", "configs", "policy.yaml")

_POLICY_VALUES = ("all_frontier", "cascade", "all_small")


class PolicyError(ValueError):
    """Raised when a policy config is missing or malformed."""


def load_policy(path: str = DEFAULT_POLICY_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        policy = yaml.safe_load(handle)
    _check_policy(policy, path)
    return policy


def _check_policy(policy: Any, source: str = "<memory>") -> None:
    if not isinstance(policy, dict):
        raise PolicyError(f"{source}: policy must be a mapping")
    threshold = policy.get("confidence_threshold")
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise PolicyError(f"{source}: confidence_threshold must be in [0, 1]")
    confidence = policy.get("confidence_by_difficulty")
    if not isinstance(confidence, dict):
        raise PolicyError(f"{source}: missing confidence_by_difficulty")
    for difficulty in ("low", "medium", "high"):
        value = confidence.get(difficulty)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise PolicyError(
                f"{source}: confidence_by_difficulty.{difficulty} must be in [0, 1]"
            )
    attempts = policy.get("max_attempts")
    if not isinstance(attempts, dict):
        raise PolicyError(f"{source}: missing max_attempts")
    for name in _POLICY_VALUES:
        value = attempts.get(name)
        if not isinstance(value, int) or value < 1:
            raise PolicyError(f"{source}: max_attempts.{name} must be a positive int")


def _stable_jitter(task_id: str) -> float:
    """Stable value in [-0.03, 0.03] so confidence varies across tasks."""
    digest = hashlib.sha256(f"confidence|{task_id}".encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) / 0xFFFFFFFF - 0.5) * 0.06


def task_confidence(task: Dict[str, Any], policy: Dict[str, Any]) -> float:
    """Small-model confidence for this task, deterministic in ``task_id``."""
    base = policy["confidence_by_difficulty"][task["expected_difficulty"]]
    value = base + _stable_jitter(task["task_id"])
    return round(max(0.0, min(1.0, value)), 4)


def needs_escalation(confidence: float, policy: Dict[str, Any]) -> bool:
    return confidence < float(policy["confidence_threshold"])


def route_first(task: Dict[str, Any], policy_name: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Decision for the first attempt of a task."""
    confidence = task_confidence(task, policy)
    if policy_name == "all_frontier":
        return {
            "task_id": task["task_id"],
            "policy": policy_name,
            "selected_model": "frontier",
            "confidence": 1.0,
            "escalated": False,
            "reason": "policy: every task goes to the frontier model",
        }
    if policy_name == "all_small":
        return {
            "task_id": task["task_id"],
            "policy": policy_name,
            "selected_model": "small",
            "confidence": confidence,
            "escalated": False,
            "reason": "policy: every task stays on the small model",
        }
    if policy_name != "cascade":
        raise PolicyError(f"unknown policy: {policy_name}")
    return {
        "task_id": task["task_id"],
        "policy": policy_name,
        "selected_model": "small",
        "confidence": confidence,
        "escalated": False,
        "reason": (
            f"cascade: start on the small model (confidence {confidence:.2f}, "
            f"threshold {float(policy['confidence_threshold']):.2f})"
        ),
    }


def route_escalation(task: Dict[str, Any], policy: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Decision to escalate a cascade task to the frontier model."""
    return {
        "task_id": task["task_id"],
        "policy": "cascade",
        "selected_model": "frontier",
        "confidence": 1.0,
        "escalated": True,
        "reason": reason,
    }
