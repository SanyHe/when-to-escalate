"""
Cascade orchestration engine.

The engine is backend-agnostic: it receives a dict of ``small`` / ``frontier``
backends and calls ``complete(task, attempt)``. All accounting is pure and
deterministic given deterministic backends.

Policies (docs/02-method.md section 5):
  all_frontier  one frontier attempt
  all_small     up to N small attempts, retrying on failure
  cascade       small first, then escalate on failure or low confidence;
                the task succeeds if either model succeeded

Every attempt is recorded as a route_decision + model_response; the task is
rolled up into one cost_record so retry spend is counted in CPST.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

from pricing import call_cost, summarize_records  # noqa: E402
from router import needs_escalation, route_escalation, route_first  # noqa: E402
from schema import validate_cost_record, validate_route_decision  # noqa: E402


class CascadeEngine:
    def __init__(self, backends: Dict[str, Any], pricing: Dict[str, Any],
                 policy: Dict[str, Any], policy_name: str = "cascade") -> None:
        self.backends = backends
        self.pricing = pricing
        self.policy = policy
        self.policy_name = policy_name

    # -- single policy -----------------------------------------------------

    def run_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if self.policy_name == "cascade":
            return self._run_cascade(task)
        return self._run_fixed(task)

    def _run_fixed(self, task: Dict[str, Any]) -> Dict[str, Any]:
        max_attempts = int(self.policy["max_attempts"][self.policy_name])
        decisions: List[Dict[str, Any]] = []
        responses: List[Dict[str, Any]] = []
        success = False
        for attempt in range(1, max_attempts + 1):
            decision = route_first(task, self.policy_name, self.policy)
            self._check_decision(decision)
            decisions.append(decision)
            response = self.backends[decision["selected_model"]].complete(task, attempt)
            responses.append(response)
            if response.get("confidence") is not None:
                decision["confidence"] = round(float(response["confidence"]), 4)
            if response["success"]:
                success = True
                break
        return self._rollup(task, decisions, responses, success)

    def _run_cascade(self, task: Dict[str, Any]) -> Dict[str, Any]:
        decisions: List[Dict[str, Any]] = []
        responses: List[Dict[str, Any]] = []

        first = route_first(task, "cascade", self.policy)
        self._check_decision(first)
        decisions.append(first)
        small = self.backends["small"].complete(task, 1)
        responses.append(small)

        # Prefer the model-reported confidence (token log-probabilities) over
        # the rule-based prior when the backend provides it.
        observed = small.get("confidence")
        if observed is not None:
            first["confidence"] = round(float(observed), 4)
            if small["success"]:
                first["reason"] = (
                    "cascade: small model reported confidence "
                    f"{first['confidence']:.2f} "
                    f"(threshold {float(self.policy['confidence_threshold']):.2f})"
                )

        reason = ""
        if not small["success"]:
            reason = "fallback: the small model failed, escalate to the frontier model"
        elif needs_escalation(first["confidence"], self.policy):
            reason = (
                "quality check: small-model confidence "
                f"{first['confidence']:.2f} is below threshold "
                f"{float(self.policy['confidence_threshold']):.2f}"
            )

        if reason:
            escalation = route_escalation(task, self.policy, reason)
            self._check_decision(escalation)
            decisions.append(escalation)
            frontier = self.backends["frontier"].complete(task, 1)
            responses.append(frontier)
            success = bool(small["success"] or frontier["success"])
        else:
            success = bool(small["success"])

        return self._rollup(task, decisions, responses, success)

    # -- accounting --------------------------------------------------------

    def _rollup(self, task: Dict[str, Any], decisions: List[Dict[str, Any]],
                responses: List[Dict[str, Any]], success: bool) -> Dict[str, Any]:
        cost = sum(
            call_cost(response["usage"], response["model"], self.pricing)
            for response in responses
        )
        latency = sum(float(response["latency_ms"]) for response in responses)
        record = {
            "task_id": task["task_id"],
            "model": responses[-1]["model"],
            "attempts": len(responses),
            "cost_usd": round(cost, 9),
            "latency_ms": round(latency, 1),
            "success": success,
            "cost_per_successful_task_usd": round(cost, 9) if success else 0.0,
        }
        result = validate_cost_record(record)
        if not result.valid:
            raise ValueError(f"cost record violates schema: {result.errors}")
        return {
            "task_id": task["task_id"],
            "policy": self.policy_name,
            "route_decisions": decisions,
            "responses": responses,
            "cost_record": record,
        }

    def _check_decision(self, decision: Dict[str, Any]) -> None:
        result = validate_route_decision(decision)
        if not result.valid:
            raise ValueError(f"route decision violates schema: {result.errors}")

    def run_policy(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.run_task(task) for task in tasks]


def aggregate(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll task traces into the per-policy metrics used by eval and the UI."""
    records = [trace["cost_record"] for trace in traces]
    summary = summarize_records(records)
    tasks = len(traces)
    escalated = sum(
        1 for trace in traces
        if any(d["escalated"] for d in trace["route_decisions"])
    )
    summary.update({
        "escalation_rate": round(escalated / tasks, 6) if tasks else 0.0,
        "avg_latency_ms": round(
            sum(float(r["latency_ms"]) for r in records) / tasks, 1
        ) if tasks else 0.0,
    })
    return summary


def export_trace(trace: Dict[str, Any]) -> str:
    """Human-readable decision chain, used in evidence and debugging."""
    lines = [f"{trace['task_id']} ({trace['policy']})"]
    for decision, response in zip(trace["route_decisions"], trace["responses"]):
        lines.append(
            f"  -> {decision['selected_model']}: success={response['success']} "
            f"latency={response['latency_ms']}ms reason={decision['reason']}"
        )
    record = trace["cost_record"]
    lines.append(
        f"  total=${record['cost_usd']:.6f} attempts={record['attempts']} "
        f"success={record['success']}"
    )
    return "\n".join(lines)
