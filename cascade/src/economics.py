"""
Cascade economics: what would it take for the cascade to beat all-frontier?

The 50-task real run answered "does the current cascade win?" (no). This
script answers the follow-up question without calling a single model: with the
measured token counts and judged pass/fail fixed, which lever - shorter small
answers, a wider price gap, or a different task mix - can flip the sign?

Everything reduces to one inequality. A cascade that tries the small model
first and escalates whenever it fails pays ``S + F_fail`` while always-using
the frontier pays ``F``, so it wins exactly when

    S / F < F_pass / F

i.e. the small model's effective cost ratio must fall below the share of
frontier spend sitting on tasks the small model would have passed. That share
is also the hard ceiling on savings: even a free small model cannot save more
than it.

Inputs (already on disk, no API calls):
  data/eval/real_ledger.json          measured token usage per task and role
  data/eval/real_ledger_judged.json   judged pass/fail under both policies
  cascade/configs/pricing.qwen.yaml   prices used to convert tokens to USD

Output:
  data/eval/economics.json            baseline, lever scenarios, break-even

Usage (repo root):
    python3 cascade/src/economics.py
    # compare a second ledger (e.g. a brevity run) against the baseline
    python3 cascade/src/economics.py --ledger data/eval/real_ledger_brief.json \
        --judged data/eval/real_ledger_brief_judged.json \
        --out data/eval/economics_brief.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

from pricing import load_pricing  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
LEDGER = os.path.join(REPO_ROOT, "data", "eval", "real_ledger.json")
JUDGED = os.path.join(REPO_ROOT, "data", "eval", "real_ledger_judged.json")
PRICING = os.path.join(REPO_ROOT, "cascade", "configs", "pricing.qwen.yaml")
OUT = os.path.join(REPO_ROOT, "data", "eval", "economics.json")

# Levers measured against the same 50 tasks. ``completion_scale`` models a
# brevity instruction on the small model; ``price_factor`` models a cheaper
# small model (qwen-flash, self-hosted vLLM) at an equal token count.
SCENARIOS = (
    ("baseline (measured)", 1.0, 1.0),
    ("small answer x0.75", 0.75, 1.0),
    ("small answer x0.50", 0.5, 1.0),
    ("small price x0.50", 1.0, 0.5),
    ("small price x0.25", 1.0, 0.25),
    ("self-hosted small (x0.10)", 1.0, 0.1),
    ("brief x0.50 + price x0.50", 0.5, 0.5),
)


def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def token_cost(usage: Dict[str, int], prices: Dict[str, float],
               completion_scale: float = 1.0,
               price_factor: float = 1.0) -> float:
    """USD cost of one response; ``completion_scale`` shrinks output tokens."""
    cost = (
        usage.get("prompt_tokens", 0) * prices["input"]
        + usage.get("completion_tokens", 0) * completion_scale * prices["output"]
    ) / 1_000_000
    return cost * price_factor


def build_rows(ledger: Dict[str, Any], judged: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Join measured usage with judged pass/fail, one row per task."""
    small_pass = {rec["task_id"]: bool(rec["passed"]) for rec in judged["all_small"]}
    frontier_pass = {rec["task_id"]: bool(rec["passed"]) for rec in judged["all_frontier"]}
    frontier_usage = {
        trace["task_id"]: trace["responses"][0]["usage"]
        for trace in ledger["traces"]["all_frontier"]
    }
    rows: List[Dict[str, Any]] = []
    for trace in ledger["traces"]["all_small"]:
        task_id = trace["task_id"]
        rows.append({
            "task_id": task_id,
            "small_usage": trace["responses"][0]["usage"],
            "frontier_usage": frontier_usage[task_id],
            "small_pass": small_pass[task_id],
            "frontier_pass": frontier_pass[task_id],
        })
    return rows


