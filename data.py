"""The player's own files (config.DATA): created on launch, and moved over once from where they used to be.

Before DATA existed, saves/, cache/ and save.json lived in the game folder. move_old_files() moves them into DATA
the first time the game runs (only what isn't there yet, so it never overwrites anything), and leaves a note
behind so it's clear where they went.

    data.prepare()        at launch: make DATA's folders, and move old files over (desktop/app.py main)
"""
import os, shutil
from config import CACHE_DIR, DATA, HERE, LOG_DIR, SAVES_DIR

def prepare(old_root=HERE):
    """old_root = where the old files would be (the game folder; the tests give their own)."""
    for folder in (SAVES_DIR, LOG_DIR, CACHE_DIR, os.path.join(DATA, "models")):
        os.makedirs(folder, exist_ok=True)
    return move_old_files(old_root)

def move_old_files(old_root=HERE):
    """Saves and the prompt cache from the old spots in the game folder -> DATA. Returns what was moved."""
    moved = []
    old_saves, old_cache = os.path.join(old_root, "saves"), os.path.join(old_root, "cache")
    legacy = os.path.join(old_root, "save.json")  # (Pip's save before there were characters)
    if os.path.isfile(legacy) and not os.path.exists(os.path.join(SAVES_DIR, "pip.json")):
        moved.append(_move(legacy, os.path.join(SAVES_DIR, "pip.json")))
    for old, new in ((old_saves, SAVES_DIR), (old_cache, CACHE_DIR)):
        if not os.path.isdir(old) or os.path.abspath(old) == os.path.abspath(new):
            continue
        for name in os.listdir(old):
            if not os.path.isfile(os.path.join(old, name)) or os.path.exists(os.path.join(new, name)):
                continue
            if old == old_saves and (name.endswith(".lock") or name == "MOVED.txt"):
                continue  # (a lock belongs to a copy of the game running from there right now; the note stays)
            moved.append(_move(os.path.join(old, name), os.path.join(new, name)))
        if old == old_saves and moved:
            with open(os.path.join(old, "MOVED.txt"), "w", encoding="utf-8") as f:
                f.write(f"The saves now live in {SAVES_DIR}\n")
    return moved

def _move(old, new):
    os.makedirs(os.path.dirname(new), exist_ok=True)
    shutil.move(old, new)  # (a rename on the same drive: instant even for the cache's big files)
    return new
