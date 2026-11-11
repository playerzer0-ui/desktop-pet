"""Starts the desktop pet.

    python main.py          Pip
    python main.py mira     another character (a folder in character/)

The built game has no console, so errors are shown in a message box, and a crash is written to logs/crash.log.
"""
import os, sys, traceback

def show_error(text):
    print(text, file=sys.stderr)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Desktop Pet", text)
    except Exception:
        pass  # no screen: the console line is all there is

if __name__ == "__main__":
    # Wayland doesn't let apps place their own windows, so she runs in X11 mode (as start.sh does)
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    try:
        from engine.character import DEFAULT
        from desktop.app import main
        main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    except SystemExit as e:
        if isinstance(e.code, str):  # a message for the player
            show_error(e.code)
            sys.exit(1)
        raise
    except Exception:
        from engine import config
        details = traceback.format_exc()
        try:
            os.makedirs(config.LOG_DIR, exist_ok=True)
            path = os.path.join(config.LOG_DIR, "crash.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write(details)
        except OSError:
            path = None
        show_error("Something went wrong, and Desktop Pet has to close.\n\n" + details.strip().splitlines()[-1]
                   + (f"\n\nThe details are in {path}" if path else ""))
        sys.exit(1)
