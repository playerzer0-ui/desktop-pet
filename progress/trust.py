"""How much a character trusts you (1-10). It never goes down.

Daily points, each capped so they can't be farmed:
    day logged     +3 the first time you open her each day
    talking        per message of 3+ words: nice +2, neutral +1, rude +0 (max 10 a day)
    stay           +1 for every 15 minutes she's open (max 4 a day)
Quests give big chunks. Each stage's major quest is a gate: until it's done, points stop at the top of that stage.
"""
import datetime, re
from engine.save import Save, load_save, write_save, stage_of

TRUST_POINTS = [0, 15, 40, 70, 110, 160, 220, 290, 370, 460]  # points needed for trust 1, 2, ... 10

DAY_POINTS = 3
TALK_POINTS = {"nice": 2, "neutral": 1, "rude": 0}
TALK_CAP = 10
STAY_MINUTES, STAY_CAP = 15, 4

def start(path, gates=None):
    """Load her save when she opens. gates = stage -> the quest id that opens the next stage."""
    data = Save(path, {"trust": 1, "points": 0, "days_logged": 0, "last_day": None,
                       "today": {"talk": 0, "minutes": 0}, "messages": 0, "quests_done": []})
    data.update(load_save(path))
    data.gates = dict(gates or {})  # kept with the save, not in it
    data["trust"] = min(max(int(data["trust"]), 1), len(TRUST_POINTS))  # a trust typed in by hand...
    data["points"] = max(data["points"], TRUST_POINTS[data["trust"] - 1])  # ...gets the points it needs
    for st, quest in data.gates.items():  # gates already behind her count as done, or trust would stop for good
        if st < stage(data) and quest not in data["quests_done"]:
            data["quests_done"].append(quest)
    _new_day(data)
    write_save(data)
    return data

def talked(data, message, feeling):
    _new_day(data)
    data["messages"] += 1
    if len(re.findall(r"\w+", message)) >= 3:  # "hi", "ok", "lol" don't count
        gain = min(TALK_POINTS.get(feeling, 1), TALK_CAP - data["today"]["talk"])
        if gain > 0:
            data["today"]["talk"] += gain
            _add(data, gain)
    write_save(data)

def stayed(data, minutes):
    _new_day(data)
    before = min(int(data["today"]["minutes"] // STAY_MINUTES), STAY_CAP)
    data["today"]["minutes"] += minutes
    after = min(int(data["today"]["minutes"] // STAY_MINUTES), STAY_CAP)
    _add(data, after - before)
    write_save(data)

def quest_done(data, quest_id, points):
    if quest_id in data["quests_done"]:
        return
    data["quests_done"].append(quest_id)
    _add(data, points)  # after marking it done, so a major quest opens its gate first
    write_save(data)

def stage(data):
    return stage_of(data["trust"])

def summary(data, stage_names):
    """Everything the Status card shows, as plain values."""
    level = data["trust"]
    next_at = TRUST_POINTS[level] if level < 10 else None
    return {
        "trust": level, "stage": stage(data), "stage_name": stage_names[stage(data)],
        "points": data["points"], "next_trust_at": next_at,
        "points_to_next": next_at - data["points"] if next_at is not None else 0,
        "progress": (data["points"] - TRUST_POINTS[level - 1]) / (next_at - TRUST_POINTS[level - 1])
                    if next_at is not None else 1.0,  # 0-1 toward the next level
        "talk_today": data["today"]["talk"], "talk_cap": TALK_CAP,
        "minutes_today": data["today"]["minutes"], "quests_today": data["today"].get("quests", 0),
        "quests_done": len(data["quests_done"]), "days": data["days_logged"], "messages": data["messages"],
        "mood": data.get("mood") or "neutral",
        "gated": at_gate(data) is not None,
    }

def _new_day(data):
    today = datetime.date.today().isoformat()
    if data["last_day"] != today:
        data["last_day"] = today
        data["today"] = {"talk": 0, "minutes": 0}
        data["days_logged"] += 1
        _add(data, DAY_POINTS)

def at_gate(data):
    """The stage whose major quest is holding trust back right now, else None."""
    st = _gate(data)
    return st if st is not None and data["points"] >= _limit(data) else None

def _gate(data):
    """The first stage whose major quest isn't done yet, or None."""
    for st, quest in sorted(getattr(data, "gates", {}).items()):
        if quest and quest not in data["quests_done"]:
            return st
    return None

def _limit(data):
    """Most points allowed now: just short of the next stage, if its gate is closed."""
    st = _gate(data)
    return TRUST_POINTS[st * 2] - 1 if st is not None else float("inf")

def _add(data, points):
    data["points"] = max(data["points"], min(data["points"] + points, _limit(data)))
    reached = sum(1 for need in TRUST_POINTS if data["points"] >= need)
    data["trust"] = max(data["trust"], reached)  # never goes down
