$ErrorActionPreference = "Stop"
$pyinstallerArgs = @(
  "--noconfirm", "--onefile", "--windowed",
  "--name", "ProxiTune",
  "--icon", "assets\proxitune.ico",
  "--add-data", "assets\proxitune-logo.png;assets",
  "tools\desktop_entry.py"
)
if (Test-Path config.json) {
  # A locally built executable can carry the user's machine-specific endpoint IDs.
  $pyinstallerArgs = @("--add-data", "config.json;.") + $pyinstallerArgs
}
python -m PyInstaller @pyinstallerArgs
