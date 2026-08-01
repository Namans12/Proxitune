"""Windows-wide media transport controls.

These controls target the session Windows considers current, so they work with
Spotify, browser media (including YouTube), VLC, and other apps that integrate
with System Media Transport Controls.
"""

from __future__ import annotations

import asyncio


class MediaController:
    """Control the current Windows media session from a synchronous caller."""

    async def _invoke(self, action: str) -> bool:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if session is None:
            raise RuntimeError("No active media session was found")

        operations = {
            "play": session.try_play_async,
            "pause": session.try_pause_async,
            "toggle": session.try_toggle_play_pause_async,
            "next": session.try_skip_next_async,
            "previous": session.try_skip_previous_async,
        }
        if action not in operations:
            raise ValueError(f"unknown media action: {action}")
        return bool(await operations[action]())

    def control(self, action: str) -> bool:
        try:
            import winrt.windows.media.control  # noqa: F401
        except ImportError as exc:  # pragma: no cover - optional Windows dependency
            raise RuntimeError("install media controls with: pip install -e .[windows]") from exc
        return asyncio.run(self._invoke(action))

