"""Talk to Pip in the terminal (the desktop pet itself is main.py).

    python desktop_cli.py

The app itself lives in cli/, and everything Pip does lives in session.py.
"""
from cli.app import main
import os
import subprocess

subprocess.run(["cmd", "/c", "cls"] if os.name == "nt" else ["clear"], check=False)
main()
