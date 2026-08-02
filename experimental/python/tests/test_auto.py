from proxitune_experimental.auto import AutoConfig, AutoRouter
from proxitune_experimental.decision import EngineConfig


def test_auto_router_switches_after_configured_margin_and_dwell():
    switched = []
    router = AutoRouter(
        {"echo": "echo-id", "google": "google-id"},
        switched.append,
        AutoConfig(
            tracker_window_size=1,
            tracker_alpha=1.0,
            decision=EngineConfig(minimum_margin_db=4, candidate_dwell_seconds=2, switch_cooldown_seconds=10),
        ),
    )
    assert router.submit({"echo": -40, "google": -50}, now=0).kind == "candidate"
    assert router.submit({"echo": -40, "google": -50}, now=1).kind == "candidate"
    assert router.submit({"echo": -40, "google": -50}, now=2).kind == "switch"
    assert switched == ["echo-id"]
