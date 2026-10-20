"""Pip as a desktop pet: she wanders along the bottom of your screen.

    python main.py

Click her to talk, right-click for the menu (status, memories, goodbye), drag her anywhere.
The app itself lives in desktop/, and everything Pip does lives in session.py.
The terminal version: python desktop_cli.py
"""
from desktop.app import main

main()
