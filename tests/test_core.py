from proxitune.decision import DecisionEngine, EngineConfig
from proxitune.proximity import ProximityReading, RssiTracker


def test_tracker_rejects_one_sample_spike():
    tracker = RssiTracker(window_size=3, alpha=1.0)
    for value in (-60, -61, -60):
        tracker.update(ProximityReading("echo", value, 1.0))
    tracker.update(ProximityReading("echo", -20, 2.0))
    assert tracker.snapshot(now=2.0)["echo"] == -60


def test_switch_requires_margin_and_dwell():
    engine = DecisionEngine(
        EngineConfig(minimum_margin_db=8, candidate_dwell_seconds=5, switch_cooldown_seconds=10),
        initial_zone="google",
    )
    assert engine.evaluate({"echo": -45, "google": -50}, 0).kind == "hold"
    assert engine.evaluate({"echo": -40, "google": -55}, 1).kind == "candidate"
    assert engine.evaluate({"echo": -40, "google": -55}, 5).kind == "candidate"
    event = engine.evaluate({"echo": -40, "google": -55}, 6)
    assert event.kind == "switch"
    assert engine.current_zone == "echo"


def test_cooldown_prevents_immediate_bounce():
    engine = DecisionEngine(
        EngineConfig(minimum_margin_db=8, candidate_dwell_seconds=1, switch_cooldown_seconds=10),
        initial_zone="google",
    )
    engine.evaluate({"echo": -40, "google": -55}, 0)
    engine.evaluate({"echo": -40, "google": -55}, 1)
    assert engine.evaluate({"echo": -55, "google": -40}, 2).kind == "hold"
