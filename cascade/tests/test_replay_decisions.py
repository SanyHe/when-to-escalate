from replay_decisions import render_markdown, replay
from telemetry import validate_event


def test_replay_is_deterministic():
    first = replay(120, seed=7)
    second = replay(120, seed=7)

    assert first["events"] == second["events"]
    assert first["summary"] == second["summary"]
    assert first["stats"] == second["stats"]


def test_all_six_buckets_are_covered():
    result = replay(240, seed=7)

    assert set(result["summary"]["by_bucket"]) == {
        "B0_sense",
        "B1_read",
        "B2_draft",
        "B3_act_reversible",
        "B4_act_irreversible",
        "B5_background",
    }


def test_every_event_matches_the_telemetry_contract():
    result = replay(80, seed=3)

    for event in result["events"]:
        validate_event(event)


def test_hard_constraints_actually_trigger():
    result = replay(240, seed=7)

    assert result["stats"]["deferred"] > 0
    assert result["stats"]["queued"] > 0
    assert result["stats"]["escalated"] > 0
    assert "device:low_battery" in result["stats"]["override_counts"]
    assert "budget:exhausted" in result["stats"]["override_counts"]


def test_pending_only_comes_from_deferred_or_queued_decisions():
    result = replay(120, seed=7)

    for event in result["events"]:
        if event["outcome"] == "pending":
            assert event["verifier_result"] in ("deferred", "queued")


def test_markdown_is_labelled_as_simulated():
    result = replay(120, seed=7)
    rendered = render_markdown(result["summary"], result["stats"])

    assert "SIMULATED" in rendered
    assert "B2_draft" in rendered
    assert "Hard constraint hits" in rendered
