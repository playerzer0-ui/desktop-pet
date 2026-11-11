"""Each character's save: saves/<character>.json in the player's data folder, plus a .bak of the one before the
last write, loaded instead if the main file was cut short (the pet killed mid-write).
"""
import json, os, shutil, sys

class Save(dict):
    """The save data plus the file it lives in, so write_save(data) knows where."""
    def __init__(self, path, data=()):
        super().__init__(data)
        self.path = path

def load_save(path, default=None):
    """default = what a missing file starts as (trust 1)."""
    try:
        return Save(path, _read(path))
    except FileNotFoundError:
        return Save(path, {"trust": 1} if default is None else dict(default))
    except (ValueError, OSError) as e:  # cut short or garbled
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
    """Write to a temporary file, then swap it in: the file on disk is always a whole save."""
    os.makedirs(os.path.dirname(data.path) or ".", exist_ok=True)
    tmp = data.path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if not os.path.exists(data.path):
        if os.path.exists(data.path + ".bak"):
            os.remove(data.path + ".bak")  # the backup of a save that was deleted to start over
    elif _readable(data.path):
        shutil.copyfile(data.path, data.path + ".bak")  # a cut-short file never replaces a good backup
    os.replace(tmp, data.path)

def _readable(path):
    try:
        _read(path)
        return True
    except (ValueError, OSError):
        return False

def stage_of(trust):
    # two trust levels per stage: 1-2 -> 1, 3-4 -> 2, ... 9-10 -> 5
    trust = min(max(trust, 1), 10)
    return (trust + 1) // 2
