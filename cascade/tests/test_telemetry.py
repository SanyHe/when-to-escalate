import pytest

from telemetry import (
    TelemetryError,
    append_event,
    build_event,
    load_events,
    summarize_events,
)


def event(**overrides):
    fields = {
        "decision_id": "d1",
        "ts": "2026-11-17T10:00:00+08:00",
        "bucket": "B2_draft",
        "model": "small",
        "outcome": "user_accepted",
    }
    fields.update(overrides)
    return build_event(**fields)


def test_build_event_fills_defaults():
    built = event()
    assert built["escalated"] is False
    assert built["retry_count"] == 0
    assert built["cost_usd"] == 0.0
    assert built["overrides"] == []
    assert list(built)[:3] == ["decision_id", "session_id", "event_id"]


def test_missing_required_field_is_rejected():
    # `outcome` has a default, so omit a field that has none.
    with pytest.raises(TelemetryError):
        build_event(decision_id="d1", ts="2026-11-17T10:00:00+08:00",
                    bucket="B2_draft", outcome="user_accepted")


def test_unknown_field_is_rejected():
    with pytest.raises(TelemetryError):
        event(unexpected="value")


def test_unknown_outcome_is_rejected():
    with pytest.raises(TelemetryError):
        event(outcome="maybe")


def test_negative_cost_is_rejected():
    with pytest.raises(TelemetryError):
        event(cost_usd=-0.1)


def test_invalid_bucket_is_rejected():
    with pytest.raises(TelemetryError):
        event(bucket="quality")


def test_append_and_load_roundtrip(tmp_path):
    path = tmp_path / "telemetry" / "decisions.jsonl"
    first = event(decision_id="d1")
    second = event(decision_id="d2", bucket="B4_act_irreversible",
                   model="frontier", outcome="pending", escalated=True)

    append_event(str(path), first)
    append_event(str(path), second)
    loaded = list(load_events(str(path)))

    assert [item["decision_id"] for item in loaded] == ["d1", "d2"]
    assert loaded[1]["escalated"] is True


def test_summary_reports_accept_and_undo_rates():
    events = [
        event(decision_id="d1", outcome="user_accepted", cost_usd=0.001),
        event(decision_id="d2", outcome="user_edited", cost_usd=0.001),
        event(decision_id="d3", outcome="user_undone", cost_usd=0.002),
        event(decision_id="d4", outcome="failed", cost_usd=0.002),
        event(decision_id="d5", outcome="pending", cost_usd=0.004),
    ]

    summary = summarize_events(events)
    bucket = summary["by_bucket"]["B2_draft"]

    assert summary["decisions"] == 5
    assert bucket["decisions"] == 5
    assert bucket["outcomes"]["user_accepted"] == 1
    assert bucket["accept_rate"] == pytest.approx(0.25)
    assert bucket["undo_rate"] == pytest.approx(0.25)
    assert bucket["error_rate"] == pytest.approx(0.5)
    assert bucket["avg_cost_usd"] == pytest.approx(0.002)
