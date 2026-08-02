# ProxiTune

ProxiTune is a Windows audio router that switches playback between an Echo,
Google Home, and laptop speakers based on where you are in the room.

The project currently provides:

- Windows audio endpoint discovery.
- Programmatic switching of the Windows console and multimedia output.
- A phone-friendly local controller with Echo, Google Home, and Laptop buttons.
- Play/pause, previous, and next controls for the current Windows media session.
- BLE advertisement discovery with RSSI reporting.
- RSSI smoothing, hysteresis, dwell time, and cooldown logic for future automatic mode.
- A configuration-driven design that can later accept BLE, phone, or other sensors.

The no-beacon phone controller is the reliable mode today. Automatic proximity
switching needs a sensor that can distinguish the two room zones; dedicated BLE
beacons are the most reliable option, while phone Bluetooth RSSI is available as
an experimental fallback.

## Requirements

- Windows 10 or Windows 11.
- Python 3.11 or newer. Python 3.13 is recommended.
- A Windows Bluetooth adapter for BLE scanning.
- Echo and Google Home paired with Windows as audio output devices.

Python 3.10 and older are not supported. If you run a lower version, pip will
stop with an error like:

```text
ERROR: Package 'proxitune' requires a different Python: 3.10.5 not in '>=3.11'
```

Install Python 3.11+ and create the environment with that interpreter, for
example:

```bat
py -3.13 -m venv venv
venv\Scripts\activate
python --version
```

## Installation

From the repository directory:

```bat
py -3.13 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[windows,ble,dev]"
```

The extras install:

- `windows`: pycaw, Windows audio, and Global System Media Transport Controls dependencies.
- `ble`: bleak and Windows BLE/WinRT dependencies.
- `dev`: pytest.

## Configure your audio devices

List active playback endpoints:

```bat
python -m proxitune.audio
```

Copy the example configuration and edit the three endpoint IDs:

```bat
copy config.example.json config.json
```

Use the IDs printed by the previous command for `echo`, `google`, and `laptop`.
`config.json` is intentionally ignored by Git because endpoint IDs are specific
to one Windows installation.

## Test manual switching

Switch directly by endpoint ID:

```bat
python -m proxitune.audio --set-default "{WINDOWS-ENDPOINT-ID}"
```

The controller sets both the Windows Console and Multimedia roles. Some apps
pin their own output device and may need to be restarted or reconfigured.

## Use the phone controller

Start the local controller on Windows:

```bat
python -m proxitune.companion --token "choose-a-long-random-token"
```

Find the PC's Wi-Fi IPv4 address with `ipconfig`. Connect the phone to the same
network and open:

```text
http://YOUR-PC-IP:8765/?token=choose-a-long-random-token
```

Tap a zone to switch output. The token prevents other devices on the local
network from changing the output. Windows Firewall may ask permission the first
time the server listens on the network.

The Media row controls the session Windows considers current. It works with
Spotify, browser media such as YouTube, VLC, and other apps that expose Windows
System Media Transport Controls. If an app does not expose a media session, the
page reports that no active media session is available.

The controller initializes Windows COM separately for every request thread. This
avoids the `CoInitialize has not been called` error that can otherwise appear
after the first successful switch.

Automatic mode can be enabled for sensor testing:

```bat
python -m proxitune.companion --auto --token "choose-a-long-random-token"
```

It accepts authenticated `POST /proximity` requests such as:

```json
{"readings": {"echo": -52, "google": -70}}
```

The existing smoothing, minimum RSSI margin, candidate dwell, and cooldown
rules decide whether a switch is justified. Until a phone sensor is connected,
the manual controller remains the recommended mode.

Automatic-mode thresholds are read from `config.json`. For example, lowering
`minimum_margin_db` from `8` to `4` makes switching more responsive when the
speakers are far apart, while the dwell and cooldown values still prevent rapid
bouncing.

## Inspect BLE signals

Scan nearby BLE advertisements and RSSI values:

```bat
python -m proxitune.ble --duration 10
```

The scanner recognizes service UUIDs and iBeacon identifiers. Place a beacon
near each speaker, scan beside each one, and record the two stable identifiers
in `config.json`.

## Build the Android companion

The experimental phone sensor lives in `android/`. Open that directory in
Android Studio, sync Gradle, and run the `app` configuration on an Android 8+
phone. The companion scans Bluetooth Classic discovery and BLE advertisements,
then posts readings to the Windows controller. See [android/README.md](android/README.md)
for configuration and the discoverability limitation.

## Run tests

```bat
python -m pytest -q
```

The tests cover RSSI spike rejection, margin/dwell/cooldown behavior, and
authenticated phone-controller requests without requiring physical speakers.

## Project layout

```text
src/proxitune/
├── audio.py       Windows endpoint discovery and switching
├── ble.py         BLE advertisement scanning and RSSI conversion
├── companion.py   Authenticated phone-friendly local controller
├── decision.py    Hysteresis and cooldown decision engine
└── proximity.py   Median and exponential RSSI smoothing

tests/             Platform-independent unit tests
config.example.json
pyproject.toml
```

## Roadmap

1. Add an Android companion that reports experimental speaker RSSI.
2. Add automatic BLE-zone mode using two beacons.
3. Add tray UI, pause/manual override, logging, and calibration.
4. Add per-application routing and presence-aware behavior.

## Safety and privacy

ProxiTune does not require cloud services. The phone controller is local to your
network and should be protected with a long random token. Do not expose port
8765 directly to the public internet.
