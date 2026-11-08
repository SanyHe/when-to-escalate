"""
Pricing and unit-economics functions for the cascade demo.

Everything here is a pure function of (usage, pricing): no model, no network,
no randomness. That is what makes the ledger testable and reproducible.

Definitions (see docs/03-eval.md):
  - single-call cost = prompt_tokens * input_price + completion_tokens * output_price
  - expected attempts = 1 / p, where p is per-attempt success probability
  - retry premium = 1 / p - 1
  - CPST (Cost per Successful Task) = total cost of successful tasks / successful tasks

Usage (repo root):
    python3 cascade/src/pricing.py        # prints the F1.2/F1.3 self-check
"""
from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Iterable, List

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_PRICING_PATH = os.path.join(REPO_ROOT, "cascade", "configs", "pricing.yaml")

# Pricing is per million tokens; keep the constant explicit in one place.
TOKENS_PER_UNIT = 1_000_000
_DP = 9  # round cost to nano-dollars so ledger comparisons are stable


class PricingError(ValueError):
    """Raised when a pricing table is missing required model entries."""


def load_pricing(path: str = DEFAULT_PRICING_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        pricing = yaml.safe_load(handle)
    _check_pricing(pricing, path)
    return pricing


def _check_pricing(pricing: Any, source: str = "<memory>") -> None:
    if not isinstance(pricing, dict) or "models" not in pricing:
        raise PricingError(f"{source}: missing top-level 'models'")
    for model in ("small", "frontier"):
        entry = pricing["models"].get(model)
        if not isinstance(entry, dict):
            raise PricingError(f"{source}: missing pricing for model '{model}'")
        for key in ("input", "output"):
            value = entry.get(key)
            if not isinstance(value, (int, float)) or value < 0:
                raise PricingError(
                    f"{source}: models.{model}.{key} must be a non-negative number"
                )


def call_cost(usage: Dict[str, int], model: str, pricing: Dict[str, Any]) -> float:
    """Cost of a single model call from token usage and the pricing table."""
    if model not in pricing["models"]:
        raise PricingError(f"unknown model in pricing table: {model}")
    prices = pricing["models"][model]
    cost = (
        usage.get("prompt_tokens", 0) / TOKENS_PER_UNIT * prices["input"]
        + usage.get("completion_tokens", 0) / TOKENS_PER_UNIT * prices["output"]
    )
    return round(cost, _DP)


def expected_attempts(p: float) -> float:
    """Expected number of independent attempts until one success."""
    if p <= 0:
        return float("inf")
    if p >= 1:
        return 1.0
    return 1.0 / p


def retry_premium(p: float) -> float:
    """Extra cost fraction caused by retries, as a ratio (0.43 = +43%)."""
    if p >= 1:
        return 0.0
    return expected_attempts(p) - 1.0


def cpst_from_records(records: Iterable[Dict[str, Any]]) -> float:
    """Cost per successful task from final per-task cost records.

    Failed tasks are excluded from the numerator and denominator; their
    wasted spend is visible separately as ``failed_cost_usd`` in summaries.
    """
    records = list(records)
    successes = [r for r in records if r.get("success")]
    if not successes:
        return 0.0
    total = sum(float(r["cost_usd"]) for r in successes)
    return round(total / len(successes), _DP)


def savings_ratio(reference_cost: float, actual_cost: float) -> float:
    """Fraction saved relative to a reference strategy (0.76 = 76% cheaper)."""
    if reference_cost <= 0:
        return 0.0
    return round(1.0 - actual_cost / reference_cost, 6)


def summarize_records(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate ledger rows into the core unit-economics metrics."""
    records: List[Dict[str, Any]] = list(records)
    total = len(records)
    if total == 0:
        return {
            "tasks": 0,
            "total_cost_usd": 0.0,
            "cpst_usd": 0.0,
            "success_rate": 0.0,
            "failed_cost_usd": 0.0,
            "avg_attempts": 0.0,
        }
    successes = [r for r in records if r.get("success")]
    failures = [r for r in records if not r.get("success")]
    return {
        "tasks": total,
        "total_cost_usd": round(sum(float(r["cost_usd"]) for r in records), _DP),
        "cpst_usd": cpst_from_records(records),
        "success_rate": round(len(successes) / total, 6),
        "failed_cost_usd": round(sum(float(r["cost_usd"]) for r in failures), _DP),
        "avg_attempts": round(
            sum(int(r["attempts"]) for r in records) / total, 4
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pricing", default=DEFAULT_PRICING_PATH)
    args = parser.parse_args()
    pricing = load_pricing(args.pricing)

    sample = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
    print(f"pricing file: {os.path.relpath(args.pricing, REPO_ROOT)}")
    for model in ("small", "frontier"):
        cost = call_cost(sample, model, pricing)
        print(f"  {model:<9} 1000 in / 500 out -> ${cost:.6f}")

    p = 0.70
    print(
        f"p={p:.2f} -> expected attempts {expected_attempts(p):.4f}, "
        f"retry premium {retry_premium(p):.2%}"
    )


if __name__ == "__main__":
    main()
