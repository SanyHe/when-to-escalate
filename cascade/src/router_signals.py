"""
Routing-signal comparison on the recorded real ledgers (offline, zero API).

The new-mix 50-task run showed that mean-token-probability confidence has no
routing power: it cannot separate frontier-required tasks from tasks the small
model already handles. This script evaluates alternative signals on the same
recorded answers and costs:

  confidence        escalate when mean token probability < threshold (current)
  completion_tokens escalate when the small answer is long
  prompt_tokens     escalate when the prompt is long
  verifier_gate     run the task's deterministic verifier; accept a pass,
                    escalate a fail, fall back to confidence when unverifiable
  verifier_strict   escalate every unverifiable task as well
  class_oracle      read `task_class`: frontier_required -> frontier (upper bound)
  keyword_router    TF-IDF + logistic regression over prompt text, out-of-fold
  hybrid            keyword pre-routing + verifier gate / confidence fallback

Each policy is compared at the frontier's success rate ("matched success"):
CPST across different success rates is not comparable, because escalating
nothing always looks cheap when only easy tasks count as successful.

Caveats written into the output file:
  - exact_match / field_match verifiers use the task's gold expectation, so
    verifier_gate is an upper bound for "every task ships a cheap checker";
    the refusal verifier is a realistic rule.
  - class_oracle reads metadata that production does not have; it is a ceiling.
  - keyword_router is cross-validated on 50 tasks with 15 positives; noisy.
  - inputs are one recorded 50-task sample per small model.

Usage (repo root):
    python3 cascade/src/router_signals.py [--out data/eval/router_signals.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

from verifier import STATUS_NEEDS_JUDGE, STATUS_PASSED, verify_answer  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
EVAL_DIR = os.path.join(REPO_ROOT, "data", "eval")
TASKS_PATH = os.path.join(REPO_ROOT, "data", "synthetic", "seed_tasks.jsonl")
DEFAULT_OUT = os.path.join(EVAL_DIR, "router_signals.json")

RUNS = ("plus", "flash")
DEFAULT_CONFIDENCE_THRESHOLD = 0.85
CLASSES = ("should_refuse", "small_sufficient", "frontier_required")

Decision = str  # "small" | "escalate" | "frontier"


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _trace_cost(trace: Dict[str, Any]) -> float:
    record = trace["cost_record"]
    if isinstance(record, list):
        return sum(item["cost_usd"] for item in record)
    return float(record["cost_usd"])


def _strip_task_number(prompt: str) -> str:
    """Remove the synthetic task-number suffix so text models cannot leak ids."""
    return re.sub(r"[（(]\s*任务编号\s*\d+\s*[）)]", "", prompt).strip()


def load_rows(name: str) -> List[Dict[str, Any]]:
    ledger = _load_json(os.path.join(EVAL_DIR, f"real_ledger_{name}_v2.json"))
    judged = _load_json(os.path.join(EVAL_DIR, f"real_ledger_{name}_v2_judged.json"))
    tasks = {
        task["task_id"]: task
        for task in (
            json.loads(line)
            for line in open(TASKS_PATH, "r", encoding="utf-8")
            if line.strip()
        )
    }

    small_trace = {trace["task_id"]: trace for trace in ledger["traces"]["all_small"]}
    frontier_trace = {trace["task_id"]: trace for trace in ledger["traces"]["all_frontier"]}
    small_pass = {
        record["task_id"]: bool(record["passed"])
        for record in judged["judged"]["records"]["all_small"]
    }
    frontier_pass = {
        record["task_id"]: bool(record["passed"])
        for record in judged["judged"]["records"]["all_frontier"]
    }

    rows: List[Dict[str, Any]] = []
    for task_id, trace in small_trace.items():
        task = tasks[task_id]
        response = trace["responses"][0]
        usage = response.get("usage") or {}
        answer = response.get("content") or ""
        confidence = response.get("confidence")
        verdict = verify_answer(task, answer)
        verification = task.get("verification") or {}
        rows.append({
            "task_id": task_id,
            "task_class": task["task_class"],
            "kind": task["kind"],
            "prompt": _strip_task_number(task["prompt"]),
            "verification_type": verification.get("type", "none"),
            "verifiable": verdict["status"] != STATUS_NEEDS_JUDGE,
            "verifier_status": verdict["status"],
            "small_cost": _trace_cost(trace),
            "frontier_cost": _trace_cost(frontier_trace[task_id]),
            "small_pass": small_pass[task_id],
            "frontier_pass": frontier_pass[task_id],
            "confidence": float(confidence) if isinstance(confidence, (int, float)) else 0.0,
            "confidence_missing": not isinstance(confidence, (int, float)),
            "completion_tokens": float(usage.get("completion_tokens") or 0),
            "prompt_tokens": float(usage.get("prompt_tokens") or 0),
        })
    return rows


def summarize(rows: List[Dict[str, Any]], decisions: List[Decision]) -> Dict[str, Any]:
    """Cost, success and per-class breakdown for one routing decision per task."""
    total = 0.0
    success_cost = 0.0
    successes = 0
    escalations = 0
    frontier_calls = 0
    by_class: Dict[str, Dict[str, float]] = {
        name: {"tasks": 0, "passed": 0, "cost_usd": 0.0} for name in CLASSES
    }

    for row, decision in zip(rows, decisions):
        if decision == "frontier":
            cost = row["frontier_cost"]
            passed = row["frontier_pass"]
            frontier_calls += 1
        elif decision == "escalate":
            cost = row["small_cost"] + row["frontier_cost"]
            passed = row["frontier_pass"]
            escalations += 1
            frontier_calls += 1
        else:
            cost = row["small_cost"]
            passed = row["small_pass"]

        total += cost
        if passed:
            successes += 1
            success_cost += cost

        bucket = by_class[row["task_class"]]
        bucket["tasks"] += 1
        bucket["passed"] += int(passed)
        bucket["cost_usd"] += cost

    n = len(rows)
    return {
        "success_rate": successes / n,
        "passed": successes,
        "tasks": n,
        "total_cost_usd": round(total, 8),
        "cpst_usd": round(success_cost / successes, 8) if successes else 0.0,
        "escalation_rate": escalations / n,
        "frontier_rate": frontier_calls / n,
        "per_class": {
            name: {
                "tasks": int(value["tasks"]),
                "passed": int(value["passed"]),
                "cost_usd": round(value["cost_usd"], 8),
            }
            for name, value in by_class.items()
            if value["tasks"]
        },
    }


def decide_constant(decision: Decision) -> Callable[[Dict[str, Any]], Decision]:
    return lambda row: decision


def decide_oracle(row: Dict[str, Any]) -> Decision:
    """Cheapest option that succeeds; the small call if nothing succeeds."""
    if row["small_pass"]:
        return "small"
    if row["frontier_pass"]:
        return "frontier"
    return "small"


def decide_confidence(row: Dict[str, Any], threshold: float) -> Decision:
    # A missing confidence value is treated as "no evidence": escalate.
    if row["confidence_missing"] or row["confidence"] < threshold:
        return "escalate"
    return "small"


def decide_threshold(field: str, threshold: float, above: bool) -> Callable[[Dict[str, Any]], Decision]:
    def decide(row: Dict[str, Any]) -> Decision:
        value = row[field]
        if (value > threshold) if above else (value < threshold):
            return "escalate"
        return "small"
    return decide


def decide_verifier(row: Dict[str, Any], fallback_threshold: float,
                    strict: bool = False) -> Decision:
    """Accept a verifier pass; escalate a fail; fall back when unverifiable."""
    if row["verifiable"]:
        return "small" if row["verifier_status"] == STATUS_PASSED else "escalate"
    if strict:
        return "escalate"
    return decide_confidence(row, fallback_threshold)


def decide_refusal_gate(row: Dict[str, Any], fallback_threshold: float) -> Decision:
    """Verifier gate restricted to the refusal check, which needs no gold.

    Other verification types (exact_match/field_match) compare against a stored
    expected answer, so they are left on the confidence fallback here. This
    isolates the part of the gain that a production system could reproduce.
    """
    if row["verification_type"] == "refusal":
        return "small" if row["verifier_status"] == STATUS_PASSED else "escalate"
    return decide_confidence(row, fallback_threshold)


def decide_class_oracle(row: Dict[str, Any]) -> Decision:
    return "frontier" if row["task_class"] == "frontier_required" else "small"


def keyword_scores(rows: List[Dict[str, Any]], seed: int = 0) -> np.ndarray:
    """Out-of-fold probability that a task is frontier_required, prompt only."""
    # Imported lazily so the rest of the module (and its tests) stays usable
    # without scikit-learn installed.
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    labels = np.array([1 if row["task_class"] == "frontier_required" else 0 for row in rows])
    if len(set(labels)) < 2:
        return np.zeros(len(rows), dtype=float)
    scores = np.zeros(len(rows), dtype=float)
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    prompts = [row["prompt"] for row in rows]
    for train_idx, test_idx in folds.split(np.zeros(len(rows)), labels):
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        train_matrix = vectorizer.fit_transform([prompts[i] for i in train_idx])
        test_matrix = vectorizer.transform([prompts[i] for i in test_idx])
        model = LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")
        model.fit(train_matrix, labels[train_idx])
        scores[test_idx] = model.predict_proba(test_matrix)[:, 1]
    return scores


def decide_keyword(row: Dict[str, Any], score: float, threshold: float) -> Decision:
    return "frontier" if score >= threshold else "small"


def decide_hybrid(row: Dict[str, Any], score: float, threshold: float,
                  fallback_threshold: float) -> Decision:
    """Pre-route likely frontier tasks; otherwise run small and verify."""
    if score >= threshold:
        return "frontier"
    return decide_verifier(row, fallback_threshold)


def run_policy(rows: List[Dict[str, Any]],
               chooser: Callable[[Dict[str, Any]], Decision]) -> Dict[str, Any]:
    return summarize(rows, [chooser(row) for row in rows])


def sweep(rows: List[Dict[str, Any]],
          factory: Callable[[float], Callable[[Dict[str, Any]], Decision]],
          values: List[float]) -> List[Dict[str, Any]]:
    curve = []
    for value in values:
        metrics = run_policy(rows, factory(value))
        metrics["parameter"] = round(float(value), 4)
        curve.append(metrics)
    return curve


def best_at_matched_success(curve: List[Dict[str, Any]],
                            target_success: float) -> Optional[Dict[str, Any]]:
    """Cheapest operating point that reaches the frontier's success rate."""
    eligible = [item for item in curve if item["success_rate"] >= target_success]
    if not eligible:
        return None
    return min(eligible, key=lambda item: item["total_cost_usd"])


