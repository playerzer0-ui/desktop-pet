"""Talk to Pip in the terminal (the prototype until she becomes a real desktop pet).

    python main.py

The app itself lives in cli/, and everything Pip does lives in session.py.
"""
from cli.app import main
import os
import subprocess

subprocess.run(["cmd", "/c", "cls"] if os.name == "nt" else ["clear"], check=False)
main()
