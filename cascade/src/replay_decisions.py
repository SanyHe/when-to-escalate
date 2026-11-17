"""
Deterministic offline replay of personal-agent decisions.

Purpose: prove the bucketing, hard constraints and telemetry add up to usable
bucket-level numbers before any real traffic or model call exists.

Every outcome, token count and latency below is SIMULATED from fixed priors.
Prices come from cascade/configs/pricing.yaml and are illustrative. Nothing
here measures a model.

Usage (repo root):
    python3 cascade/src/replay_decisions.py
    python3 cascade/src/replay_decisions.py --decisions 400 --seed 11
"""
from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from personal_policy import (
    DEFAULT_PERSONAL_POLICY_PATH,
    assign_bucket,
    load_personal_policy,
)
from pricing import DEFAULT_PRICING_PATH, call_cost, load_pricing
from telemetry import build_event, summarize_events, validate_event

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_EVENTS_PATH = os.path.join(REPO_ROOT, "data", "telemetry", "replay_events.jsonl")
DEFAULT_SUMMARY_PATH = os.path.join(REPO_ROOT, "data", "telemetry", "replay_summary.json")
DEFAULT_MD_PATH = os.path.join(REPO_ROOT, "data", "telemetry", "replay_summary.md")

BASE_TS = datetime(2026, 11, 17, 8, 0, tzinfo=timezone(timedelta(hours=8)))

# Simulated priors. small_pass / frontier_pass are assumptions for the replay,
# not measured model accuracy.
SCENARIOS: Tuple[Dict[str, Any], ...] = (
    {
        "name": "sense_notification",
        "weight": 30,
        "decision": {"consequence": "read", "latency": "near_real_time",
                     "load": "sensing"},
        "small_pass": 1.0,
        "frontier_pass": 1.0,
    },
    {
        "name": "read_weather",
        "weight": 30,
        "decision": {"consequence": "read", "latency": "interactive",
                     "load": "single_tool"},
        "small_pass": 0.85,
        "frontier_pass": 0.95,
    },
    {
        "name": "draft_reply",
        "weight": 30,
        "decision": {"consequence": "suggest", "latency": "interactive",
                     "load": "single_tool"},
        "small_pass": 0.75,
        "frontier_pass": 0.92,
    },
    {
        "name": "reversible_reminder",
        "weight": 25,
        "decision": {"consequence": "write_reversible", "latency": "interactive",
                     "load": "single_tool"},
        "small_pass": 0.70,
        "frontier_pass": 0.90,
    },
    {
        "name": "irreversible_send_present",
        "weight": 20,
        "decision": {"consequence": "write_irreversible", "latency": "interactive",
                     "load": "multi_step", "user_present": True},
        "small_pass": 0.55,
        "frontier_pass": 0.93,
    },
    {
        "name": "irreversible_send_absent",
        "weight": 10,
        "decision": {"consequence": "write_irreversible", "latency": "interactive",
                     "load": "multi_step", "user_present": False},
        "small_pass": 0.55,
        "frontier_pass": 0.93,
    },
    {
        "name": "local_only_draft",
        "weight": 15,
        "decision": {"consequence": "suggest", "latency": "interactive",
                     "load": "single_tool", "sensitivity": "local_only"},
        "small_pass": 0.75,
        "frontier_pass": 0.92,
    },
    {
        "name": "local_model_missing",
        "weight": 5,
        "decision": {"consequence": "suggest", "latency": "interactive",
                     "load": "single_tool", "sensitivity": "local_only",
                     "local_model_available": False},
        "small_pass": 0.75,
        "frontier_pass": 0.92,
    },
    {
        "name": "low_battery_read",
        "weight": 10,
        "decision": {"consequence": "read", "latency": "interactive",
                     "load": "single_tool", "device": "low_battery"},
        "small_pass": 0.85,
        "frontier_pass": 0.95,
    },
    {
        "name": "background_digest",
        "weight": 25,
        "decision": {"consequence": "read", "latency": "background",
                     "load": "synthesis"},
        "small_pass": 0.80,
        "frontier_pass": 0.90,
    },
    {
        "name": "budget_exhausted_write",
        "weight": 8,
        "decision": {"consequence": "write_reversible", "latency": "interactive",
                     "load": "single_tool", "budget_exhausted": True},
        "small_pass": 0.70,
        "frontier_pass": 0.90,
    },
)


def build_decisions(count: int, seed: int) -> List[Dict[str, Any]]:
    """Sample scenarios deterministically so bucket coverage is stable."""
    rng = random.Random(seed)
    indexes = rng.choices(
        range(len(SCENARIOS)),
        weights=[scenario["weight"] for scenario in SCENARIOS],
        k=count,
    )
    decisions: List[Dict[str, Any]] = []
    for index in indexes:
        scenario = SCENARIOS[index]
        decisions.append(
            {
                "scenario": scenario["name"],
                "small_pass": scenario["small_pass"],
                "frontier_pass": scenario["frontier_pass"],
                "payload": dict(scenario["decision"]),
            }
        )
    return decisions


