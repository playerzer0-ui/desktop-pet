import json, os, shutil, sys

# Each character's memory of you between runs, in saves/<character>.json (see character.py).
# Not in git: every player has their own.
# Next to it, <character>.json.bak is the save as it was before the last write: if the pet is killed or the power
# goes while a save is being written, the main file can be left cut short, and the backup is loaded instead.

class Save(dict):
    """The save data (a plain dict, written as JSON) plus the file it lives in, so write_save(data) knows where."""
    def __init__(self, path, data=()):
        super().__init__(data)
        self.path = path

def load_save(path):
    try:
        return Save(path, _read(path))
    except FileNotFoundError:
        # a first visit, or the save was deleted to start over (a write never leaves it missing: see write_save)
        return Save(path, {"trust": 1})
    except (ValueError, OSError) as e:  # cut short or garbled (json's errors are ValueErrors)
        problem = e
    try:
        data = _read(path + ".bak")
    except (ValueError, OSError):
        raise SystemExit(f"{path} can't be read ({problem}), and neither can its backup {path}.bak. "
                         f"Fix or delete the file to start over.")
    print(f"{path} can't be read ({problem}): loaded the backup from before the last save instead.", file=sys.stderr)
    return Save(path, data)

def _read(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("not a save")
    return data

def write_save(data):
    """Written to a temporary file first and then swapped in, so the save on disk is always a whole one:
    either the old one or the new one, never half of each. The old one is kept as the backup."""
    os.makedirs(os.path.dirname(data.path) or ".", exist_ok=True)
    tmp = data.path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if not os.path.exists(data.path):
        if os.path.exists(data.path + ".bak"):
            os.remove(data.path + ".bak")  # (the backup of a save that was deleted to start over: not this one's)
    elif _readable(data.path):
        shutil.copyfile(data.path, data.path + ".bak")  # (a cut-short main file never replaces a good backup)
    os.replace(tmp, data.path)

def _readable(path):
    try:
        _read(path)
        return True
    except (ValueError, OSError):
        return False

def stage_of(trust):
    # two trust levels per stage: 1-2 -> 1, 3-4 -> 2, ... 9-10 -> 5 (see the arc table in a character's events.md)
    trust = min(max(trust, 1), 10)
    return (trust + 1) // 2
