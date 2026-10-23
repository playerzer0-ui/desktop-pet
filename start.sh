#!/usr/bin/env bash
# Starts the desktop pet on Linux with the project's own Python (start.bat is the Windows one). Run ./setup.sh once first.
# Another character: ./start.sh mira
cd "$(dirname "$0")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
    echo "The pet isn't set up yet: run ./setup.sh first."
    exit 1
fi
# On Wayland, apps can't place their own windows, so she couldn't walk along the bottom of the screen or keep her
# speech bubble over her head. X11 mode (through XWayland) lets her. Set QT_QPA_PLATFORM yourself to choose otherwise.
if [ -n "$WAYLAND_DISPLAY" ] && [ -z "$QT_QPA_PLATFORM" ]; then
    export QT_QPA_PLATFORM=xcb
fi
exec .venv/bin/python main.py "$@"
