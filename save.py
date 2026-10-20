import json, os
from load import HERE

# Pip's memory of you between runs. Not in git: every player has their own.
SAVE = os.path.join(HERE, "save.json")

def load_save():
    try:
        with open(SAVE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"trust": 1}

def write_save(data):
    with open(SAVE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def stage_of(trust):
    # two trust levels per stage: 1-2 -> 1, 3-4 -> 2, ... 9-10 -> 5 (see character/pip/events.md)
    trust = min(max(trust, 1), 10)
    return (trust + 1) // 2
