$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --onefile --windowed `
  --name ProxiTune `
  --icon assets\proxitune.ico `
  --add-data "assets\proxitune-logo.png;assets" `
  tools\desktop_entry.py
