import json, os

# Each character's memory of you between runs, in saves/<character>.json (see character.py).
# Not in git: every player has their own.

class Save(dict):
    """The save data (a plain dict, written as JSON) plus the file it lives in, so write_save(data) knows where."""
    def __init__(self, path, data=()):
        super().__init__(data)
        self.path = path

def load_save(path):
    try:
        with open(path, encoding="utf-8") as f:
            return Save(path, json.load(f))
    except FileNotFoundError:
        return Save(path, {"trust": 1})

def write_save(data):
    os.makedirs(os.path.dirname(data.path), exist_ok=True)
    with open(data.path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def stage_of(trust):
    # two trust levels per stage: 1-2 -> 1, 3-4 -> 2, ... 9-10 -> 5 (see the arc table in a character's events.md)
    trust = min(max(trust, 1), 10)
    return (trust + 1) // 2