def _tokens(rng: random.Random, model: str, max_tokens: int) -> Tuple[int, int]:
    if model == "none":
        return 0, 0
    prompt = 180 + rng.randint(0, 120)
    ceiling = max(max_tokens, 40)
    if model == "frontier":
        prompt += 100
        completion = rng.randint(min(120, ceiling), ceiling)
    elif model == "local":
        completion = rng.randint(40, min(240, ceiling))
    else:
        completion = rng.randint(40, min(400, ceiling))
    return prompt, completion


def _latency(rng: random.Random, model: str) -> int:
    if model == "none":
        return rng.randint(5, 25)
    if model == "frontier":
        return 900 + rng.randint(0, 2000)
    if model == "local":
        return 250 + rng.randint(0, 450)
    return 400 + rng.randint(0, 800)


def _outcome(rng: random.Random, success: bool, bucket: str) -> str:
    if bucket == "B0_sense":
        return "ignored" if rng.random() < 0.8 else "user_accepted"
    if success:
        roll = rng.random()
        if roll < 0.75:
            return "user_accepted"
        if roll < 0.93:
            return "user_edited"
        if roll < 0.98:
            return "user_undone"
        return "ignored"
    return "failed" if rng.random() < 0.85 else "user_undone"


def simulate(
    decisions: List[Dict[str, Any]],
    config: Dict[str, Any],
    pricing: Dict[str, Any],
    seed: int,
) -> Dict[str, Any]:
    """Turn decisions into telemetry events plus replay counters."""
    rng = random.Random(seed + 1)
    events: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {
        "deferred": 0,
        "queued": 0,
        "escalated": 0,
        "override_counts": Counter(),
        "scenario_counts": Counter(),
    }

    for index, item in enumerate(decisions):
        route = assign_bucket(item["payload"], config)
        bucket = route["bucket"]
        model = route["model"]
        stats["scenario_counts"][bucket] += 1
        for override in route["overrides"]:
            stats["override_counts"][override] += 1

        deferred = route["deferred"]
        queued = route["queue_for_confirmation"]
        if deferred:
            stats["deferred"] += 1
        if queued:
            stats["queued"] += 1

        escalated = False
        tokens_in = tokens_out = 0
        latency_ms = 0
        cost_usd = 0.0
        success = False
        verifier_result = "not_run"

        if deferred or queued:
            outcome = "pending"
            verifier_result = "queued" if queued else "deferred"
        else:
            if model in ("none", "local"):
                success = rng.random() < (
                    1.0 if model == "none" else max(0.10, item["small_pass"] - 0.15)
                )
                prompt, completion = _tokens(rng, model, route["max_tokens"])
                tokens_in, tokens_out = prompt, completion
                latency_ms = _latency(rng, model)
            elif model == "frontier":
                success = rng.random() < item["frontier_pass"]
                prompt, completion = _tokens(rng, "frontier", route["max_tokens"])
                tokens_in, tokens_out = prompt, completion
                latency_ms = _latency(rng, "frontier")
                cost_usd += call_cost(
                    {"prompt_tokens": prompt, "completion_tokens": completion},
                    "frontier",
                    pricing,
                )
            else:
                success = rng.random() < item["small_pass"]
                prompt, completion = _tokens(rng, "small", route["max_tokens"])
                tokens_in, tokens_out = prompt, completion
                latency_ms = _latency(rng, "small")
                cost_usd += call_cost(
                    {"prompt_tokens": prompt, "completion_tokens": completion},
                    "small",
                    pricing,
                )
                if (
                    not success
                    and route["escalate"] == "on_failure"
                ):
                    escalated = True
                    stats["escalated"] += 1
                    prompt, completion = _tokens(
                        rng, "frontier", route["max_tokens"]
                    )
                    tokens_in += prompt
                    tokens_out += completion
                    latency_ms += _latency(rng, "frontier")
                    cost_usd += call_cost(
                        {"prompt_tokens": prompt, "completion_tokens": completion},
                        "frontier",
                        pricing,
                    )
                    success = rng.random() < item["frontier_pass"]

            outcome = _outcome(rng, success, bucket)
            verifier_result = "pass" if success else "fail"

        timestamp = BASE_TS + timedelta(seconds=90 * index)
        event = build_event(
            decision_id=f"d{index + 1:04d}",
            session_id=f"s{(index // 8) + 1:03d}",
            event_id=f"e{index + 1:04d}",
            ts=timestamp.isoformat(),
            bucket=bucket,
            requested_bucket=route["requested_bucket"],
            consequence=item["payload"]["consequence"],
            latency_class=item["payload"]["latency"],
            load=item["payload"]["load"],
            sensitivity=item["payload"].get("sensitivity", "cloud_ok"),
            user_present=item["payload"].get("user_present", True),
            device=item["payload"].get("device", "normal"),
            overrides=route["overrides"],
            context_tokens=200 + rng.randint(0, 2800),
            tools_available=rng.randint(0, 4),
            memory_hits=rng.randint(0, 6),
            model=model,
            cost_usd=round(cost_usd, 9),
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            verifier_type=route["verifier"],
            verifier_result=verifier_result,
            escalated=escalated,
            retry_count=1 if escalated else 0,
            outcome=outcome,
        )
        events.append(event)

    stats["override_counts"] = dict(stats["override_counts"])
    stats["scenario_counts"] = dict(stats["scenario_counts"])
    return {"events": events, "stats": stats}


