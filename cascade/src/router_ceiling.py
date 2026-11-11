"""
Learned-router ceiling check (offline, zero model calls).

The 50-task real run showed that mean-token-probability confidence has no
routing power. Before building a better router, this script answers a cheaper
question: if we train a classifier on the labels we already have, how close can
it get to the ORACLE router (the router that knows in advance whether the small
model would pass and whether the frontier would rescue it)?

Inputs (all already on disk, no API calls):
  data/eval/real_ledger.json          per-attempt answers, costs, confidence
  data/eval/real_ledger_judged.json   per-task pass/fail under both policies
  data/synthetic/seed_tasks.jsonl     task kind, difficulty, tags, prompt

Output:
  data/eval/router_ceiling.json       metrics per baseline and per threshold

Usage (repo root):
    python3 cascade/src/router_ceiling.py
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.path.join(REPO_ROOT, "data", "eval", "real_ledger.json")
JUDGED = os.path.join(REPO_ROOT, "data", "eval", "real_ledger_judged.json")
SEEDS = os.path.join(REPO_ROOT, "data", "synthetic", "seed_tasks.jsonl")
OUT = os.path.join(REPO_ROOT, "data", "eval", "router_ceiling.json")

MISSING_INPUT_TAGS = ("weather", "meeting", "report", "minutes")


def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _trace_cost(trace: Dict[str, Any]) -> float:
    record = trace["cost_record"]
    if isinstance(record, list):
        return sum(item["cost_usd"] for item in record)
    return float(record["cost_usd"])


def build_rows() -> List[Dict[str, Any]]:
    """Join answers, verdicts and task metadata into one row per task."""
    ledger = _load(LEDGER)
    judged = _load(JUDGED)["judged"]["records"]
    seeds = [json.loads(line) for line in open(SEEDS, "r", encoding="utf-8") if line.strip()]

    meta = {task["task_id"]: task for task in seeds}
    small_trace = {trace["task_id"]: trace for trace in ledger["traces"]["all_small"]}
    frontier_trace = {trace["task_id"]: trace for trace in ledger["traces"]["all_frontier"]}
    small_pass = {rec["task_id"]: rec["passed"] for rec in judged["all_small"]}
    frontier_pass = {rec["task_id"]: rec["passed"] for rec in judged["all_frontier"]}

    rows: List[Dict[str, Any]] = []
    for task_id, task in meta.items():
        if task_id not in small_trace:
            continue
        small_response = small_trace[task_id]["responses"][0]
        usage = small_response.get("usage") or {}
        tags = task.get("tags") or []
        rows.append({
            "task_id": task_id,
            "kind": task["kind"],
            "difficulty": task.get("expected_difficulty", ""),
            "tag_missing_input": float(any(tag in MISSING_INPUT_TAGS for tag in tags)),
            "n_tags": float(len(tags)),
            "prompt_chars": math.log1p(len(task["prompt"])),
            "confidence": float(small_response.get("confidence") or 0.0),
            "completion_tokens": math.log1p(usage.get("completion_tokens", 0)),
            "prompt_tokens": math.log1p(usage.get("prompt_tokens", 0)),
            "small_cost": _trace_cost(small_trace[task_id]),
            "frontier_cost": _trace_cost(frontier_trace[task_id]),
            "small_pass": int(small_pass[task_id]),
            "frontier_pass": int(frontier_pass[task_id]),
        })
    return rows


def feature_matrix(rows: List[Dict[str, Any]], kind: str) -> Tuple[np.ndarray, List[str]]:
    """Build a feature matrix; `kind` selects which feature set to use."""
    names: List[str] = []
    columns: List[List[float]] = []
    if kind in ("full", "difficulty"):
        for level in ("simple", "medium", "complex"):
            names.append(f"kind_{level}")
            columns.append([1.0 if row["kind"] == level else 0.0 for row in rows])
    if kind == "full":
        for name in ("tag_missing_input", "n_tags", "prompt_chars",
                     "completion_tokens", "prompt_tokens"):
            names.append(name)
            columns.append([row[name] for row in rows])
    if kind in ("full", "confidence"):
        names.append("confidence")
        columns.append([row["confidence"] for row in rows])
    return np.array(columns, dtype=float).T, names


def out_of_fold_scores(matrix: np.ndarray, labels: np.ndarray, seed: int = 0) -> np.ndarray:
    """Stratified 5-fold CV; returns one predicted probability per task."""
    scores = np.zeros(len(labels), dtype=float)
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    for train_idx, test_idx in folds.split(matrix, labels):
        scaler = StandardScaler().fit(matrix[train_idx])
        model = LogisticRegression(C=0.5, max_iter=1000, class_weight="balanced")
        model.fit(scaler.transform(matrix[train_idx]), labels[train_idx])
        scores[test_idx] = model.predict_proba(scaler.transform(matrix[test_idx]))[:, 1]
    return scores


def policy_metrics(rows: List[Dict[str, Any]], escalate: List[bool],
                   include_small: bool = True) -> Dict[str, float]:
    """CPST and success for a cascade policy given per-task escalation flags.

    ``include_small=False`` models a fixed all-frontier policy, which never pays
    the small attempt.
    """
    total = 0.0
    success_cost = 0.0
    successes = 0
    for row, did_escalate in zip(rows, escalate):
        cost = (row["small_cost"] if include_small else 0.0) + (
            row["frontier_cost"] if did_escalate else 0.0
        )
        passed = row["frontier_pass"] if did_escalate else row["small_pass"]
        total += cost
        if passed:
            successes += 1
            success_cost += cost
    n = len(rows)
    return {
        "success_rate": successes / n,
        "total_cost_usd": round(total, 6),
        "cpst_usd": round(success_cost / successes, 6) if successes else 0.0,
        "escalation_rate": sum(1 for flag in escalate if flag) / n,
    }


def sweep(scores: np.ndarray, rows: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    """Escalate when the predicted small-model pass probability is below t."""
    curve = []
    for threshold in [round(0.05 * step, 2) for step in range(1, 20)]:
        escalate = [bool(score < threshold) for score in scores]
        metrics = policy_metrics(rows, escalate)
        metrics["threshold"] = threshold
        curve.append(metrics)
    return curve


def best_at_matched_success(curve: List[Dict[str, float]],
                            target_success: float) -> Dict[str, float] | None:
    """Cheapest operating point that reaches the frontier's success rate.

    Comparing CPST across different success rates is meaningless: escalating
    nothing always looks cheap because only the easy tasks count as successful.
    A router must therefore be judged at (or above) the baseline's success.
    """
    eligible = [item for item in curve if item["success_rate"] >= target_success]
    if not eligible:
        return None
    return min(eligible, key=lambda item: item["cpst_usd"])


def main() -> None:
    rows = build_rows()
    labels = np.array([row["small_pass"] for row in rows])
    n = len(rows)
    print(f"tasks: {n} | small passes: {int(labels.sum())} ({labels.mean():.0%})")

    baselines = {
        "all_frontier": policy_metrics(rows, [True] * n, include_small=False),
        "all_small": policy_metrics(rows, [False] * n),
        "oracle": policy_metrics(
            rows,
            [bool((not row["small_pass"]) and row["frontier_pass"]) for row in rows],
        ),
    }
    print("\nbaselines:")
    for name, metrics in baselines.items():
        print(f"  {name:<12} succ={metrics['success_rate']:>5.0%} "
              f"cpst=${metrics['cpst_usd']:.6f} esc={metrics['escalation_rate']:>4.0%}")

    target_success = baselines["all_frontier"]["success_rate"]

    result: Dict[str, Any] = {
        "_meta": {
            "mode": "offline-router-ceiling",
            "note": (
                "OFLINE ONLY: trained and evaluated on the recorded 50-task "
                "real ledger. No model was called. 50 rows / 13 positives make "
                "these estimates noisy; read them as an upper-bound check."
            ),
            "tasks": n,
            "small_passes": int(labels.sum()),
            "baselines": baselines,
        },
        "models": {},
    }

    print(f"\nlearned routers (stratified 5-fold CV), cheapest point at "
          f"success >= {target_success:.0%}:")
    for kind in ("confidence", "difficulty", "full"):
        matrix, names = feature_matrix(rows, kind)
        scores = out_of_fold_scores(matrix, labels)
        auc = roc_auc_score(labels, scores) if len(set(labels)) > 1 else 0.0
        curve = sweep(scores, rows)
        best = best_at_matched_success(curve, target_success)
        result["models"][kind] = {
            "features": names,
            "auc": round(float(auc), 4),
            "best_at_matched_success": best,
            "curve": curve,
        }
        if best is None:
            print(f"  {kind:<10} AUC={auc:.3f}  never reaches {target_success:.0%} success")
            continue
        print(f"  {kind:<10} AUC={auc:.3f}  t={best['threshold']:.2f} "
              f"succ={best['success_rate']:>5.0%} cpst=${best['cpst_usd']:.6f} "
              f"esc={best['escalation_rate']:>4.0%}")

    oracle_cpst = baselines["oracle"]["cpst_usd"]
    frontier_cpst = baselines["all_frontier"]["cpst_usd"]
    full_best = result["models"]["full"]["best_at_matched_success"]
    # Headroom is measured on TOTAL spend at matched success, not CPST: CPST
    # ignores money spent on failed tasks, so a policy that fails cheaply can
    # look good while wasting more overall.
    oracle_total = baselines["oracle"]["total_cost_usd"]
    frontier_total = baselines["all_frontier"]["total_cost_usd"]
    if full_best and oracle_total < frontier_total:
        captured = (frontier_total - full_best["total_cost_usd"]) / (frontier_total - oracle_total)
    else:
        captured = 0.0
    result["_meta"]["headroom_captured_on_total_spend"] = round(float(captured), 4)
    result["_meta"]["headroom_note"] = (
        "Headroom is measured on total spend at matched success. CPST alone is "
        "not comparable across success rates: escalating nothing has the lowest "
        "CPST because only easy tasks count as successful."
    )
    print(f"\nmatched success >= {target_success:.0%}, total spend per 50 tasks:")
    print(f"  all_frontier      ${frontier_total:.6f}")
    print(f"  oracle            ${oracle_total:.6f}  (perfect router)")
    if full_best:
        print(f"  learned (full)    ${full_best['total_cost_usd']:.6f}")
    print(f"  headroom captured by the full router: {captured:.0%}")
    print("NOTE: the threshold is chosen on the same out-of-fold scores, so the best "
          "point is optimistic; the curve is the honest comparison.")

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"ledger -> {OUT}")


if __name__ == "__main__":
    main()
