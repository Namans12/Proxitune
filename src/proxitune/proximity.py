"""Sensor-independent proximity signal processing."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median
from time import monotonic


@dataclass(frozen=True)
class ProximityReading:
    """One sensor observation for a named zone."""

    zone: str
    rssi_dbm: float
    observed_at: float
    source: str = "ble"


class RssiTracker:
    """Maintains a robust, smoothed RSSI estimate for each zone.

    A median rejects short spikes (people moving past the radio, Wi-Fi
    interference), while the exponential moving average makes the value change
    quickly enough for room-scale interaction.
    """

    def __init__(self, window_size: int = 7, alpha: float = 0.35) -> None:
        if window_size < 1:
            raise ValueError("window_size must be positive")
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        self._window_size = window_size
        self._alpha = alpha
        self._windows: dict[str, deque[float]] = {}
        self._smoothed: dict[str, float] = {}
        self._last_seen: dict[str, float] = {}

    def update(self, reading: ProximityReading) -> float:
        values = self._windows.setdefault(reading.zone, deque(maxlen=self._window_size))
        values.append(reading.rssi_dbm)
        robust = float(median(values))
        previous = self._smoothed.get(reading.zone, robust)
        smoothed = previous + self._alpha * (robust - previous)
        self._smoothed[reading.zone] = smoothed
        self._last_seen[reading.zone] = reading.observed_at
        return smoothed

    def snapshot(self, now: float | None = None, stale_after: float = 8.0) -> dict[str, float]:
        now = monotonic() if now is None else now
        return {
            zone: value
            for zone, value in self._smoothed.items()
            if now - self._last_seen[zone] <= stale_after
        }

