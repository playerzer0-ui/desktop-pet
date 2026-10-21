"""A character as a desktop pet: they wander along the bottom of your screen.

    python main.py          Pip
    python main.py mira     another character (a folder in character/, with a character.toml)

Click them to talk, right-click for the menu (status, memories, goodbye), drag them anywhere.
The app itself lives in desktop/, and everything they do lives in session.py; who they are is their folder.
Each sitting's reply stats (timings, context, mood, trust) are written to <character>.log, e.g. pip.log, for tuning.
"""
import sys
from character import DEFAULT
from desktop.app import main

main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
