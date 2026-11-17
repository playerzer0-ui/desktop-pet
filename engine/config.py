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
JUDGE_CTX = 1024  # extra context for the judge's own slot (mind/judge.py): its questions are a few hundred tokens

# change all seven together to switch models (and give build_notices.py the new model's license: it stops the build
# for a model it has no notice for)
MODEL_FILE = "gemma-3-4b-it-Q5_K_M.gguf"
# (pinned to one commit of the repo, not "main": if the file there is ever replaced, the checksum below would fail
#  for everyone. Checked 2026-11-16: the size and SHA-256 Hugging Face reports are the ones below)
MODEL_URL = ("https://huggingface.co/unsloth/gemma-3-4b-it-GGUF/resolve/5a3566e716d80f709ed7b79817eaf7733d2a1fce/"
             "gemma-3-4b-it-Q5_K_M.gguf")
MODEL_SHA256 = "974e5c2f13c321fc3258b6fbf2ce326a09d8ace511aa6846df1db62baf7df7d4"
MODEL_SIZE = 2_829_698_176  # bytes
# How many snapshots of her conversation llama-server keeps per slot, to go back to when the end of it changes (each
# message carries a hidden note that the next one doesn't). The server's own default is 32, and at 115-160 MB each
# its memory grew 250-400 MB with every message (4.4 GB -> 8.7 GB in ten). Measured over 30-40 messages:
#   Gemma 3 4B   4: levels off about 0.7 GB above the start, no stalls. (0: flat, but twice in 40 messages she
#                read her whole prompt again, a 45-65 s reply. 1: the same stalls)
#   Qwen3.5-4B   2: levels off about 1.7 GB above the start. (0 or 1: she reads her whole prompt again on most
#                messages, 20 s a reply: this model can't go back without a snapshot)
MODEL_CHECKPOINTS = 4
# how she writes (mind/pet.py). Qwen: its own chat settings (temperature 0.7, top_p 0.8, top_k 20, min_p 0.05) and a
# light presence_penalty (0.5: at 1.5 she reached for odd words)
SAMPLING = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.05, "presence_penalty": 0.5}
# shown wherever the model is downloaded (the first-launch window, setup.ps1 / setup.sh) and in the build's notices.
# Gemma's terms ask for exactly this sentence, and for whoever receives the model to be told its use is restricted
# (licenses/Gemma-Terms-of-Use.txt, section 3.1). "" for a model with no such condition (Qwen: Apache 2.0)
MODEL_NOTICE = ("Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms "
                "(what it may not be used for: ai.google.dev/gemma/prohibited_use_policy)")

def _model():
    """DATA/models, or models/ next to the code. If in neither yet: where it will be downloaded."""
    for folder in (os.path.join(DATA, "models"), os.path.join(HERE, "models")):
        if os.path.exists(os.path.join(folder, MODEL_FILE)):
            return os.path.join(folder, MODEL_FILE)
    return os.path.join(DATA, "models", MODEL_FILE)

MODEL = _model()
