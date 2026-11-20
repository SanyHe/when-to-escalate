#!/usr/bin/env python3
"""Build the single source of truth for the panel's real-results display.

Reads the three committed judged ledgers (verifier-first repeats r1..r3) and
emits web/data/real_summary.json: per-run + 3-run-mean metrics for the three
policies, the headline trade-off, and a representative offline threshold sweep.

This is a pure reduction of existing evidence files: no model is called, no
randomness is involved, so the numeric content is reproducible from the
committed ledgers. Only the `generated_at` timestamp changes between runs.

Usage:
    python3 cascade/src/build_web_real.py
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_FILES = [
    REPO / "data" / "eval" / f"real_ledger_plus_repeat_verifier_first_r{i}_judged.json"
    for i in (1, 2, 3)
]
OUT = REPO / "web" / "data" / "real_summary.json"

POLICIES = ("all_frontier", "cascade", "all_small")
# Metric keys taken verbatim from judged.policies[policy] so the panel and the
# evidence files always agree.
METRIC_KEYS = (
    "tasks",
    "judged",
    "judge_failures",
    "verified_by_verifier",
    "judged_by_llm",
    "passed",
    "failed",
    "success_rate",
    "cpst_usd",
    "pass_cost_usd",
    "failed_cost_usd",
    "judge_cost_usd",
    "all_in_cpst_usd",
)


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _model_label(meta: dict, role: str) -> str:
    """Best-effort human label for the small/frontier model from ledger meta."""
    backends = meta.get("backends") or {}
    backend = backends.get(role)
    if isinstance(backend, str) and backend:
        return backend
    if isinstance(backend, dict):
        for key in ("model", "model_id", "name"):
            if backend.get(key):
                return str(backend[key])
    return role


def _run_metrics(judged: dict) -> dict:
    out = {}
    for policy in POLICIES:
        row = judged["policies"][policy]
        out[policy] = {k: row[k] for k in METRIC_KEYS if k in row}
    return out


def _mean(run_metrics: list[dict]) -> dict:
    mean = {}
    for policy in POLICIES:
        col = {}
        for key in METRIC_KEYS:
            vals = [rm[policy][key] for rm in run_metrics if key in rm[policy]]
            if not vals:
                continue
            if all(isinstance(v, int) for v in vals):
                # Keep integer counters exact by rounding the mean.
                col[key] = int(round(statistics.mean(vals)))
            else:
                col[key] = statistics.mean(vals)
        col["success_rate_min"] = min(rm[policy]["success_rate"] for rm in run_metrics)
        col["success_rate_max"] = max(rm[policy]["success_rate"] for rm in run_metrics)
        mean[policy] = col
    return mean


def _headline(mean: dict) -> dict:
    f = mean["all_frontier"]
    c = mean["cascade"]
    s = mean["all_small"]
    f_total = f["pass_cost_usd"] + f["failed_cost_usd"]
    c_total = c["pass_cost_usd"] + c["failed_cost_usd"]
    return {
        "frontier_success": f["success_rate"],
        "cascade_success": c["success_rate"],
        "small_success": s["success_rate"],
        "success_gap_pp": (f["success_rate"] - c["success_rate"]) * 100,
        "frontier_serving_cost_usd": f_total,
        "cascade_serving_cost_usd": c_total,
        "cascade_cost_pct_of_frontier": (c_total / f_total) * 100 if f_total else 0.0,
        "cascade_cost_reduction_pct": (1 - c_total / f_total) * 100 if f_total else 0.0,
        "frontier_all_in_cpst_usd": f["all_in_cpst_usd"],
        "cascade_all_in_cpst_usd": c["all_in_cpst_usd"],
        "small_all_in_cpst_usd": s["all_in_cpst_usd"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT), help="output JSON path")
    args = ap.parse_args()
    out_path = Path(args.out)

    runs_raw = [_load(p) for p in RUN_FILES]
    judged_list = [r["judged"] for r in runs_raw]

    # Meta is stable across the three repeats; take it from r1.
    meta0 = runs_raw[0]["_meta"]
    jmeta = judged_list[0]["_meta"]
    run_metrics = [_run_metrics(j) for j in judged_list]
    mean = _mean(run_metrics)
    headline = _headline(mean)

    # Representative offline threshold sweep (r1). The sweep is a pure replay of
    # recorded answers/verdicts; it cannot change any online route.
    sweep = judged_list[0].get("threshold_sweep") or []

    runs_out = []
    for idx, (raw, rm) in enumerate(zip(runs_raw, run_metrics), start=1):
        runs_out.append(
            {
                "run": idx,
                "generated_at": raw["_meta"].get("generated_at"),
                "policies": rm,
            }
        )

    summary = {
        "_meta": {
            "mode": "real_measured",
            "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "source_files": [str(p.relative_to(REPO)) for p in RUN_FILES],
            "task_count": meta0.get("task_count"),
            "runs": len(runs_raw),
            "escalation_mode": (meta0.get("policy") or {}).get("escalation_mode"),
            "threshold": (meta0.get("policy") or {}).get("confidence_threshold"),
            "max_tokens": meta0.get("max_tokens"),
            "small_model": _model_label(meta0, "small"),
            "frontier_model": _model_label(meta0, "frontier"),
            "small_system_prompt": meta0.get("small_system_prompt"),
            "judge_model": jmeta.get("judge_model"),
            "judge_note": jmeta.get("note"),
            "pricing_file": meta0.get("pricing_file"),
            "task_class_distribution": meta0.get("task_class_distribution"),
            "sampled_task_ids": meta0.get("sampled_task_ids"),
            "caveat": (
                "50-task stratified sample; real-model numbers are model- and "
                "operating-point dependent. This is a measured trade-off, not a "
                "'same success, cheaper' claim: cascade costs about 37% of "
                "frontier serving cost for a ~4 pp success loss."
            ),
            "threshold_sweep_note": (
                "Representative offline sweep from run r1: replayed from "
                "recorded answers and verdicts, no extra API calls, cannot "
                "change online routes."
            ),
        },
        "headline": headline,
        "mean": mean,
        "runs": runs_out,
        "threshold_sweep": sweep,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    # Console echo for the verification log / deploy workflow.
    h = headline
    print(f"wrote {out_path.relative_to(REPO)}")
    print(
        "3-run mean: frontier {fs:.1f}% | cascade {cs:.1f}% | small {ss:.1f}% "
        "| cascade serving cost {pct:.1f}% of frontier ({red:.1f}% reduction) "
        "| success gap {gap:.1f} pp".format(
            fs=h["frontier_success"] * 100,
            cs=h["cascade_success"] * 100,
            ss=h["small_success"] * 100,
            pct=h["cascade_cost_pct_of_frontier"],
            red=h["cascade_cost_reduction_pct"],
            gap=h["success_gap_pp"],
        )
    )


if __name__ == "__main__":
    main()