def evaluate(rows: List[Dict[str, Any]], prices: Dict[str, Dict[str, float]],
             completion_scale: float = 1.0,
             price_factor: float = 1.0) -> Dict[str, Any]:
    """Cost and savings for the three policies under one lever setting."""
    small_total = sum(
        token_cost(row["small_usage"], prices["small"], completion_scale, price_factor)
        for row in rows
    )
    frontier_by_task = {
        row["task_id"]: token_cost(row["frontier_usage"], prices["frontier"])
        for row in rows
    }
    frontier_total = sum(frontier_by_task.values())
    avoidable = sum(
        frontier_by_task[row["task_id"]] for row in rows if row["small_pass"]
    )

    # Fail-then-escalate cascade: pay the small attempt on every task, pay the
    # frontier only where the small answer failed.
    cascade_total = small_total + (frontier_total - avoidable)
    # Oracle additionally skips frontier calls that would have failed too; this
    # needs knowledge no router has, so it is only an upper bound.
    oracle_total = small_total + sum(
        frontier_by_task[row["task_id"]]
        for row in rows
        if not row["small_pass"] and row["frontier_pass"]
    )
    successes = sum(1 for row in rows if row["small_pass"] or row["frontier_pass"])
    tasks = len(rows)
    ratio = small_total / frontier_total if frontier_total else 0.0
    return {
        "small_total_usd": round(small_total, 6),
        "frontier_total_usd": round(frontier_total, 6),
        "cost_ratio": round(ratio, 4),
        "avoidable_share": round(avoidable / frontier_total, 4) if frontier_total else 0.0,
        "cascade_total_usd": round(cascade_total, 6),
        "cascade_savings": round((frontier_total - cascade_total) / frontier_total, 4)
        if frontier_total else 0.0,
        "oracle_total_usd": round(oracle_total, 6),
        "oracle_savings": round((frontier_total - oracle_total) / frontier_total, 4)
        if frontier_total else 0.0,
        "success_rate": round(successes / tasks, 4) if tasks else 0.0,
        "small_pass_rate": round(sum(1 for row in rows if row["small_pass"]) / tasks, 4)
        if tasks else 0.0,
    }


def break_even(rows: List[Dict[str, Any]],
               prices: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    """The inequality a cascade has to satisfy, in measured terms."""
    measured = evaluate(rows, prices)
    return {
        "rule": "cascade wins iff cost_ratio < avoidable_share",
        "cost_ratio": measured["cost_ratio"],
        "required_ratio": measured["avoidable_share"],
        "small_pass_rate": measured["small_pass_rate"],
        "max_savings_at_zero_small_cost": measured["avoidable_share"],
        "note": (
            "avoidable_share is the share of frontier spend on tasks the small "
            "model would have passed; it is both the break-even ratio and the "
            "savings ceiling. A free small model still cannot save more."
        ),
    }


def render(result: Dict[str, Any]) -> str:
    lines = [
        "lever                        ratio   cascade  oracle  success",
        "-------------------------------------------------------------",
    ]
    for name, metrics in result["scenarios"].items():
        lines.append(
            f"{name:<28} {metrics['cost_ratio']:>5.3f} "
            f"{metrics['cascade_savings']:>+7.1%} {metrics['oracle_savings']:>+7.1%} "
            f"{metrics['success_rate']:>7.0%}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=LEDGER)
    parser.add_argument("--judged", default=JUDGED)
    parser.add_argument("--pricing", default=PRICING)
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args()

    ledger = _load(args.ledger)
    judged = _load(args.judged)["judged"]["records"]
    prices = load_pricing(args.pricing)["models"]
    rows = build_rows(ledger, judged)

    result: Dict[str, Any] = {
        "_meta": {
            "mode": "offline-economics",
            "note": (
                "OFFLINE ONLY: measured token counts and judged verdicts from "
                "the 50-task real run, re-priced under lever assumptions. No "
                f"model was called. Prices: {os.path.relpath(args.pricing, REPO_ROOT)}."
            ),
            "tasks": len(rows),
            "pricing_file": os.path.relpath(args.pricing, REPO_ROOT),
            "ledger_file": os.path.relpath(args.ledger, REPO_ROOT),
            "judged_file": os.path.relpath(args.judged, REPO_ROOT),
            "prices": prices,
            "levers": (
                "completion_scale shrinks only small-model output tokens; "
                "price_factor scales the small model's whole price card."
            ),
        },
        "scenarios": {},
        "break_even": break_even(rows, prices),
    }
    for name, scale, factor in SCENARIOS:
        result["scenarios"][name] = evaluate(rows, prices, scale, factor)

    print(f"tasks: {len(rows)} | " + render(result))
    rule = result["break_even"]
    print(
        f"\nbreak-even: cost_ratio {rule['cost_ratio']:.3f} must drop below "
        f"avoidable_share {rule['required_ratio']:.3f}"
    )
    print(
        f"savings ceiling if the small model were free: "
        f"{rule['max_savings_at_zero_small_cost']:.1%}"
    )

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"ledger -> {args.out}")


if __name__ == "__main__":
    main()
