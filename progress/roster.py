"""The cast as a whole: who invites whom, and who comes on a given day.
Rules: character/roster.toml. What has happened: the player's saves/roster.json, shared by everyone:

    {"unlocked": {"mira": {"by": "pip", "invited_on": "2026-10-23", "visit_day": "2026-10-24",
                           "introduced": "2026-10-25"}},
     "today": {"day": "2026-11-02", "members": ["pip", "mira"], "story": null}}

At trust 10 Pip invites Vesper on her way out, the next day Vesper comes on her own, and from then on they come
in roster.toml's lineups (or as a story needs).
"""
import datetime, os, random, threading, tomllib
from dataclasses import dataclass, field
from mind import memory
from progress import story, trust
from engine.character import Character, DEFAULT
from engine.config import HERE, SAVES_DIR
from engine.save import Save, load_save, write_save

RULES = os.path.join(HERE, "character", "roster.toml")
PATH = os.path.join(SAVES_DIR, "roster.json")
ON_SCREEN = 2  # most characters on the desktop at once (on_screen in roster.toml)
_lock = threading.RLock()  # two minds on their own threads may write roster.json

# --- the rules (roster.toml) ---

def rules(path=None):
    """roster.toml, checked: {"on_screen", "unlocks", "lineups"}. A mistake fails loudly at launch."""
    with open(path or RULES, "rb") as f:
        r = tomllib.load(f)
    unlocks, lineups = r.get("unlocks", []), r.get("lineups", [])
    on_screen = r.get("on_screen", ON_SCREEN)
    if not isinstance(on_screen, int) or on_screen < 1:
        raise ValueError("roster.toml: on_screen must be a whole number, 1 or more")
    folders = {f for f in os.listdir(os.path.join(HERE, "character"))
               if os.path.isfile(os.path.join(HERE, "character", f, "character.toml"))}
    known = {DEFAULT}  # in order: someone can only invite once she can come herself
    for i, u in enumerate(unlocks, 1):
        where = f"roster.toml [[unlocks]] {i}"
        missing = [key for key in ("who", "by", "at_trust", "invite", "memory") if key not in u]
        if missing:
            raise ValueError(f"{where} is missing: {', '.join(missing)}")
        for key in ("who", "by"):
            if u[key] not in folders:
                raise ValueError(f"{where}: {key} = {u[key]!r} isn't a character in character/")
        if u["by"] not in known:
            raise ValueError(f"{where}: {u['by']!r} invites {u['who']!r}, but nobody has invited {u['by']!r} yet "
                             "(an unlock above this one has to)")
        if u["who"] in known:
            raise ValueError(f"{where}: {u['who']!r} is already in the cast (the first character, or invited above)")
        if not isinstance(u["at_trust"], int) or not 1 <= u["at_trust"] <= 10:
            raise ValueError(f"{where}: at_trust must be a whole number from 1 to 10")
        known.add(u["who"])
    for i, l in enumerate(lineups, 1):
        where = f"roster.toml [[lineups]] {i}"
        members = l.get("members")
        if not isinstance(members, list) or not members or len(set(members)) != len(members):
            raise ValueError(f"{where}: members must be a list of different folders")
        if len(members) > on_screen:
            raise ValueError(f"{where}: at most {on_screen} on the desktop at once (on_screen)")
        for m in members:
            if m not in known:
                raise ValueError(f"{where}: {m!r} is neither the first character nor invited in [[unlocks]]")
        if not isinstance(l.get("weight"), int) or l["weight"] < 0:
            raise ValueError(f"{where}: weight must be a whole number, 0 or more")
        if not isinstance(l.setdefault("note", ""), str):
            raise ValueError(f"{where}: note must be text")
    if lineups and not sum(l["weight"] for l in lineups):
        raise ValueError("roster.toml: the lineups' weights are all 0")
    return {"on_screen": on_screen, "unlocks": unlocks, "lineups": lineups}

