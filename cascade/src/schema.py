"""
Data contract for the When-to-Escalate cascade demo.

Defines JSON schemas and validation helpers for:
  - task:           the input unit of work
  - route_decision: which model to use, how confident, whether it is an escalation
  - model_response: the selected model's output plus token usage
  - cost_record:    the ledger entry for one task (all attempts included)

Schemas follow docs/02-method.md section 2. All objects are strict JSON:
fixed keys, UTF-8, no extra fields allowed. Cross-field business rules
are encoded in JSON Schema (if/then/else) wherever possible; the
token-sum rule is checked explicitly because JSON Schema cannot express it.

Usage (repo root):
    python3 cascade/src/schema.py --export   # write JSON Schemas to data/schema/
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

import jsonschema

# ---------------------------------------------------------------------------
# Field enums — single source of truth for the generator, router and engine.
# ---------------------------------------------------------------------------

KINDS = ("simple", "medium", "complex")
DIFFICULTIES = ("low", "medium", "high")
POLICIES = ("all_frontier", "cascade", "all_small")
MODELS = ("small", "frontier")

_ISO8601_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"


# ---------------------------------------------------------------------------
# Task schema (input)
# ---------------------------------------------------------------------------

TASK_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Task",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_id",
        "kind",
        "prompt",
        "expected_difficulty",
        "tags",
        "created_at",
    ],
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "enum": list(KINDS)},
        "prompt": {"type": "string", "minLength": 1},
        "expected_difficulty": {"type": "string", "enum": list(DIFFICULTIES)},
        "tags": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "created_at": {"type": "string", "pattern": _ISO8601_PATTERN},
    },
}


# ---------------------------------------------------------------------------
# Route decision schema (routing output for one attempt)
# ---------------------------------------------------------------------------

ROUTE_DECISION_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "RouteDecision",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_id",
        "policy",
        "selected_model",
        "confidence",
        "escalated",
        "reason",
    ],
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "policy": {"type": "string", "enum": list(POLICIES)},
        "selected_model": {"type": "string", "enum": list(MODELS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "escalated": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    # Fixed policies never escalate and always use their own model; a cascade
    # escalation must select the frontier model.
    "allOf": [
        {
            "if": {"properties": {"policy": {"const": "all_frontier"}}},
            "then": {
                "properties": {
                    "selected_model": {"const": "frontier"},
                    "escalated": {"const": False},
                }
            },
        },
        {
            "if": {"properties": {"policy": {"const": "all_small"}}},
            "then": {
                "properties": {
                    "selected_model": {"const": "small"},
                    "escalated": {"const": False},
                }
            },
        },
        {
            "if": {
                "properties": {
                    "policy": {"const": "cascade"},
                    "escalated": {"const": True},
                }
            },
            "then": {"properties": {"selected_model": {"const": "frontier"}}},
        },
    ],
}


# ---------------------------------------------------------------------------
# Model response schema
# ---------------------------------------------------------------------------

MODEL_RESPONSE_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ModelResponse",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_id",
        "model",
        "content",
        "success",
        "latency_ms",
        "usage",
    ],
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "model": {"type": "string", "enum": list(MODELS)},
        "content": {"type": "string"},
        "success": {"type": "boolean"},
        "latency_ms": {"type": "number", "minimum": 0},
        # Optional model-reported confidence in [0, 1]. Real backends fill it
        # from token log-probabilities; the deterministic mock leaves it out.
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "usage": {
            "type": "object",
            "additionalProperties": False,
            "required": ["prompt_tokens", "completion_tokens", "total_tokens"],
            "properties": {
                "prompt_tokens": {"type": "integer", "minimum": 0},
                "completion_tokens": {"type": "integer", "minimum": 0},
                "total_tokens": {"type": "integer", "minimum": 0},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Cost record schema (one ledger row per task, all attempts aggregated)
# ---------------------------------------------------------------------------

COST_RECORD_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CostRecord",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_id",
        "model",
        "attempts",
        "cost_usd",
        "latency_ms",
        "success",
        "cost_per_successful_task_usd",
    ],
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "model": {"type": "string", "enum": list(MODELS)},
        "attempts": {"type": "integer", "minimum": 1},
        "cost_usd": {"type": "number", "minimum": 0},
        "latency_ms": {"type": "number", "minimum": 0},
        "success": {"type": "boolean"},
        "cost_per_successful_task_usd": {"type": "number", "minimum": 0},
    },
    # A failed task contributes no successful-task cost; a successful task
    # contributes exactly its accumulated cost.
    "if": {"properties": {"success": {"const": False}}},
    "then": {"properties": {"cost_per_successful_task_usd": {"const": 0}}},
}


# ---------------------------------------------------------------------------
# Validation API
# ---------------------------------------------------------------------------

class ValidationResult:
    """Structured outcome of validating an object against a schema."""

    def __init__(self, valid: bool, errors: List[str] | None = None) -> None:
        self.valid = valid
        self.errors = errors or []

    def __bool__(self) -> bool:
        return self.valid

    def __repr__(self) -> str:
        if self.valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, errors={self.errors!r})"


def _validate(obj: Any, schema: Dict[str, Any]) -> ValidationResult:
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(obj), key=lambda e: list(e.absolute_path))
    messages: List[str] = []
    for err in errors:
        loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
        messages.append(f"{loc}: {err.message}")
    return ValidationResult(valid=not messages, errors=messages)


def validate_task(obj: Any) -> ValidationResult:
    return _validate(obj, TASK_SCHEMA)


def validate_route_decision(obj: Any) -> ValidationResult:
    return _validate(obj, ROUTE_DECISION_SCHEMA)


def validate_model_response(obj: Any) -> ValidationResult:
    result = _validate(obj, MODEL_RESPONSE_SCHEMA)
    if not result.valid:
        return result
    usage = obj["usage"]
    expected = usage["prompt_tokens"] + usage["completion_tokens"]
    if usage["total_tokens"] != expected:
        return ValidationResult(
            valid=False,
            errors=[
                f"usage.total_tokens: must equal prompt_tokens + completion_tokens "
                f"({expected}), got {usage['total_tokens']}"
            ],
        )
    return result


def validate_cost_record(obj: Any) -> ValidationResult:
    result = _validate(obj, COST_RECORD_SCHEMA)
    if not result.valid:
        return result
    if obj["success"] and obj["cost_per_successful_task_usd"] < 0:
        return ValidationResult(False, ["cost_per_successful_task_usd: must be >= 0"])
    if obj["success"] and obj["cost_per_successful_task_usd"] == 0 and obj["cost_usd"] > 0:
        return ValidationResult(
            False,
            ["cost_per_successful_task_usd: must equal cost_usd for a successful task"],
        )
    return result


VALIDATORS = {
    "task": validate_task,
    "route_decision": validate_route_decision,
    "model_response": validate_model_response,
    "cost_record": validate_cost_record,
}

SCHEMAS = {
    "task": TASK_SCHEMA,
    "route_decision": ROUTE_DECISION_SCHEMA,
    "model_response": MODEL_RESPONSE_SCHEMA,
    "cost_record": COST_RECORD_SCHEMA,
}


def export_schemas(out_dir: str) -> List[str]:
    """Write each schema to ``out_dir`` as a standalone JSON file."""
    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    for name, schema in SCHEMAS.items():
        path = os.path.join(out_dir, f"{name}.schema.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(schema, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true", help="write JSON Schemas")
    parser.add_argument("--out-dir", default="data/schema")
    args = parser.parse_args()
    if args.export:
        for path in export_schemas(args.out_dir):
            print(f"wrote {path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
