"""Paths, the server's port, the context size and the model.

    HERE   the game itself: code, characters, the bundled llama-server
    DATA   the player's own files (saves, logs, cache, the model), kept apart so updates never touch them:
           %LOCALAPPDATA%\\DesktopPet on Windows, ~/.local/share/desktop-pet on Linux.
           PET_DATA_DIR=<folder> puts them somewhere else (the tests use it).
"""
import os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # one up from engine/

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
CACHE_DIR = os.path.join(DATA, "cache")  # prompts the server has already read

PORT = int(os.environ.get("PET_PORT", 8080))
SERVER = f"http://127.0.0.1:{PORT}"  # not "localhost": on Windows that tries IPv6 first, ~2 s per request
N_CTX = 12288  # context per character (at 8192 she forgot the chat after ~10 exchanges)
FORGET_AT = 0.75  # this full, she forgets the oldest chat lines

# change all four together to switch models
MODEL_FILE = "Qwen3.5-4B-Q5_K_M.gguf"
MODEL_URL = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q5_K_M.gguf"
MODEL_SHA256 = "8814232b85594dcd46c50e5b8b29324a7efe9e746edbe8a3d1df3d3fce7aad39"
MODEL_SIZE = 3_143_656_608  # bytes

def _model():
    """DATA/models, or models/ next to the code. If in neither yet: where it will be downloaded."""
    for folder in (os.path.join(DATA, "models"), os.path.join(HERE, "models")):
        if os.path.exists(os.path.join(folder, MODEL_FILE)):
            return os.path.join(folder, MODEL_FILE)
    return os.path.join(DATA, "models", MODEL_FILE)

MODEL = _model()
