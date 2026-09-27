import os
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.main_window import ScratchpadWindow
from ui.widgets import DummyVisualizerEmitter


def configure_qt_platform():
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    session = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    desk_session = (os.environ.get("DESKTOP_SESSION") or "").lower()
    wayland_display = os.environ.get("WAYLAND_DISPLAY")

    if "hyprland" in desktop or "hyprland" in desk_session or session == "wayland" or bool(wayland_display):
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
        os.environ.setdefault("QT_WAYLAND_FORCE_DPI", "96")
        print("Hyprland/Wayland detected; forcing Qt to use the Wayland platform plugin.")
        return "wayland"

    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    return "xcb"


def main():
    try:
        from diagnostics import run_diagnostics
        run_diagnostics()
    except Exception as e:
        print(f"Diagnostics error: {e}")

    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or ""
    session_type = os.environ.get("XDG_SESSION_TYPE") or ""

    if not display and not session_type and "hyprland" not in desktop.lower():
        print("Guru Agent requires a desktop session (X11 or Wayland).")
        print("No DISPLAY/WAYLAND_DISPLAY was detected, so no UI window can be opened here.")
        return 1

    platform = configure_qt_platform()
    print("Starting Guru Agent UI...")
    print(f"Desktop session detected: {display or 'Wayland'} ({platform})")

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("guru-agent")
        app.setDesktopFileName("guru-agent")
        dummy_emitter = DummyVisualizerEmitter()
        window = ScratchpadWindow(
            visualizer_state_emitter=dummy_emitter.state_signal,
            visualizer_glow_emitter=dummy_emitter.glow_signal,
        )
        # Ensure window behaves as a normal tiled window in Hyprland
        window.setWindowFlag(Qt.WindowType.Window, True)
        window.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        window.show()
        window.move(40, 40)
        window.raise_()
        window.activateWindow()
        return app.exec()
    except Exception as exc:
        print(f"Failed to launch Guru Agent UI: {exc}")
        raise


if __name__ == "__main__":
    sys.exit(main())
