"""Where things are and how the model runs: paths, the server's port, the context size.

Two places:
    HERE   the game itself: code, characters, the bundled llama-server. Read-only once installed.
    DATA   the player's own files, kept apart so updates and reinstalls never touch them:
               Windows   %LOCALAPPDATA%\\DesktopPet
               Linux     $XDG_DATA_HOME/desktop-pet (usually ~/.local/share/desktop-pet)
               macOS     ~/Library/Application Support/DesktopPet
           with saves/ (each character's memory of you), logs/ (each sitting's reply stats, server.log),
           cache/ (the server's already-read prompts) and models/ (the model, downloaded on first launch).
           PET_DATA_DIR=<folder> puts them somewhere else (the tests use it).
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))  # the desktop-pet folder (in the built game: its _internal folder)

def _data_dir():
    if os.environ.get("PET_DATA_DIR"):
        return os.path.abspath(os.environ["PET_DATA_DIR"])
    if os.name == "nt":
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local"), "DesktopPet")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/DesktopPet")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "desktop-pet")

DATA = _data_dir()
SAVES_DIR = os.path.join(DATA, "saves")
LOG_DIR = os.path.join(DATA, "logs")
CACHE_DIR = os.path.join(DATA, "cache")  # each character's already-read system prompt, saved by the server (see pet.warm_up)

PORT = int(os.environ.get("PET_PORT", 8080))  # override if port 8080 is taken
SERVER = f"http://127.0.0.1:{PORT}"  # (not "localhost": on Windows that tries IPv6 ::1 first, where llama-server
                                     #  isn't listening, and every request waited ~2 s for that to fail)
N_CTX = 8192  # context size

MODEL_FILE = "Qwen3.5-4B-Q5_K_M.gguf"
# where it's downloaded from (first launch: desktop/download.py; setup.ps1 / setup.sh), and its checksum
# (change all three together to switch models)
MODEL_URL = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q5_K_M.gguf"
MODEL_SHA256 = "8814232b85594dcd46c50e5b8b29324a7efe9e746edbe8a3d1df3d3fce7aad39"
MODEL_SIZE = 3_143_656_608  # bytes (for the download's progress bar and the free-space check)

def _model():
    """In DATA/models (where it's downloaded to), or next to the game in models/ (a copy that came with it, or a
    developer's from before DATA existed). If it's in neither yet: where it will be downloaded."""
    for folder in (os.path.join(DATA, "models"), os.path.join(HERE, "models")):
        if os.path.exists(os.path.join(folder, MODEL_FILE)):
            return os.path.join(folder, MODEL_FILE)
    return os.path.join(DATA, "models", MODEL_FILE)

MODEL = _model()
