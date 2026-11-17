"""
Decision telemetry for an always-on personal agent.

One JSONL line per decision point. The schema is the contract behind
bucket-level cost, escalation rate and undo rate, so every consumer reads the
same field names. Nothing here calls a model or touches the network.

The outcome field is the part that matters most: without `user_edited` and
`user_undone`, an always-on agent has no verifier at all.

Usage (repo root):
    python3 cascade/src/telemetry.py    # prints a self-check summary
"""
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, Iterable, Iterator, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_TELEMETRY_PATH = os.path.join(
    REPO_ROOT, "data", "telemetry", "decisions.jsonl"
)

FIELD_ORDER = (
    "decision_id",
    "session_id",
    "event_id",
    "ts",
    "bucket",
    "requested_bucket",
    "consequence",
    "latency_class",
    "load",
    "sensitivity",
    "user_present",
    "device",
    "overrides",
    "context_tokens",
    "tools_available",
    "memory_hits",
    "model",
    "cost_usd",
    "latency_ms",
    "tokens_in",
    "tokens_out",
    "verifier_type",
    "verifier_result",
    "escalated",
    "retry_count",
    "outcome",
)

REQUIRED_FIELDS = ("decision_id", "ts", "bucket", "model", "outcome")

OUTCOMES = (
    "pending",
    "user_accepted",
    "user_edited",
    "user_undone",
    "ignored",
    "failed",
)

NUMERIC_FIELDS = (
    "cost_usd",
    "latency_ms",
    "tokens_in",
    "tokens_out",
    "retry_count",
    "context_tokens",
    "tools_available",
    "memory_hits",
)

_DEFAULTS: Dict[str, Any] = {
    "outcome": "pending",
    "escalated": False,
    "user_present": True,
    "overrides": [],
    "cost_usd": 0.0,
    "latency_ms": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "retry_count": 0,
}

_BUCKET_PATTERN = re.compile(r"^B[0-5]_[a-z_]+$")


class TelemetryError(ValueError):
    """Raised when a decision event does not match the telemetry contract."""


def build_event(**fields: Any) -> Dict[str, Any]:
    """Build a validated event in the canonical field order."""
    unknown = sorted(set(fields) - set(FIELD_ORDER))
    if unknown:
        raise TelemetryError(f"unknown event fields: {', '.join(unknown)}")

    # Every field is emitted so the JSONL schema stays stable even when a
    # producer does not know a value yet; unknown values become null.
    event: Dict[str, Any] = {}
    for name in FIELD_ORDER:
        if name in fields:
            event[name] = fields[name]
        elif name in _DEFAULTS:
            value = _DEFAULTS[name]
            event[name] = list(value) if isinstance(value, list) else value
        else:
            event[name] = None

    validate_event(event)
    return event


def validate_event(event: Any) -> None:
    if not isinstance(event, dict):
        raise TelemetryError("event must be a mapping")

    missing = [field for field in REQUIRED_FIELDS if not event.get(field)]
    if missing:
        raise TelemetryError(f"missing required fields: {', '.join(missing)}")

    if not _BUCKET_PATTERN.match(str(event["bucket"])):
        raise TelemetryError(f"invalid bucket id: {event['bucket']}")

    if event["outcome"] not in OUTCOMES:
        raise TelemetryError(
            f"outcome must be one of {', '.join(OUTCOMES)}"
        )

    for field in NUMERIC_FIELDS:
        if field not in event or event[field] is None:
            continue
        value = event[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise TelemetryError(f"{field} must be a non-negative number")

    for field in ("escalated", "user_present"):
        if field in event and not isinstance(event[field], bool):
            raise TelemetryError(f"{field} must be a bool")

    if "overrides" in event and not isinstance(event["overrides"], list):
        raise TelemetryError("overrides must be a list")


def append_event(path: str, event: Dict[str, Any]) -> None:
    """Append one validated event as a JSON line, creating the directory."""
    validate_event(event)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_events(path: str = DEFAULT_TELEMETRY_PATH) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def summarize_events(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate events per bucket for the phase-0 instrumentation review."""
    summary: Dict[str, Any] = {"decisions": 0, "by_bucket": {}}
    for event in events:
        summary["decisions"] += 1
        bucket = event["bucket"]
        entry = summary["by_bucket"].setdefault(
            bucket,
            {
                "decisions": 0,
                "escalated": 0,
                "cost_usd": 0.0,
                "latency_ms": 0.0,
                "outcomes": {name: 0 for name in OUTCOMES},
            },
        )
        entry["decisions"] += 1
        entry["escalated"] += int(bool(event.get("escalated", False)))
        entry["cost_usd"] += float(event.get("cost_usd", 0.0))
        entry["latency_ms"] += float(event.get("latency_ms", 0.0))
        entry["outcomes"][event["outcome"]] += 1

    for entry in summary["by_bucket"].values():
        outcomes = entry["outcomes"]
        resolved = sum(
            outcomes[name]
            for name in ("user_accepted", "user_edited", "user_undone", "ignored", "failed")
        )
        entry["accept_rate"] = (
            outcomes["user_accepted"] / resolved if resolved else 0.0
        )
        entry["undo_rate"] = (
            outcomes["user_undone"] / resolved if resolved else 0.0
        )
        entry["error_rate"] = (
            (outcomes["user_undone"] + outcomes["failed"]) / resolved
            if resolved
            else 0.0
        )
        entry["avg_cost_usd"] = entry["cost_usd"] / entry["decisions"]
        entry["avg_latency_ms"] = entry["latency_ms"] / entry["decisions"]

    return summary


def _self_check() -> None:
    events: List[Dict[str, Any]] = [
        build_event(
            decision_id="d1",
            ts="2026-11-17T10:00:00+08:00",
            bucket="B2_draft",
            model="small",
            escalated=False,
            outcome="user_accepted",
            cost_usd=0.00002,
            latency_ms=850,
        ),
        build_event(
            decision_id="d2",
            ts="2026-11-17T10:01:00+08:00",
            bucket="B2_draft",
            model="frontier",
            escalated=True,
            outcome="user_undone",
            cost_usd=0.0004,
            latency_ms=2400,
        ),
    ]
    print(json.dumps(summarize_events(events), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Summarize decision telemetry")
    parser.add_argument("--path", default=None)
    args = parser.parse_args()
    if args.path:
        print(
            json.dumps(
                summarize_events(load_events(args.path)),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _self_check()
