"""
Offline confidence calibration analysis for recorded ledgers.

The question this answers: when the small model reports confidence c, how often
is it actually right? And when a threshold escalates on low confidence, how
much of that escalation is wasted on answers that were already correct?

Nothing here calls a model. It reuses the answers, token counts and judged
verdicts already stored in a judged ledger, so results are reproducible.

Metrics:
  - reliability table per confidence bin (mean confidence vs accuracy)
  - ECE (expected calibration error)
  - Brier score
  - AUC of confidence as a correctness ranker
  - escalation confusion at fixed thresholds

Usage (repo root):
    python3 cascade/src/calibration.py
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_LEDGERS = (
    os.path.join(REPO_ROOT, "data", "eval", "real_ledger_judged.json"),
    os.path.join(REPO_ROOT, "data", "eval", "real_ledger_brief_judged.json"),
    os.path.join(REPO_ROOT, "data", "eval", "real_ledger_flash_judged.json"),
)
DEFAULT_OUT = os.path.join(REPO_ROOT, "data", "eval", "calibration.json")
DEFAULT_MD = os.path.join(REPO_ROOT, "data", "eval", "calibration.md")

THRESHOLD_TARGETS = (0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 1.00)

Pair = Tuple[float, bool]


def extract_pairs(ledger: Dict[str, Any]) -> Tuple[List[Pair], int]:
    """Return (confidence, passed) pairs for the all-small policy.

    Judge infrastructure failures are excluded: they are not a statement about
    answer quality and would otherwise look like confident wrong answers.
    """
    records = ledger.get("judged", {}).get("records", {}).get("all_small", [])
    traces = ledger.get("traces", {}).get("all_small", [])

    confidence: Dict[str, float] = {}
    for trace in traces:
        decisions = trace.get("route_decisions") or []
        if decisions and decisions[0].get("confidence") is not None:
            confidence[trace["task_id"]] = float(decisions[0]["confidence"])

    pairs: List[Pair] = []
    excluded = 0
    for record in records:
        if record.get("judge_failed"):
            excluded += 1
            continue
        value = confidence.get(record["task_id"])
        if value is None:
            excluded += 1
            continue
        pairs.append((value, bool(record["passed"])))
    return pairs, excluded


def auc(pairs: Sequence[Pair]) -> Optional[float]:
    """Probability that a correct answer outranks a wrong one by confidence."""
    positives = [score for score, passed in pairs if passed]
    negatives = [score for score, passed in pairs if not passed]
    if not positives or not negatives:
        return None
    total = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                total += 1.0
            elif positive == negative:
                total += 0.5
    return total / (len(positives) * len(negatives))


def brier(pairs: Sequence[Pair]) -> Optional[float]:
    if not pairs:
        return None
    return sum((score - (1.0 if passed else 0.0)) ** 2 for score, passed in pairs) / len(pairs)


def reliability(pairs: Sequence[Pair], bins: int = 10) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        bucket = [
            (score, passed)
            for score, passed in pairs
            if (low <= score < high) or (index == bins - 1 and score == 1.0)
        ]
        row: Dict[str, Any] = {
            "low": low,
            "high": high,
            "n": len(bucket),
        }
        if bucket:
            mean_conf = sum(score for score, _ in bucket) / len(bucket)
            accuracy = sum(1 for _, passed in bucket if passed) / len(bucket)
            row.update(
                {
                    "mean_confidence": mean_conf,
                    "accuracy": accuracy,
                    "gap": accuracy - mean_conf,
                }
            )
        rows.append(row)
    return rows


def ece(pairs: Sequence[Pair], bins: int = 10) -> Optional[float]:
    if not pairs:
        return None
    total = 0.0
    for row in reliability(pairs, bins):
        if row["n"]:
            total += row["n"] / len(pairs) * abs(row["gap"])
    return total


def confusion(pairs: Sequence[Pair], threshold: float) -> Dict[str, Any]:
    """Counts when everything below `threshold` escalates to the frontier."""
    escalated = [(score, passed) for score, passed in pairs if score < threshold]
    kept = [(score, passed) for score, passed in pairs if score >= threshold]
    return {
        "threshold": threshold,
        "escalated": len(escalated),
        "escalation_rate": len(escalated) / len(pairs) if pairs else 0.0,
        "caught_wrong": sum(1 for _, passed in escalated if not passed),
        "wasted_on_correct": sum(1 for _, passed in escalated if passed),
        "kept_wrong": sum(1 for _, passed in kept if not passed),
        "kept_correct": sum(1 for _, passed in kept if passed),
    }


def summarize(ledger: Dict[str, Any], path: str) -> Dict[str, Any]:
    pairs, excluded = extract_pairs(ledger)
    correct = [score for score, passed in pairs if passed]
    wrong = [score for score, passed in pairs if not passed]
    return {
        "ledger": os.path.relpath(path, REPO_ROOT) if os.path.isabs(path) else path,
        "tasks": len(ledger.get("judged", {}).get("records", {}).get("all_small", [])),
        "scored": len(pairs),
        "excluded_judge_failed": excluded,
        "accuracy": (len(correct) / len(pairs)) if pairs else None,
        "mean_confidence": (
            sum(score for score, _ in pairs) / len(pairs) if pairs else None
        ),
        "mean_confidence_correct": (
            sum(correct) / len(correct) if correct else None
        ),
        "mean_confidence_wrong": (sum(wrong) / len(wrong) if wrong else None),
        "ece": ece(pairs),
        "brier": brier(pairs),
        "auc": auc(pairs),
        "bins": reliability(pairs),
        "confusion": {
            f"{threshold:.2f}": confusion(pairs, threshold)
            for threshold in THRESHOLD_TARGETS
        },
        "frontier": _frontier(ledger),
    }


def _frontier(ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    sweep = ledger.get("judged", {}).get("threshold_sweep") or []
    picked: List[Dict[str, Any]] = []
    for target in THRESHOLD_TARGETS:
        best = min(sweep, key=lambda row: abs(row["threshold"] - target), default=None)
        if best is not None and abs(best["threshold"] - target) <= 0.013:
            picked.append(best)
    return picked


def label_for(path: str, ledger: Dict[str, Any]) -> str:
    backends = ledger.get("_meta", {}).get("backends") or {}
    small = backends.get("small") or "small"
    stem = Path(path).stem
    tag = stem.replace("real_ledger_", "").replace("_judged", "").strip("_")
    # A bare ledger is the baseline run; a model-named tag adds nothing.
    if tag in ("", "judged"):
        return f"{small}-baseline"
    if tag in (small, small.split("-")[-1]):
        return small
    return f"{small}-{tag}"


def build_report(paths: Iterable[str]) -> Dict[str, Any]:
    reports: Dict[str, Any] = {}
    sources: List[str] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            ledger = json.load(handle)
        reports[label_for(path, ledger)] = summarize(ledger, path)
        sources.append(reports[label_for(path, ledger)]["ledger"])
    return {
        "_meta": {
            "mode": "OFFLINE",
            "note": (
                "Reuses recorded small-model answers, confidences and judged "
                "verdicts. No model was called. Each ledger has 50 tasks, so "
                "bin-level estimates and differences under ~5pp are noisy."
            ),
            "sources": sources,
            "bins": 10,
        },
        "reports": reports,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Calibration Analysis (OFFLINE)",
        "",
        "> OFFLINE: reuses recorded answers and judged verdicts; no model was "
        "called. Each ledger has 50 tasks, so treat differences under ~5pp and "
        "sparse high-confidence bins as noise.",
        "",
        "## Summary",
        "",
        "| Run | Scored | Accuracy | Mean conf | Conf (correct) | Conf (wrong) | "
        "ECE | Brier | AUC |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, item in report["reports"].items():
        lines.append(
            "| {name} | {scored}/{tasks} | {acc:.1%} | {conf:.3f} | {cc} | {cw} | "
            "{ece} | {brier} | {auc} |".format(
                name=name,
                scored=item["scored"],
                tasks=item["tasks"],
                acc=item["accuracy"] or 0.0,
                conf=item["mean_confidence"] or 0.0,
                cc=_fmt(item["mean_confidence_correct"]),
                cw=_fmt(item["mean_confidence_wrong"]),
                ece=_fmt(item["ece"], 3),
                brier=_fmt(item["brier"], 3),
                auc=_fmt(item["auc"], 3),
            )
        )

    lines += [
        "",
        "Accuracy below mean confidence means overconfidence. AUC measures how "
        "well confidence ranks correct answers above wrong ones; 0.5 is chance.",
        "",
        "## Escalation confusion at threshold 0.85",
        "",
        "| Run | Escalated | Caught wrong | Wasted on correct | Kept wrong |",
        "|---|---|---|---|---|",
    ]
    for name, item in report["reports"].items():
        row = item["confusion"]["0.85"]
        lines.append(
            "| {name} | {esc} ({rate:.0%}) | {caught} | {wasted} | {kept} |".format(
                name=name,
                esc=row["escalated"],
                rate=row["escalation_rate"],
                caught=row["caught_wrong"],
                wasted=row["wasted_on_correct"],
                kept=row["kept_wrong"],
            )
        )

    for name, item in report["reports"].items():
        lines += [
            "",
            f"## Reliability — {name}",
            "",
            "| Bin | n | Mean conf | Accuracy | Gap |",
            "|---|---|---|---|---|",
        ]
        for row in item["bins"]:
            if not row["n"]:
                continue
            lines.append(
                "| {low:.1f}–{high:.1f} | {n} | {conf:.3f} | {acc:.1%} | "
                "{gap:+.3f} |".format(
                    low=row["low"],
                    high=row["high"],
                    n=row["n"],
                    conf=row["mean_confidence"],
                    acc=row["accuracy"],
                    gap=row["gap"],
                )
            )
        if not any(row["n"] for row in item["bins"]):
            lines.append("| no records | 0 | – | – | – |")

    lines += [
        "",
        "## Threshold frontier (from each ledger's recorded sweep)",
        "",
        "| Run | Threshold | Escalation | Judged success | Total cost |",
        "|---|---|---|---|---|",
    ]
    for name, item in report["reports"].items():
        for row in item["frontier"]:
            lines.append(
                "| {name} | {threshold:.3f} | {esc:.0%} | {success:.0%} | "
                "${cost:.6f} |".format(
                    name=name,
                    threshold=row["threshold"],
                    esc=row["escalation_rate"],
                    success=row["judged_success"],
                    cost=row["total_cost_usd"],
                )
            )

    lines += [
        "",
        "All costs reuse the recorded ledger spend under its own pricing file; "
        "this report does not re-price anything.",
        "",
    ]
    return "\n".join(lines)


def _fmt(value: Optional[float], digits: int = 3) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline calibration analysis")
    parser.add_argument("--ledgers", nargs="+", default=list(DEFAULT_LEDGERS))
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--md", default=DEFAULT_MD)
    args = parser.parse_args()

    report = build_report(args.ledgers)
    for path in (args.out, args.md):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with open(args.md, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(report))

    for name, item in report["reports"].items():
        print(
            "{name}: n={scored} acc={acc:.0%} conf={conf:.3f} "
            "ece={ece:.3f} auc={auc}".format(
                name=name,
                scored=item["scored"],
                acc=item["accuracy"] or 0.0,
                conf=item["mean_confidence"] or 0.0,
                ece=item["ece"] or 0.0,
                auc=_fmt(item["auc"], 3),
            )
        )


if __name__ == "__main__":
    main()
