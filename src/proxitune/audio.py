"""Windows audio endpoint discovery and switching boundary.

The endpoint IDs printed by this module are the stable values that should be
stored in configuration. Friendly names are not unique and can change when a
Bluetooth profile is re-created.
"""

from __future__ import annotations

import argparse
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioEndpoint:
    id: str
    name: str
    state: str


def list_render_endpoints() -> list[AudioEndpoint]:
    """Return Windows render endpoints using pycaw.

    pycaw is intentionally optional so the decision engine remains usable on
    non-Windows development machines.
    """

    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError as exc:  # pragma: no cover - platform/dependency branch
        raise RuntimeError("install the Windows extra with: pip install -e .[windows]") from exc

    endpoints: list[AudioEndpoint] = []
    # pycaw currently warns when a driver rejects a handful of optional
    # property keys. They are irrelevant to endpoint selection, so keep the
    # diagnostic output focused on devices we can actually use.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        devices = AudioUtilities.GetAllDevices()
    for device in devices:
        # pycaw exposes the underlying IMMDevice through `Device`.
        state = str(getattr(device, "state", "unknown"))
        state_value = getattr(getattr(device, "state", None), "value", None)
        endpoint_id = str(getattr(device, "id", ""))
        # 0.0.0 is the Windows render (playback) flow; 0.0.1 is capture.
        if state_value != 1 or not endpoint_id.startswith("{0.0.0."):
            continue
        name = str(getattr(device, "FriendlyName", ""))
        if endpoint_id and name:
            endpoints.append(AudioEndpoint(endpoint_id, name, state))
    return endpoints


class SoundVolumeViewSwitcher:
    """Small adapter around NirSoft SoundVolumeView.

    Download SoundVolumeView separately and pass its full path. Keeping this
    behind an adapter lets us later replace it with a native IPolicyConfig
    implementation without touching proximity or decision code.
    """

    def __init__(self, executable: str | Path) -> None:
        self.executable = str(executable)

    def set_default(self, endpoint: AudioEndpoint | str) -> None:
        endpoint_id = endpoint.id if isinstance(endpoint, AudioEndpoint) else endpoint
        completed = subprocess.run(
            [self.executable, "/SetDefault", endpoint_id, "all"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            details = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"SoundVolumeView failed ({completed.returncode}): {details}")


class NativeWindowsSwitcher:
    """Set the Windows default render endpoint through Core Audio policy.

    pycaw already ships a small wrapper around the Windows policy COM
    interface. Keeping that call behind this adapter avoids spreading Windows
    implementation details through the rest of ProxiTune.
    """

    def set_default(self, endpoint: AudioEndpoint | str, roles: tuple[str, ...] = ("console", "multimedia")) -> None:
        try:
            import comtypes
            from pycaw.constants import ERole
            from pycaw.pycaw import AudioUtilities
        except ImportError as exc:  # pragma: no cover - platform/dependency branch
            raise RuntimeError("install the Windows extra with: pip install -e .[windows]") from exc

        device_id = endpoint.id if isinstance(endpoint, AudioEndpoint) else endpoint
        role_map = {
            "console": ERole.eConsole,
            "multimedia": ERole.eMultimedia,
            "communications": ERole.eCommunications,
        }
        for role in roles:
            if role not in role_map:
                raise ValueError(f"unknown audio role: {role}")
        # The phone controller invokes this method from an HTTP worker thread.
        # COM is apartment-threaded, so every worker must initialize it before
        # pycaw touches the Windows audio policy interface.
        comtypes.CoInitialize()
        try:
            AudioUtilities.SetDefaultDevice(device_id, [role_map[role] for role in roles])
        finally:
            comtypes.CoUninitialize()


def main() -> int:
    parser = argparse.ArgumentParser(description="List active Windows audio render endpoints")
    parser.add_argument("--set-default", metavar="ENDPOINT_ID", help="set endpoint as console and multimedia default")
    args = parser.parse_args()
    if args.set_default:
        NativeWindowsSwitcher().set_default(args.set_default)
        print(f"Default output set to {args.set_default}")
        return 0
    for endpoint in list_render_endpoints():
        print(f"{endpoint.name}\t{endpoint.id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
