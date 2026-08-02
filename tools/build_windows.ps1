$ErrorActionPreference = "Stop"
$python = "python"
if (Test-Path venv\Scripts\python.exe) {
  $python = (Resolve-Path venv\Scripts\python.exe).Path
}
& $python -c "import pycaw, winrt.windows.media.control"
if ($LASTEXITCODE -ne 0) {
  throw "Windows dependencies are missing. Run: $python -m pip install -e `".[windows,desktop]`""
}
$pyinstallerArgs = @(
  "--noconfirm", "--onefile", "--windowed",
  "--name", "ProxiTune",
  "--icon", "assets\proxitune.ico",
  "--add-data", "assets\proxitune-logo.png;assets",
  "--add-data", "assets\proxitune.ico;assets",
  "--collect-submodules", "pycaw",
  "--collect-binaries", "winrt",
  "--hidden-import", "winrt._winrt_windows_media_control",
  "--hidden-import", "winrt.windows.media.control",
  "tools\desktop_entry.py"
)
if (Test-Path config.json) {
  # A locally built executable can carry the user's machine-specific endpoint IDs.
  $pyinstallerArgs = @("--add-data", "config.json;.") + $pyinstallerArgs
}
& $python -m PyInstaller @pyinstallerArgs
