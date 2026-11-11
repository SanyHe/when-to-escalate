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


def sweep_thresholds(ledger: Dict[str, Any],
                     records: Dict[str, List[Dict[str, Any]]],
                     step: float = 0.025) -> List[Dict[str, Any]]:
    """Replay the cascade offline across confidence thresholds.

    Uses only recorded answers, verdicts and costs, so no model is called:
    for each threshold a task escalates when the small attempt failed or its
    reported confidence is below the threshold. It answers "would another
    threshold have produced a better judged CPST on this same sample?" without
    spending money or changing the recorded online routing.
    """
    small_rec = {r["task_id"]: r for r in records["all_small"]}
    frontier_rec = {r["task_id"]: r for r in records["all_frontier"]}
    small_trace = {t["task_id"]: t for t in ledger["traces"]["all_small"]}
    frontier_trace = {t["task_id"]: t for t in ledger["traces"]["all_frontier"]}

    def trace_cost(trace: Dict[str, Any]) -> float:
        rec = trace["cost_record"]
        if isinstance(rec, list):
            return sum(item["cost_usd"] for item in rec)
        return float(rec["cost_usd"])

    thresholds = [0.0]
    current = 0.6
    while current <= 0.9501:
        thresholds.append(round(current, 3))
        current += step
    # Keep the full-escalation control for matched-success comparisons.
    thresholds.append(1.0)

    rows = []
    for threshold in thresholds:
        escalated = 0
        successes = 0
        total_cost = 0.0
        success_cost = 0.0
        for task_id, small in small_rec.items():
            small_trace_item = small_trace[task_id]
            responses = small_trace_item["responses"]
            confidence = responses[0].get("confidence") if responses else None
            small_ok = any(r["success"] for r in responses)
            needs = (not small_ok) or confidence is None or float(confidence) < threshold
            if needs:
                escalated += 1
                cost = trace_cost(small_trace_item) + trace_cost(frontier_trace[task_id])
                passed = frontier_rec[task_id]["passed"]
            else:
                cost = trace_cost(small_trace_item)
                passed = small["passed"]
            total_cost += cost
            if passed:
                successes += 1
                success_cost += cost
        cpst = success_cost / successes if successes else 0.0
        rows.append({
            "threshold": threshold,
            "escalation_rate": escalated / max(len(small_rec), 1),
            "judged_success": successes / max(len(small_rec), 1),
            "total_cost_usd": round(total_cost, 6),
            "cpst_usd": round(cpst, 6),
        })
    return rows


def render_sweep(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "",
        "## Threshold sweep (offline replay, no extra API calls)",
        "",
        "| Threshold | Escalation | Judged success | Total cost | CPST |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['threshold']:.3f} | {row['escalation_rate']:.0%} | "
            f"{row['judged_success']:.0%} | ${row['total_cost_usd']:.6f} | "
            f"${row['cpst_usd']:.6f} |"
        )
    lines += [
        "",
        "> Replayed from the recorded answers, verdicts and costs; the judge is "
        "never re-called, so this sweep cannot change any online route.",
        "",
    ]
    return "\n".join(lines)


def render_markdown(ledger: Dict[str, Any], judged: Dict[str, Any]) -> str:
    meta = judged["_meta"]
    lines = [
        "# Real Ledger (LLM-as-a-Judge)",
        "",
        f"> {meta['note']}",
        f"> Judge: `{meta['judge_model']}` | sample: {meta['task_count']} tasks",
        f"> {meta.get('judge_cost_note', '')}",
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


def resolve_sweep_outputs(ledger_path: str, out_path: str, md_path: str,
                          sweep_only: bool) -> tuple:
    """Pick output paths so a sweep never overwrites another ledger's verdicts."""
    if sweep_only and ledger_path != DEFAULT_LEDGER and out_path == DEFAULT_OUT:
        return ledger_path, os.path.splitext(ledger_path)[0] + ".md"
    return out_path, md_path


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
    parser.add_argument("--sweep-only", action="store_true",
                        help="reuse verdicts already stored in the ledger and "
                             "only rebuild the threshold sweep (no judge calls)")
    args = parser.parse_args()

    # A sweep must never write into another ledger's judged file: it rewrites
    # the file it was given unless the caller named an explicit output.
    args.out, args.md_out = resolve_sweep_outputs(
        args.ledger, args.out, args.md_out, args.sweep_only
    )

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
    if args.sweep_only:
        # Reuse verdicts already stored in a judged ledger: no judge calls.
        existing = ledger.get("judged") or {}
        if not existing.get("records"):
            raise RuntimeError(
                "--sweep-only needs a ledger that already contains judged records."
            )
        records = existing["records"]
        judge_model = existing.get("_meta", {}).get("judge_model", "unknown")
        policies = {
            name: summarize_judged(recs) for name, recs in records.items()
        }
    else:
        backend = build_judge_backend(args.timeout)
        # Public artifacts may need a neutral label instead of an internal
        # judge model name; the label never affects the calls themselves.
        judge_model = os.environ.get("CASCADE_JUDGE_LABEL") or backend.model_name
        policies = {}
        records = {}
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
            "judge_cost_note": (
                "Judge tokens are priced with the frontier rate of pricing_file; "
                "that is an estimate, not the judge model's own tariff."
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task_count": ledger["_meta"]["task_count"],
            "pricing_file": pricing_path,
        },
        "policies": policies,
        "records": records,
        "threshold_sweep": sweep_thresholds(ledger, records),
    }

    output = dict(ledger)
    output["judged"] = judged
    _write_json(args.out, output)
    with open(args.md_out, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(ledger, judged))
        handle.write(render_sweep(judged["threshold_sweep"]))

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