def _meta(count: int, seed: int) -> Dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "note": (
            "Synthetic decision stream. Outcomes, tokens and latencies are "
            "fixed priors, not measured model output. Prices are illustrative "
            "and come from cascade/configs/pricing.yaml."
        ),
        "seed": seed,
        "decisions": count,
        "policy_config": os.path.relpath(
            DEFAULT_PERSONAL_POLICY_PATH, REPO_ROOT
        ),
        "pricing_file": os.path.relpath(DEFAULT_PRICING_PATH, REPO_ROOT),
    }


def render_markdown(summary: Dict[str, Any], stats: Dict[str, Any]) -> str:
    lines = [
        "# Decision Replay (SIMULATED)",
        "",
        "> SIMULATED: outcomes, token counts and latencies are synthetic priors, "
        "not a model measurement. Prices are illustrative.",
        "",
        "| Bucket | Decisions | Escalated | Accepted | Edited | Undone | Failed | "
        "Pending | Accept rate | Avg cost | Avg latency |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for bucket in sorted(summary["by_bucket"]):
        entry = summary["by_bucket"][bucket]
        outcomes = entry["outcomes"]
        lines.append(
            "| {bucket} | {decisions} | {escalated} | {accepted} | {edited} | "
            "{undone} | {failed} | {pending} | {accept:.1%} | ${cost:.6f} | "
            "{latency:.0f} ms |".format(
                bucket=bucket,
                decisions=entry["decisions"],
                escalated=entry["escalated"],
                accepted=outcomes["user_accepted"],
                edited=outcomes["user_edited"],
                undone=outcomes["user_undone"],
                failed=outcomes["failed"],
                pending=outcomes["pending"],
                accept=entry["accept_rate"],
                cost=entry["avg_cost_usd"],
                latency=entry["avg_latency_ms"],
            )
        )

    lines += [
        "",
        f"Deferred by a hard constraint: {stats['deferred']}  ",
        f"Queued for confirmation: {stats['queued']}  ",
        f"Escalated attempts: {stats['escalated']}",
        "",
        "## Hard constraint hits",
        "",
        "| Override | Decisions |",
        "|---|---|",
    ]
    if stats["override_counts"]:
        for override, count in sorted(stats["override_counts"].items()):
            lines.append(f"| `{override}` | {count} |")
    else:
        lines.append("| none | 0 |")

    lines += [
        "",
        "B0 accept rate is not meaningful: sensing decisions are filtered "
        "without a model call, so they are reported as `ignored` or accepted.",
        "",
    ]
    return "\n".join(lines)


def replay(
    count: int = 240, seed: int = 7
) -> Dict[str, Any]:
    """Run the full replay in memory. Kept side-effect free for tests."""
    config = load_personal_policy()
    pricing = load_pricing()
    decisions = build_decisions(count, seed)
    result = simulate(decisions, config, pricing, seed)
    summary = summarize_events(result["events"])
    return {
        "meta": _meta(count, seed),
        "summary": summary,
        "stats": result["stats"],
        "events": result["events"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline decision replay")
    parser.add_argument("--decisions", type=int, default=240)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--events", default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--summary", default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--md", default=DEFAULT_MD_PATH)
    args = parser.parse_args()

    result = replay(args.decisions, args.seed)
    for event in result["events"]:
        validate_event(event)

    payload = {
        "_meta": result["meta"],
        "summary": result["summary"],
        "stats": result["stats"],
    }
    for path in (args.events, args.summary, args.md):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    with open(args.events, "w", encoding="utf-8") as handle:
        for event in result["events"]:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    with open(args.summary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with open(args.md, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(result["summary"], result["stats"]))

    summary = result["summary"]
    print(f"SIMULATED replay: {summary['decisions']} decisions")
    for bucket in sorted(summary["by_bucket"]):
        entry = summary["by_bucket"][bucket]
        print(
            "  {bucket}: decisions={decisions} escalated={escalated} "
            "accept={accept:.0%} avg_cost=${cost:.6f}".format(
                bucket=bucket,
                decisions=entry["decisions"],
                escalated=entry["escalated"],
                accept=entry["accept_rate"],
                cost=entry["avg_cost_usd"],
            )
        )
    print(f"  deferred={result['stats']['deferred']} "
          f"queued={result['stats']['queued']} "
          f"escalated={result['stats']['escalated']}")


if __name__ == "__main__":
    main()