def evaluate_run(name: str) -> Dict[str, Any]:
    rows = load_rows(name)
    n = len(rows)

    baselines = {
        "all_frontier": run_policy(rows, decide_constant("frontier")),
        "all_small": run_policy(rows, decide_constant("small")),
        "oracle": run_policy(rows, decide_oracle),
    }
    target = baselines["all_frontier"]["success_rate"]

    confidence_curve = sweep(
        rows,
        lambda value: (lambda row: decide_confidence(row, value)),
        [round(0.05 * step, 2) for step in range(10, 20)],
    )
    completion_curve = sweep(
        rows,
        lambda value: decide_threshold("completion_tokens", value, above=True),
        [0, 20, 40, 60, 80, 100, 150, 200, 300, 500],
    )
    prompt_curve = sweep(
        rows,
        lambda value: decide_threshold("prompt_tokens", value, above=True),
        [0, 20, 30, 40, 50, 60, 80, 100, 150],
    )
    verifier_curve = sweep(
        rows,
        lambda value: (lambda row: decide_verifier(row, value)),
        [round(0.05 * step, 2) for step in range(10, 20)],
    )
    refusal_curve = sweep(
        rows,
        lambda value: (lambda row: decide_refusal_gate(row, value)),
        [round(0.05 * step, 2) for step in range(10, 20)],
    )

    keyword = keyword_scores(rows)
    keyword_by_id = {
        row["task_id"]: float(score) for row, score in zip(rows, keyword)
    }
    labels = np.array([1 if row["task_class"] == "frontier_required" else 0 for row in rows])
    keyword_auc = 0.0
    if len(set(labels)) > 1:
        from sklearn.metrics import roc_auc_score
        keyword_auc = float(roc_auc_score(labels, keyword))
    keyword_curve = sweep(
        rows,
        lambda value: (
            lambda row: decide_keyword(row, keyword_by_id[row["task_id"]], value)
        ),
        [round(0.1 * step, 2) for step in range(1, 10)],
    )
    hybrid_curve = sweep(
        rows,
        lambda value: (
            lambda row: decide_hybrid(
                row, keyword_by_id[row["task_id"]], value,
                DEFAULT_CONFIDENCE_THRESHOLD,
            )
        ),
        [round(0.1 * step, 2) for step in range(1, 10)],
    )

    fixed = {
        "confidence": run_policy(
            rows, lambda row: decide_confidence(row, DEFAULT_CONFIDENCE_THRESHOLD)
        ),
        "verifier_gate": run_policy(
            rows, lambda row: decide_verifier(row, DEFAULT_CONFIDENCE_THRESHOLD)
        ),
        "refusal_gate": run_policy(
            rows, lambda row: decide_refusal_gate(row, DEFAULT_CONFIDENCE_THRESHOLD)
        ),
    }

    def best(curve: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
        point = best_at_matched_success(curve, target)
        return {
            "signal": label,
            "best_at_matched_success": point,
            "curve": curve,
        }

    signals = {
        "confidence": best(confidence_curve, "mean token probability"),
        "completion_tokens": best(completion_curve, "small answer length"),
        "prompt_tokens": best(prompt_curve, "prompt length"),
        "verifier_gate": best(verifier_curve, "deterministic verifier, confidence fallback"),
        "refusal_gate": best(refusal_curve, "refusal verifier only (no gold), confidence fallback"),
        "verifier_strict": {
            "signal": "deterministic verifier, escalate when unverifiable",
            "best_at_matched_success": run_policy(rows, lambda row: decide_verifier(row, 0.0, strict=True)),
            "curve": [],
        },
        "class_oracle": {
            "signal": "task_class metadata (ceiling, not available in production)",
            "best_at_matched_success": run_policy(rows, decide_class_oracle),
            "curve": [],
        },
        "keyword_router": best(keyword_curve, "TF-IDF prompt classifier"),
        "hybrid": best(hybrid_curve, "keyword pre-route + verifier gate"),
    }
    signals["keyword_router"]["auc"] = round(keyword_auc, 4)

    return {
        "_meta": {
            "run": name,
            "tasks": n,
            "class_counts": {
                name_: sum(1 for row in rows if row["task_class"] == name_)
                for name_ in CLASSES
            },
            "confidence_threshold_used": DEFAULT_CONFIDENCE_THRESHOLD,
            "caveats": [
                "Recorded 50-task sample per model; one task moves 2pp of success.",
                "exact_match/field_match verifiers use gold expectations: "
                "verifier_gate is an upper bound for shipping cheap checkers.",
                "class_oracle reads task_class metadata unavailable in production.",
                "keyword_router is 5-fold out-of-fold on 50 tasks (15 positives).",
                "Costs are serving costs from the recorded ledger; judging is offline.",
            ],
        },
        "baselines": baselines,
        "fixed_threshold": fixed,
        "signals": signals,
    }


def _format_point(point: Optional[Dict[str, Any]]) -> str:
    if not point:
        return "never reaches the frontier success rate"
    return (
        f"succ={point['success_rate']:>5.0%} total=${point['total_cost_usd']:.6f} "
        f"cpst=${point['cpst_usd']:.6f} esc={point['escalation_rate']:>4.0%} "
        f"frontier={point['frontier_rate']:>4.0%}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help="result JSON path")
    args = parser.parse_args()

    result: Dict[str, Any] = {"_meta": {"mode": "offline-routing-signals"}, "runs": {}}
    for name in RUNS:
        run = evaluate_run(name)
        result["runs"][name] = run

        print(f"== {name} ==")
        for policy, metrics in run["baselines"].items():
            print(f"  {policy:<13} {_format_point(metrics)}")
        target = run["baselines"]["all_frontier"]["success_rate"]
        print("  fixed fallback threshold 0.85:")
        for key, metrics in run["fixed_threshold"].items():
            print(f"    {key:<18} {_format_point(metrics)}")
        print(f"  cheapest point at success >= {target:.0%}:")
        for key, item in run["signals"].items():
            extra = ""
            if "auc" in item:
                extra = f"  auc={item['auc']:.3f}"
            point = item["best_at_matched_success"]
            parameter = f"  t={point['parameter']}" if point and "parameter" in point else ""
            print(f"    {key:<18} {_format_point(point)}{parameter}{extra}")
        for key in ("verifier_gate", "refusal_gate"):
            gate = run["fixed_threshold"][key]
            print(f"    {key} per class:")
            for class_name, stats in gate["per_class"].items():
                print(f"      {class_name:<18} {stats['passed']}/{stats['tasks']} "
                      f"cost=${stats['cost_usd']:.6f}")
        print()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"router signals -> {args.out}")


if __name__ == "__main__":
    main()
