"""Automatic zone routing from live proximity readings."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .decision import DecisionEngine, DecisionEvent, EngineConfig
from .proximity import ProximityReading, RssiTracker


@dataclass(frozen=True)
class AutoConfig:
    tracker_window_size: int = 7
    tracker_alpha: float = 0.35
    decision: EngineConfig = EngineConfig()


class AutoRouter:
    """Combine phone readings and switch only after a stable decision."""

    def __init__(self, zone_devices: dict[str, str], switch, config: AutoConfig | None = None) -> None:
        self.zone_devices = zone_devices
        self.switch = switch
        self.config = config or AutoConfig()
        self.tracker = RssiTracker(self.config.tracker_window_size, self.config.tracker_alpha)
        self.engine = DecisionEngine(self.config.decision)

    def submit(self, readings: dict[str, float], now: float | None = None) -> DecisionEvent:
        timestamp = monotonic() if now is None else now
        for zone, rssi in readings.items():
            if zone in self.zone_devices:
                self.tracker.update(ProximityReading(zone, float(rssi), timestamp, source="phone"))
        event = self.engine.evaluate(
            self.tracker.snapshot(timestamp, self.config.decision.reading_stale_after_seconds),
            timestamp,
        )
        if event.kind == "switch" and event.zone is not None:
            self.switch(self.zone_devices[event.zone])
        return event

    def set_current(self, zone: str) -> None:
        if zone not in self.zone_devices:
            raise ValueError(f"unknown zone: {zone}")
        self.engine.current_zone = zone

