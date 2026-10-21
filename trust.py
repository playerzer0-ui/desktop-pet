"""How much a character trusts you (1-10), earned from what you do together. It never goes down.

Daily things fill the bar slowly, each with a daily cap so they can't be farmed:
    day logged     +3 the first time you open her each day
    talking        per message of 3+ words, judged by the character: nice +2, neutral +1, rude +0 (max 10 a day)
    stay           +1 for every 15 minutes she's open (max 4 a day)
Quests give big chunks. A stage's MAJOR quest is a gate: until it's done, trust stops at the
top of that stage (and so do points, so they can't be saved up to skip a stage).
Minor quests just give points.
"""
import datetime, re
from save import Save, load_save, write_save, stage_of

TRUST_POINTS = [0, 15, 40, 70, 110, 160, 220, 290, 370, 460]  # points needed for trust 1, 2, ... 10
MAJOR_QUESTS = {1: None, 2: None, 3: None, 4: None}  # stage -> quest id that opens the next stage (None = no gate yet)

DAY_POINTS = 3
TALK_POINTS = {"nice": 2, "neutral": 1, "rude": 0}
TALK_CAP = 10
STAY_MINUTES, STAY_CAP = 15, 4

def start(path):
    """Call when a character opens. path = their save (Character.save_path).
    Returns the save data that the other functions update."""
    data = Save(path, {"trust": 1, "points": 0, "days_logged": 0, "last_day": None,
                       "today": {"talk": 0, "minutes": 0}, "messages": 0, "quests_done": []})
    data.update(load_save(path))
    data["trust"] = min(max(int(data["trust"]), 1), len(TRUST_POINTS))  # a trust typed into the save by hand...
    data["points"] = max(data["points"], TRUST_POINTS[data["trust"] - 1])  # ...gets the points it needs
    _new_day(data)
    write_save(data)
    return data

def talked(data, message, feeling):
    """One message from the user. feeling = how it felt to them: nice, neutral or rude."""
    _new_day(data)
    data["messages"] += 1
    if len(re.findall(r"\w+", message)) >= 3:  # "hi", "ok", "lol" don't count
        gain = min(TALK_POINTS.get(feeling, 1), TALK_CAP - data["today"]["talk"])
        if gain > 0:
            data["today"]["talk"] += gain
            _add(data, gain)
    write_save(data)

def stayed(data, minutes):
    """The character has been open for this many more minutes."""
    _new_day(data)
    before = min(int(data["today"]["minutes"] // STAY_MINUTES), STAY_CAP)
    data["today"]["minutes"] += minutes
    after = min(int(data["today"]["minutes"] // STAY_MINUTES), STAY_CAP)
    _add(data, after - before)
    write_save(data)

def quest_done(data, quest_id, points):
    """A quest was finished (does nothing if it was already done)."""
    if quest_id in data["quests_done"]:
        return
    data["quests_done"].append(quest_id)
    _add(data, points)  # after marking it done, so a major quest opens its gate first
    write_save(data)

def stage(data):
    return stage_of(data["trust"])

def summary(data, stage_names):
    """Everything a screen shows about trust and today, as plain values (front ends only format this).
    stage_names = the character's names for stages 1-5 (Character.stage_names)."""
    level = data["trust"]
    next_at = TRUST_POINTS[level] if level < 10 else None
    return {
        "trust": level, "stage": stage(data), "stage_name": stage_names[stage(data)],
        "points": data["points"], "next_trust_at": next_at,
        "points_to_next": next_at - data["points"] if next_at is not None else 0,
        "talk_today": data["today"]["talk"], "talk_cap": TALK_CAP,
        "minutes_today": data["today"]["minutes"], "quests_today": data["today"].get("quests", 0),
        "quests_done": len(data["quests_done"]), "days": data["days_logged"], "messages": data["messages"],
        "mood": data.get("mood") or "neutral",
    }

def _new_day(data):
    today = datetime.date.today().isoformat()
    if data["last_day"] != today:
        data["last_day"] = today
        data["today"] = {"talk": 0, "minutes": 0}
        data["days_logged"] += 1
        _add(data, DAY_POINTS)

def _limit(data):
    """Most points allowed right now: just short of the next stage, if its major quest isn't done."""
    for st, quest in sorted(MAJOR_QUESTS.items()):
        if quest and quest not in data["quests_done"]:
            return TRUST_POINTS[st * 2] - 1  # TRUST_POINTS[st * 2] = first trust level of the next stage
    return float("inf")

def _add(data, points):
    data["points"] = max(data["points"], min(data["points"] + points, _limit(data)))
    reached = sum(1 for need in TRUST_POINTS if data["points"] >= need)
    data["trust"] = max(data["trust"], reached)  # never goes down
