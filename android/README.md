# ProxiTune Android Companion

This is the experimental sensor companion for the Windows ProxiTune controller.
It scans Bluetooth Classic discovery and BLE advertisements, matches the Echo
and Google Home by name or address, and posts two RSSI values to the Windows
`/proximity` endpoint every two seconds.

## Build

Open the `android` directory in Android Studio, let Gradle sync, and run the
`app` configuration on an Android 8+ phone. The project uses no third-party
runtime library.

## Configure

1. Start Windows ProxiTune with `--auto` and a token.
2. Find the PC's LAN URL, for example `http://192.168.1.20:8765`.
3. Enter that URL, the same token, and the Bluetooth names or addresses for the
   Echo and Google Home.
4. Grant Bluetooth permissions and tap **Start proximity scanning**.

The phone sends readings only when both targets have been seen within the last
eight seconds. The Windows engine still applies its RSSI smoothing, margin,
dwell, and cooldown rules.

The **Seen devices** section is a diagnostic list. `(unnamed)` entries are
usually BLE advertisements that do not include a friendly name. They are not
automatically the Echo or Google Home. Android discovery can report an RSSI
value without a device name; use the address only if you can positively identify
that device.

## Important limitation

Android Classic Bluetooth RSSI is available during device discovery only. The
speakers may need to be discoverable/pairing before they appear, and some Echo
or Google Home models may not expose usable scan results while connected to the
PC. If either target never appears, the app cannot infer room position without
BLE beacons or another sensor.
