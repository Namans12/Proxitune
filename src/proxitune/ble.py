"""BLE advertisement discovery for beacon setup and live proximity input."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from .proximity import ProximityReading


@dataclass(frozen=True)
class BleAdvertisement:
    address: str
    name: str | None
    rssi_dbm: float
    service_uuids: tuple[str, ...]
    manufacturer_ids: tuple[int, ...]
    manufacturer_data: tuple[tuple[int, bytes], ...] = ()

    @property
    def identifier(self) -> str:
        """Stable setup identifier when a beacon exposes a service UUID."""

        if self.service_uuids:
            return self.service_uuids[0].lower()
        for company_id, payload in self.manufacturer_data:
            # Apple iBeacon payload: type 0x02, length 0x15, UUID, major,
            # minor, and calibrated power. This survives private-address
            # rotation and is therefore a better configuration key.
            if company_id == 0x004C and len(payload) >= 23 and payload[:2] == b"\x02\x15":
                beacon_uuid = payload[2:18].hex()
                major = int.from_bytes(payload[18:20], "big")
                minor = int.from_bytes(payload[20:22], "big")
                return f"ibeacon:{beacon_uuid}:{major}:{minor}"
        if self.manufacturer_ids:
            return f"manufacturer:{self.manufacturer_ids[0]:04x}/{self.address.lower()}"
        return self.address.lower()


class BleScanner:
    """Thin adapter over bleak, kept separate from decision policy."""

    async def scan_once(self, duration_seconds: float = 5.0) -> list[BleAdvertisement]:
        try:
            from bleak import BleakScanner
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install BLE support with: pip install -e .[ble]") from exc

        discovered = await BleakScanner.discover(
            timeout=duration_seconds,
            return_adv=True,
        )
        advertisements: list[BleAdvertisement] = []
        for address, (device, data) in discovered.items():
            advertisements.append(
                BleAdvertisement(
                    address=address,
                    name=device.name or data.local_name,
                    rssi_dbm=float(data.rssi),
                    service_uuids=tuple(data.service_uuids),
                    manufacturer_ids=tuple(data.manufacturer_data.keys()),
                    manufacturer_data=tuple(data.manufacturer_data.items()),
                )
            )
        return sorted(advertisements, key=lambda item: item.rssi_dbm, reverse=True)

    async def readings_for(self, zone_by_identifier: dict[str, str], duration_seconds: float = 5.0) -> list[ProximityReading]:
        """Convert known beacon advertisements into engine-ready readings."""

        now = asyncio.get_running_loop().time()
        readings: list[ProximityReading] = []
        for advertisement in await self.scan_once(duration_seconds):
            zone = zone_by_identifier.get(advertisement.identifier)
            if zone is not None:
                readings.append(ProximityReading(zone, advertisement.rssi_dbm, now, source="ble"))
        return readings


async def _main(duration_seconds: float) -> None:
    advertisements = await BleScanner().scan_once(duration_seconds)
    if not advertisements:
        print("No BLE advertisements found. Check Bluetooth and beacon power.")
        return
    print("RSSI\tIdentifier\tName\tAddress")
    for item in advertisements:
        print(f"{item.rssi_dbm:5.0f}\t{item.identifier}\t{item.name or '-'}\t{item.address}")


def main() -> int:
    parser = argparse.ArgumentParser(description="List nearby BLE advertisements and RSSI")
    parser.add_argument("--duration", type=float, default=5.0, help="scan duration in seconds")
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be positive")
    asyncio.run(_main(args.duration))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