def _partner(folder, r, among=None):
    """The one who invited `folder`, else the first one she invited (only from `among`, if given), or None."""
    for u in r["unlocks"]:
        if u["who"] == folder and (among is None or u["by"] in among):
            return u["by"]
    for u in r["unlocks"]:
        if u["by"] == folder and (among is None or u["who"] in among):
            return u["who"]
    return None

def _pair(a, b, r):
    """Two folders in lineup order: the one who invited the other leads."""
    return [b, a] if any(u["by"] == b and u["who"] == a for u in r["unlocks"]) else [a, b]

# --- what has happened (roster.json) ---

def state():
    """roster.json as a Save. The first time, it's built from old saves (see _from_old_saves)."""
    with _lock:
        if not os.path.exists(PATH):
            data = Save(PATH, _from_old_saves())
            if data:
                write_save(data)
        else:
            data = load_save(PATH, default={})
        data.setdefault("unlocked", {})
        return data

def _from_old_saves(r=None):
    """The roster from before roster.json existed, when an inviter's save kept it as save["friend"]."""
    data = {}
    for u in (r or rules())["unlocks"]:
        path = Character(u["by"]).save_path
        if not os.path.isfile(path):
            continue
        old = load_save(path).get("friend")
        if not old or old.get("folder") != u["who"]:
            continue
        data.setdefault("unlocked", {})[u["who"]] = {
            "by": u["by"], "invited_on": old["invited_on"], "visit_day": old.get("visit_day"),
            "introduced": old.get("introduced")}
        day = old.get("today")
        if day:
            members = {"together": [u["by"], u["who"]], "only_her": [u["by"]], "only_friend": [u["who"]]}[day["who"]]
            data["today"] = {"day": day["day"], "members": members,
                             "story": (u["who"] if day.get("story") else None)}
    return data

# --- in a sitting ---

def _due(save, character):
    """The unlock she should give on her way out now, else None."""
    unlocked = state()["unlocked"]
    for u in rules()["unlocks"]:
        if u["by"] == character.folder and u["who"] not in unlocked and save.get("trust", 1) >= u["at_trust"]:
            return u
    return None

def invite_due(save, character):
    return _due(save, character) is not None

def invite(save, character, today=None):
    """Her invite on her way out (text for a stage direction), or None. Marked once, and she remembers it."""
    today = (today or datetime.date.today()).isoformat()
    with _lock:
        u = _due(save, character)
        if not u:
            return None
        data = state()
        data["unlocked"][u["who"]] = {"by": character.folder, "invited_on": today, "visit_day": None,
                                      "introduced": None}
        write_save(data)
    memory.remember(save, "milestone", character.fill(u["memory"]))
    write_save(save)
    return character.fill(u["invite"])

def introduce(character, company=(), today=None):
    """The first day she comes with someone she invited: how her greeting introduces them, once. Else None."""
    with _lock:
        data = state()
        for u in rules()["unlocks"]:
            entry = data["unlocked"].get(u["who"])
            if (u["by"] != character.folder or not entry or entry.get("introduced") or not u.get("introduce")
                    or (company and Character(u["who"]).name not in company)):
                continue
            entry["introduced"] = (today or datetime.date.today()).isoformat()
            write_save(data)
            return character.fill(u["introduce"])
    return None

# --- at launch: who comes today ---

@dataclass
class Today:
    members: list                # folders, the first one leads (her save and daily time decide for everyone)
    note: str | None = None      # for the leader's greeting: why the others aren't here
    invited_today: bool = False  # someone sent an invite today: nobody comes out
    story: str | None = None     # whose story step picked today's lineup

@dataclass
class Need:
    """A lineup a story step (or a private major quest) needs today."""
    members: list
    owner: str | None = None  # whose story it is (None for a private quest)

