"""ProxiTune Windows desktop companion.

This is the normal entry point for the working product. It starts the local
controller, shows a QR code for the Android remote, and optionally registers
itself to launch with Windows.
"""

from __future__ import annotations

import argparse
import json
import secrets
import socket
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlencode

from .audio import NativeWindowsSwitcher
from .companion import CompanionServer, _load_zone_devices
from .media import MediaController


def _local_ip() -> str:
    """Return the LAN address phones on the same Wi-Fi can reach."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        probe.close()


def _state_path() -> Path:
    root = Path.home() / "AppData" / "Local" / "ProxiTune"
    root.mkdir(parents=True, exist_ok=True)
    return root / "state.json"


def _asset_path(name: str) -> Path | None:
    """Locate a bundled logo in source and PyInstaller layouts."""
    roots = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.extend((Path(sys.executable).resolve().parent, Path(__file__).resolve().parents[2]))
    for root in roots:
        candidate = root / "assets" / name
        if candidate.exists():
            return candidate
    return None


def _load_token() -> str:
    path = _state_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("token")
        if value:
            return str(value)
    except (OSError, json.JSONDecodeError):
        pass
    token = secrets.token_urlsafe(18)
    path.write_text(json.dumps({"token": token}, indent=2), encoding="utf-8")
    return token


def _startup_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            winreg.QueryValueEx(key, "ProxiTune")
            return True
    except (ImportError, FileNotFoundError, OSError):
        return False


def _set_startup(enabled: bool, config_path: str = "config.json") -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if enabled:
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}" --config "{Path(config_path).resolve()}" --minimized'
            else:
                command = f'"{sys.executable}" -m proxitune.desktop --config "{Path(config_path).resolve()}" --minimized'
            winreg.SetValueEx(key, "ProxiTune", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "ProxiTune")
            except FileNotFoundError:
                pass


class DesktopApp:
    def __init__(self, config_path: str, port: int, minimized: bool = False) -> None:
        self.config_path = config_path
        self.port = port
        self.token = _load_token()
        self.ip = _local_ip()
        self.root = tk.Tk()
        self.root.title("ProxiTune")
        self.root.geometry("560x650")
        self.root.minsize(480, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self._qr_image = None
        self._tray = None
        self._tray_thread = None
        self._build_ui()
        self._start_server()
        self._start_tray()
        if minimized:
            self.root.after(250, self._hide_window)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="ProxiTune", font=("Segoe UI", 26, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Phone remote for your Windows speakers", font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 18))

        self.status = tk.StringVar(value="Starting controller…")
        ttk.Label(frame, textvariable=self.status, foreground="#176b3a").pack(anchor="w", pady=(0, 10))
        ttk.Label(frame, text="On your Android phone, scan this QR code once:").pack(anchor="w")
        self.qr_label = ttk.Label(frame, text="Preparing QR code…", anchor="center")
        self.qr_label.pack(fill="both", expand=True, pady=12)

        self.url_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.url_var, wraplength=500, justify="left").pack(anchor="w")
        button_row = ttk.Frame(frame)
        button_row.pack(fill="x", pady=12)
        ttk.Button(button_row, text="Copy pairing URL", command=self._copy_url).pack(side="left")
        ttk.Button(button_row, text="Regenerate token", command=self._regenerate).pack(side="left", padx=8)

        self.startup = tk.BooleanVar(value=_startup_enabled())
        ttk.Checkbutton(
            frame,
            text="Start ProxiTune with Windows (launch minimized)",
            variable=self.startup,
            command=self._toggle_startup,
        ).pack(anchor="w", pady=(2, 4))
        ttk.Label(
            frame,
            text="Keep both speakers connected to this laptop. The phone sends controls over Wi-Fi.",
            wraplength=500,
            foreground="#555",
        ).pack(anchor="w", pady=(8, 0))

    def _start_server(self) -> None:
        try:
            zones = _load_zone_devices(self.config_path)
            self.server = CompanionServer(
                zones,
                self.token,
                NativeWindowsSwitcher().set_default,
                MediaController().control,
            )
            self.server.start("0.0.0.0", self.port)
            self._refresh_pairing()
            self.status.set(f"Ready on Wi-Fi · port {self.port}")
        except Exception as exc:  # noqa: BLE001 - show setup errors in the UI
            self.server = None
            self.status.set("Setup error")
            messagebox.showerror("ProxiTune could not start", str(exc), parent=self.root)

    def _refresh_pairing(self) -> None:
        self.ip = _local_ip()
        base_url = f"http://{self.ip}:{self.port}"
        payload = "proxitune://pair?" + urlencode({"url": base_url, "token": self.token})
        self.url_var.set(base_url + "\nPairing token is embedded in the QR code.")
        try:
            import qrcode
            from PIL import ImageTk

            image = qrcode.make(payload).convert("RGB")
            image.thumbnail((360, 360))
            self._qr_image = ImageTk.PhotoImage(image)
            self.qr_label.configure(image=self._qr_image, text="")
        except ImportError:
            self.qr_label.configure(text="Install the desktop extras to show a QR code:\npython -m pip install -e '.[desktop]'")

    def _copy_url(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.url_var.get().splitlines()[0])
        self.status.set("Pairing URL copied")

    def _regenerate(self) -> None:
        if not messagebox.askyesno("Regenerate token", "Existing phones will need to scan the new QR code. Continue?", parent=self.root):
            return
        self.token = secrets.token_urlsafe(18)
        _state_path().write_text(json.dumps({"token": self.token}, indent=2), encoding="utf-8")
        if self.server is not None:
            self.server.stop()
        self._start_server()

    def _toggle_startup(self) -> None:
        try:
            _set_startup(self.startup.get(), self.config_path)
            self.status.set("Windows startup setting saved")
        except OSError as exc:
            self.startup.set(not self.startup.get())
            messagebox.showerror("Startup setting failed", str(exc), parent=self.root)

    def _start_tray(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw

            logo_path = _asset_path("proxitune-logo.png")
            if logo_path is not None:
                icon_image = Image.open(logo_path).convert("RGBA")
                icon_image.thumbnail((64, 64), Image.Resampling.LANCZOS)
            else:
                icon_image = Image.new("RGB", (64, 64), "#176b3a")
                ImageDraw.Draw(icon_image).ellipse((12, 12, 52, 52), fill="white")
            menu = pystray.Menu(
                pystray.MenuItem("Show ProxiTune", lambda icon, item: self.root.after(0, self._show_window)),
                pystray.MenuItem("Quit", lambda icon, item: self.root.after(0, self._quit)),
            )
            self._tray = pystray.Icon("ProxiTune", icon_image, "ProxiTune", menu)
            self._tray_thread = threading.Thread(target=self._tray.run, name="proxitune-tray", daemon=True)
            self._tray_thread.start()
        except ImportError:
            self._tray = None

    def _hide_window(self) -> None:
        self.root.withdraw()

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def _quit(self) -> None:
        if self.server is not None:
            self.server.stop()
        if self._tray is not None:
            self._tray.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ProxiTune Windows desktop companion")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--minimized", action="store_true")
    args = parser.parse_args()
    config = Path(args.config)
    if not config.is_absolute() and not config.exists():
        executable_dir = Path(sys.executable).resolve().parent
        candidates = [
            executable_dir / config,
            executable_dir.parent / config,
            Path(__file__).resolve().parents[2] / config,
        ]
        config = next((candidate for candidate in candidates if candidate.exists()), config)
    DesktopApp(str(config), args.port, args.minimized).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
