# Experimental proximity mode

This folder contains the earlier automatic room-routing prototype. It is not
needed for the working ProxiTune remote and is intentionally kept separate so
it cannot complicate the normal setup.

## What it achieved

- RSSI smoothing, hysteresis, candidate dwell, and cooldown logic.
- An Android scanner that reports Bluetooth Classic/BLE readings to a Windows
  `/proximity` endpoint.
- BLE advertisement inspection and beacon identifier helpers.

## Why it is not the main app

Android and Windows generally do not provide a stable RSSI stream for consumer
speakers while those speakers are connected as classic Bluetooth audio. A scan
may show `-dBm` or unnamed devices, and a speaker can disappear as soon as it
is no longer discoverable. Without reliable readings, automatic switching is
not dependable. Dedicated BLE beacons or another sensor are still needed for
that mode.

## Contents

- `android-proximity/` — the old Android scanner project.
- `python/proxitune_experimental/` — the archived decision, smoothing, BLE,
  and automatic-routing modules.
- `python/tests/` — their original unit tests.

The old Android project can be opened in Android Studio and built with:

```bat
cd experimental\android-proximity
gradlew.bat assembleDebug
```

The Python tests can be run from the repository root with:

```bat
set PYTHONPATH=experimental\python
python -m pytest experimental\python\tests -q
```

These files are retained for reference and future sensor work. The supported
workflow is the QR-paired Android remote described in the root README.
