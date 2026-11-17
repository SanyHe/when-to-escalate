import json

import pytest

from calibration import (
    auc,
    brier,
    build_report,
    confusion,
    ece,
    extract_pairs,
    render_markdown,
)


def test_auc_rewards_correct_answers_with_higher_confidence():
    pairs = [(0.9, True), (0.8, True), (0.2, False), (0.1, False)]

    assert auc(pairs) == pytest.approx(1.0)


def test_auc_is_half_for_tied_scores():
    assert auc([(0.5, True), (0.5, False)]) == pytest.approx(0.5)


def test_auc_is_undefined_with_a_single_class():
    assert auc([(0.9, True), (0.8, True)]) is None


def test_brier_matches_manual_values():
    assert brier([(1.0, True), (0.0, False)]) == pytest.approx(0.0)
    assert brier([(0.5, True)]) == pytest.approx(0.25)


def test_ece_is_zero_for_extreme_correct_bins():
    assert ece([(1.0, True)]) == pytest.approx(0.0)
    assert ece([(0.0, False)]) == pytest.approx(0.0)


def test_ece_captures_overconfidence():
    # Every answer is wrong but reports 0.9 confidence.
    assert ece([(0.9, False)] * 4) == pytest.approx(0.9)


def test_confusion_counts_escalation_outcomes():
    pairs = [(0.3, False), (0.4, True), (0.9, True), (0.95, False)]

    result = confusion(pairs, 0.85)

    assert result["escalated"] == 2
    assert result["caught_wrong"] == 1
    assert result["wasted_on_correct"] == 1
    assert result["kept_wrong"] == 1
    assert result["kept_correct"] == 1
    assert result["escalation_rate"] == pytest.approx(0.5)


def fake_ledger():
    return {
        "_meta": {"backends": {"small": "fake-small"}},
        "judged": {
            "records": {
                "all_small": [
                    {"task_id": "t1", "passed": True, "judge_failed": False},
                    {"task_id": "t2", "passed": False, "judge_failed": True},
                    {"task_id": "t3", "passed": False, "judge_failed": False},
                ]
            },
            "threshold_sweep": [
                {"threshold": 0.85, "escalation_rate": 0.5, "judged_success": 0.8,
                 "total_cost_usd": 0.01, "cpst_usd": 0.0002},
            ],
        },
        "traces": {
            "all_small": [
                {"task_id": "t1", "route_decisions": [{"confidence": 0.9}]},
                {"task_id": "t2", "route_decisions": [{"confidence": 0.3}]},
                {"task_id": "t3", "route_decisions": [{"confidence": 0.8}]},
            ]
        },
    }


def test_extract_pairs_excludes_judge_failures():
    pairs, excluded = extract_pairs(fake_ledger())

    assert pairs == [(0.9, True), (0.8, False)]
    assert excluded == 1


def test_report_is_labelled_offline(tmp_path):
    path = tmp_path / "real_ledger_brief_judged.json"
    path.write_text(json.dumps(fake_ledger()), encoding="utf-8")

    report = build_report([str(path)])
    key = next(iter(report["reports"]))
    rendered = render_markdown(report)

    assert key == "fake-small-brief"
    assert report["_meta"]["mode"] == "OFFLINE"
    assert "OFFLINE" in rendered
    assert "fake-small-brief" in rendered
    assert "0.85" in rendered
