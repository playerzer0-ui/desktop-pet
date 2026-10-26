"""A character as a desktop pet: they wander along the bottom of your screen.

    python main.py          Pip
    python main.py mira     another character (a folder in character/, with a character.toml)

Click them to talk, right-click for the menu (status, memories, goodbye), drag them anywhere.
The app itself lives in desktop/, and everything they do lives in session.py; who they are is their folder.
Each sitting's reply stats (timings, context, mood, trust) are written to <character>.log, e.g. pip.log, for tuning,
in the logs/ of the player's data folder (config.DATA, like %LOCALAPPDATA%\\DesktopPet).

The built game (build.ps1) has no console window, so anything that stops it is shown in a message box too, and a
crash is written to logs/crash.log.
"""
import os, sys, traceback

def show_error(text):
    print(text, file=sys.stderr)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Desktop Pet", text)
    except Exception:
        pass  # (no screen to show it on: the console line above is all there is)

if __name__ == "__main__":
    try:
        from character import DEFAULT
        from desktop.app import main
        main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    except SystemExit as e:
        if isinstance(e.code, str):  # a message (no llama-server, a save that can't be read...): say it, then stop
            show_error(e.code)
            sys.exit(1)
        raise
    except Exception:
        import config
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
