"""
Offline LLM-as-a-judge pass over a real evaluation ledger (F2.5).

Reads ``data/eval/real_ledger.json`` (or another real ledger), judges the final
answer of every recorded task with a strict rubric, and writes judged success
and CPST metrics next to the original API-success metrics. Candidate answers
are not regenerated, so this pass costs only the judge calls.

Usage (repo root):
    DASHSCOPE_API_KEY=... python3 cascade/src/judge_ledger.py \
        --ledger data/eval/real_ledger.json --sleep 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

from judge import build_judge_backend, judge_answer, summarize_judged  # noqa: E402
from pricing import call_cost, load_pricing  # noqa: E402
from replay import _write_json, load_tasks  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
DEFAULT_TASKS = os.path.join(REPO_ROOT, "data", "synthetic", "seed_tasks.jsonl")
DEFAULT_LEDGER = os.path.join(REPO_ROOT, "data", "eval", "real_ledger.json")
DEFAULT_OUT = os.path.join(REPO_ROOT, "data", "eval", "real_ledger_judged.json")
DEFAULT_MD = os.path.join(REPO_ROOT, "data", "eval", "real_ledger_judged.md")


def final_answer(trace: Dict[str, Any]) -> str:
    """Return the last successful answer, else the last attempt's content."""
    responses = trace.get("responses") or []
    for response in reversed(responses):
        if response.get("success") and response.get("content"):
            return response["content"]
    return responses[-1]["content"] if responses else ""


def judged_records_for_policy(traces: List[Dict[str, Any]],
                              task_prompts: Dict[str, str],
                              backend: Any, pricing: Dict[str, Any],
                              sleep_s: float) -> List[Dict[str, Any]]:
    cache: Dict[str, Dict[str, Any]] = {}
    records: List[Dict[str, Any]] = []
    for trace in traces:
        task_id = trace["task_id"]
        answer = final_answer(trace)
        serving_cost = float(trace["cost_record"]["cost_usd"])
        if not answer:
            records.append({
                "task_id": task_id, "passed": False,
                "reason": "no answer produced", "judge_failed": False,
                "cost_usd": serving_cost, "judge_cost_usd": 0.0,
            })
            continue
        prompt = task_prompts[task_id]
        key = hashlib.sha256((prompt + "\n" + answer).encode("utf-8")).hexdigest()
        verdict = cache.get(key)
        if verdict is None:
            verdict = judge_answer(backend, prompt, answer)
            cache[key] = verdict
            if sleep_s:
                time.sleep(sleep_s)
        judge_cost = call_cost(verdict.get("usage", {}), "frontier", pricing)
        records.append({
            "task_id": task_id,
            "passed": bool(verdict["pass"]),
            "reason": verdict.get("reason", ""),
            "judge_failed": bool(verdict.get("judge_failed", False)),
            "cost_usd": serving_cost,
            "judge_cost_usd": round(judge_cost, 9),
        })
    return records


def render_markdown(ledger: Dict[str, Any], judged: Dict[str, Any]) -> str:
    meta = judged["_meta"]
    lines = [
        "# Real Ledger (LLM-as-a-Judge)",
        "",
        f"> {meta['note']}",
        f"> Judge: `{meta['judge_model']}` | sample: {meta['task_count']} tasks",
        "",
        "| Policy | Tasks | Judged | Judge failures | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for policy_name, summary in judged["policies"].items():
        lines.append(
            f"| {policy_name} | {summary['tasks']} | {summary['judged']} | "
            f"{summary['judge_failures']} | {summary['success_rate']:.2%} | "
            f"${summary['cpst_usd']:.6f} | "
            f"${summary['all_in_cpst_usd']:.6f} | "
            f"${summary['failed_cost_usd']:.6f} | ${summary['judge_cost_usd']:.6f} |"
        )
    lines += [
        "",
        "> Judged success comes from a strict rubric-based judge, not HTTP success. "
        "Judge failures are judge-side infrastructure errors (timeout / rate limit), "
        "not quality verdicts, so they are excluded from the success denominator.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--tasks", default=DEFAULT_TASKS)
    parser.add_argument("--pricing", default=None,
                        help="pricing file for judge cost; defaults to the ledger's")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--md-out", default=DEFAULT_MD)
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="seconds between judge calls")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    with open(args.ledger, "r", encoding="utf-8") as handle:
        ledger = json.load(handle)
    if ledger.get("_meta", {}).get("mode") != "real":
        raise RuntimeError("judge_ledger.py only accepts a REAL ledger")

    tasks = load_tasks(args.tasks)
    task_prompts = {task["task_id"]: task["prompt"] for task in tasks}
    pricing_path = args.pricing or ledger["_meta"].get("pricing_file",
                                                       "cascade/configs/pricing.yaml")
    pricing = load_pricing(
        pricing_path if os.path.isabs(pricing_path)
        else os.path.join(REPO_ROOT, pricing_path)
    )
    backend = build_judge_backend(args.timeout)
    judge_model = backend.model_name

    policies: Dict[str, Dict[str, Any]] = {}
    records: Dict[str, List[Dict[str, Any]]] = {}
    for policy_name, traces in ledger["traces"].items():
        print(f"[{policy_name}] judging {len(traces)} answers", flush=True)
        policy_records = judged_records_for_policy(
            traces, task_prompts, backend, pricing, args.sleep,
        )
        records[policy_name] = policy_records
        policies[policy_name] = summarize_judged(policy_records)

    judged = {
        "_meta": {
            "mode": "judged",
            "note": (
                "Answers are judged offline with a strict rubric; routing was "
                "already decided, so the judge never affects online behaviour."
            ),
            "judge_model": judge_model,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task_count": ledger["_meta"]["task_count"],
            "pricing_file": pricing_path,
        },
        "policies": policies,
        "records": records,
    }

    output = dict(ledger)
    output["judged"] = judged
    _write_json(args.out, output)
    with open(args.md_out, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(ledger, judged))

    print("\nJudged results:")
    for policy_name, summary in policies.items():
        print(
            f"  {policy_name:<12} judged_success={summary['success_rate']:.2%} "
            f"cpst=${summary['cpst_usd']:.6f} "
            f"all_in=${summary['all_in_cpst_usd']:.6f} "
            f"judge_cost=${summary['judge_cost_usd']:.6f}"
        )
    print(f"ledger -> {args.out}")
    print(f"table  -> {args.md_out}")


if __name__ == "__main__":
    main()
