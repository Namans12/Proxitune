# ProxiTune Remote (Android)

This is the supported Android client. It does not scan Bluetooth or estimate
room proximity. The Windows companion owns the Bluetooth audio connections;
this app sends speaker and media commands over the same Wi-Fi network.

Build from the repository root with Android Studio or:

```bat
gradlew.bat assembleDebug
```

Install `app\build\outputs\apk\debug\app-debug.apk`, start the Windows
companion with `python -m proxitune.desktop`, and tap **Scan Windows QR Code**.
Pairing is saved locally, so the QR scan is normally a one-time step.