def today(lead=DEFAULT, day=None, pick=random.choices, need=None):
    """Who comes today. Only the first character runs the roster; any other, opened by name, comes alone.
    pick and need are for the tests."""
    if lead != DEFAULT:
        return Today([lead])
    day = day or datetime.date.today()
    iso = day.isoformat()
    with _lock:
        data, r = state(), rules()
        unlocked = data["unlocked"]
        for u in r["unlocks"]:  # someone's own first day: the first launch after her invite
            entry = unlocked.get(u["who"])
            if entry and entry["visit_day"] is None and iso > entry["invited_on"]:
                entry["visit_day"] = iso
                write_save(data)
            if entry and entry["visit_day"] == iso:
                return Today([u["who"]])
        if any(e["visit_day"] is None and e["invited_on"] == iso for e in unlocked.values()):
            return Today([lead], invited_today=True)  # she went home after inviting them
        settled = [DEFAULT] + [u["who"] for u in r["unlocks"]
                               if unlocked.get(u["who"], {}).get("visit_day") and iso > unlocked[u["who"]]["visit_day"]]
        if len(settled) == 1:
            return Today([DEFAULT])
        picked = data.get("today")
        if not picked or picked["day"] != iso:
            picked = {"day": iso, "story": None}
            intro = next((u for u in r["unlocks"] if u["who"] in settled and u.get("introduce")
                          and not unlocked[u["who"]].get("introduced")), None)
            needed = None if intro else (need or stories_need)(settled, r, day)
            if intro:  # the first day together: she introduces them
                picked["members"] = [intro["by"], intro["who"]]
            elif needed:
                picked["members"], picked["story"] = needed.members, needed.owner
            else:
                open_ = [l for l in r["lineups"] if set(l["members"]) <= set(settled) and l["weight"]]
                picked["members"] = (pick(open_, weights=[l["weight"] for l in open_])[0]["members"]
                                     if open_ else [DEFAULT])
            data["today"] = picked
            write_save(data)
        members, owner = picked["members"], picked.get("story")
        note = None
        if owner and owner not in members:  # someone else's story keeps her away: she tells it, if it's hers to tell
            note = _tell_for(members[0], settled, r, day)
        if not note and (not owner or owner not in members):
            lineup = next((l for l in r["lineups"] if l["members"] == members), None)
            if lineup and lineup["note"]:
                note = Character(members[0]).fill(lineup["note"]) + "."
        return Today(list(members), note=note, story=owner)

def _save_of(folder):
    """A character and her save, ready for story.py (with her gates, and caught up)."""
    c = Character(folder)
    data = load_save(c.save_path)
    data.gates = c.gates
    for key, empty in (("points", 0), ("quests_done", [])):  # a save that's never been opened has neither
        data.setdefault(key, empty)
    story.catch_up(data, c)
    return c, data

def private_due(data, character):
    """True if the quest holding her trust back is private: it only comes up when she's alone with the user,
    so she needs a day on her own (Vesper's real name waited weeks without this)."""
    quest = character.major_quests.get(trust.at_gate(data))
    return bool(quest and quest["private"])

def stories_need(settled, r, day=None):
    """The lineup a story step needs today, as a Need, or None. Invited ones' stories first, then the first
    character's. Failing that, a private major quest that's due brings that one alone."""
    order = [u["who"] for u in r["unlocks"] if u["who"] in settled] + [DEFAULT]
    for folder in order:
        partner = _partner(folder, r, settled)
        c, data = _save_of(folder)
        step = story.next_step(data, c, day)
        wanted = step and story.who_comes(step, folder, partner)
        if not wanted:
            continue
        members = wanted[0]
        if step.get("day") == "together":
            members = _pair(folder, partner, r)
        if set(members) <= set(settled):
            return Need(members, owner=folder)
    for folder in order:
        c, data = _save_of(folder)
        if _partner(folder, r, settled) and private_due(data, c):
            return Need([folder])
    return None

def _tell_for(teller, settled, r, day=None):
    """When `teller` comes alone because someone's story keeps that one away: what she says about it in her
    greeting (and that step is over). Else None."""
    for folder in settled:
        if folder == teller:
            continue
        c, data = _save_of(folder)
        step = story.next_step(data, c, day)
        if not step or (step.get("told_by") != teller and _partner(folder, r, settled) != teller):
            continue
        told = story.tell(data, c, Character(teller), day)
        if told:
            return told + "."
    return None
