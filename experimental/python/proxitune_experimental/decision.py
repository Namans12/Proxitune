"""Hysteresis and cooldown policy for automatic audio switching."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    minimum_margin_db: float = 8.0
    candidate_dwell_seconds: float = 6.0
    switch_cooldown_seconds: float = 20.0
    reading_stale_after_seconds: float = 8.0


@dataclass(frozen=True)
class DecisionEvent:
    kind: str  # "switch", "candidate", "hold", or "no_signal"
    zone: str | None
    reason: str


class DecisionEngine:
    """Turn filtered zone RSSI values into deliberately infrequent switches."""

    def __init__(self, config: EngineConfig | None = None, initial_zone: str | None = None) -> None:
        self.config = config or EngineConfig()
        self.current_zone = initial_zone
        self._candidate: str | None = None
        self._candidate_since: float | None = None
        self._last_switch_at: float | None = None

    def evaluate(self, scores: dict[str, float], now: float) -> DecisionEvent:
        if len(scores) < 2:
            self._clear_candidate()
            return DecisionEvent("no_signal", None, "need at least two live zone readings")

        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        winner, winner_score = ordered[0]
        runner_score = ordered[1][1]
        margin = winner_score - runner_score

        if margin < self.config.minimum_margin_db:
            self._clear_candidate()
            return DecisionEvent("hold", self.current_zone, f"margin {margin:.1f} dB is below threshold")
        if winner == self.current_zone:
            self._clear_candidate()
            return DecisionEvent("hold", self.current_zone, "current zone remains strongest")
        if (
            self._last_switch_at is not None
            and now - self._last_switch_at < self.config.switch_cooldown_seconds
        ):
            return DecisionEvent("hold", self.current_zone, "switch cooldown is active")

        if winner != self._candidate:
            self._candidate = winner
            self._candidate_since = now
            return DecisionEvent("candidate", winner, f"winner leads by {margin:.1f} dB")

        assert self._candidate_since is not None
        dwell = now - self._candidate_since
        if dwell < self.config.candidate_dwell_seconds:
            return DecisionEvent("candidate", winner, f"stable for {dwell:.1f}s")

        self.current_zone = winner
        self._last_switch_at = now
        self._clear_candidate()
        return DecisionEvent("switch", winner, f"winner led by {margin:.1f} dB for {dwell:.1f}s")

    def _clear_candidate(self) -> None:
        self._candidate = None
        self._candidate_since = None

