"""The cast as a whole: who invites whom, and who comes on a given day.
Rules: character/roster.toml. What has happened: the player's saves/roster.json, shared by everyone:

    {"unlocked": {"mira": {"by": "pip", "invited_on": "2026-10-23", "visit_day": "2026-10-24",
                           "introduced": "2026-10-25"}},
     "today": {"day": "2026-11-02", "members": ["pip", "mira"], "story": null, "why": "random"},
     "together": {"pip-ruby": {"days": 6, "last": "2026-11-02"}}}

"together" counts the days each pair has shared the desktop (shared_day, from launch.py), so strangers like Pip
and Ruby get to know each other over time (company.py tells them how well).

Each launch prints who comes and why (launch.py), like "today: pip, mira (random)".

At trust 10 Pip invites Vesper on her way out, the next day Vesper comes on her own, and from then on they come
in roster.toml's lineups (or as a story needs).

Someone can also arrive uninvited ([[arrivals]]): once `after` reaches a trust, a clock of `days` starts, and on the
day it runs out she comes on her own, a surprise, and from the day after that she's in the lineups too:

    {"arrived": {"ruby": {"started_on": "2026-12-01", "visit_day": "2027-01-01"}}}

For testing, today.json in the data folder (next to saves/, made by hand) decides who comes, every day, while it's
there: no invites, arrivals, introductions or story lineups. Delete it (or leave it empty, or broken: that's
printed at launch) and the roster takes over again. Only when
running from source: the built game ignores it, so a test file left in the data folder never decides a player's day.

    {"members": ["ruby", "pip"], "note": "optional: why the others aren't here (about the first one)"}
"""
import datetime, json, os, random, sys, threading, tomllib
from dataclasses import dataclass, field
from mind import memory
from progress import story, trust
from engine.character import Character, DEFAULT, is_character, is_npc
from engine.config import DATA, HERE, SAVES_DIR
from engine.save import Save, load_save, write_save

RULES = os.path.join(HERE, "character", "roster.toml")
PATH = os.path.join(SAVES_DIR, "roster.json")
FORCED = os.path.join(DATA, "today.json")  # (yours, for testing: see forced)
ON_SCREEN = 2  # most characters on the desktop at once (on_screen in roster.toml)
TOGETHER = 50  # the percent chance that two come instead of one (together in roster.toml)
_lock = threading.RLock()  # two minds on their own threads may write roster.json

# --- the rules (roster.toml) ---

def rules(path=None):
    """roster.toml, checked: {"on_screen", "together", "unlocks", "arrivals", "lineups"}. A mistake fails loudly
    at launch."""
    with open(path or RULES, "rb") as f:
        r = tomllib.load(f)
    unlocks, arrivals, lineups = r.get("unlocks", []), r.get("arrivals", []), r.get("lineups", [])
    on_screen = r.get("on_screen", ON_SCREEN)
    if not isinstance(on_screen, int) or on_screen < 1:
        raise ValueError("roster.toml: on_screen must be a whole number, 1 or more")
    together = r.get("together", TOGETHER)
    if not isinstance(together, int) or not 0 <= together <= 100:
        raise ValueError("roster.toml: together must be a whole number from 0 to 100 (a percent)")
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
    for i, a in enumerate(arrivals, 1):
        where = f"roster.toml [[arrivals]] {i}"
        missing = [key for key in ("who", "after", "at_trust", "days") if key not in a]
        if missing:
            raise ValueError(f"{where} is missing: {', '.join(missing)}")
        for key in ("who", "after"):
            if a[key] not in folders:
                raise ValueError(f"{where}: {key} = {a[key]!r} isn't a character in character/")
        if a["after"] not in known:
            raise ValueError(f"{where}: {a['after']!r} can't come yet, so her trust can't start {a['who']!r}'s clock "
                             "(an unlock or arrival above this one has to bring her)")
        if a["who"] in known:
            raise ValueError(f"{where}: {a['who']!r} is already in the cast (the first character, or invited above)")
        if not isinstance(a["at_trust"], int) or not 1 <= a["at_trust"] <= 10:
            raise ValueError(f"{where}: at_trust must be a whole number from 1 to 10")
        if not isinstance(a["days"], int) or a["days"] < 0:
            raise ValueError(f"{where}: days must be a whole number, 0 or more")
        known.add(a["who"])
    for i, l in enumerate(lineups, 1):
        where = f"roster.toml [[lineups]] {i}"
        members = l.get("members")
        if not isinstance(members, list) or not members or len(set(members)) != len(members):
            raise ValueError(f"{where}: members must be a list of different folders")
        if len(members) > on_screen:
            raise ValueError(f"{where}: at most {on_screen} on the desktop at once (on_screen)")
        for m in members:
            if m not in known:
                raise ValueError(f"{where}: {m!r} is neither the first character nor in [[unlocks]] or [[arrivals]]")
        if "weight" in l:
            raise ValueError(f"{where}: lineups have no weight any more (together, at the top, decides)")
        if not isinstance(l.setdefault("note", ""), str):
            raise ValueError(f"{where}: note must be text")
        if any(set(m["members"]) == set(members) for m in lineups[:i - 1]):
            raise ValueError(f"{where}: the same members as a lineup above it")
    return {"on_screen": on_screen, "together": together, "unlocks": unlocks, "arrivals": arrivals,
            "lineups": lineups}

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
        data.setdefault("arrived", {})
        data.setdefault("together", {})
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

# --- how well they know each other ---

def _pair_key(a, b):
    return "-".join(sorted((a, b)))

def knew_before(a, b, r=None):
    """One invited the other ([[unlocks]]), so they were friends before the desktop (Pip and Vesper)."""
    return any({u["by"], u["who"]} == {a, b} for u in (r or rules())["unlocks"])

def shared_day(members, today=None):
    """A day on the desktop together: each pair of them counts it, once a day (roster.json "together")."""
    iso = (today or datetime.date.today()).isoformat()
    with _lock:
        data, changed = state(), False
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                entry = data["together"].setdefault(_pair_key(a, b), {"days": 0, "last": None})
                if entry["last"] != iso:
                    entry["days"], entry["last"], changed = entry["days"] + 1, iso, True
        if changed:
            write_save(data)

def days_before(a, b, today=None):
    """How many days a and b had shared the desktop before today (today itself doesn't count)."""
    entry = state()["together"].get(_pair_key(a, b))
    if not entry:
        return 0
    iso = (today or datetime.date.today()).isoformat()
    return entry["days"] - (1 if entry["last"] == iso else 0)

# --- at launch: who comes today ---

@dataclass
class Today:
    members: list                # folders, the first one leads (her save and daily time decide for everyone)
    note: str | None = None      # for the leader's greeting: why the others aren't here
    invited_today: bool = False  # someone sent an invite today: nobody comes out
    story: str | None = None     # whose story step picked today's lineup
    why: str = ""                # what decided it, for the launch print (launch.py)

@dataclass
class Need:
    """A lineup a story step (or a private major quest) needs today."""
    members: list
    owner: str | None = None  # whose story it is (None for a private quest)

def forced(path=None):
    """today.json (see the top): who you've said comes, as a Today, or None if there's no such file.
    A mistake in it (or an empty file) raises ValueError, and today() falls back to the roster. The built game never
    reads it."""
    if getattr(sys, "frozen", False):  # (PyInstaller sets this)
        return None
    path = path or FORCED
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8-sig") as f:  # (-sig: Notepad may start the file with a BOM)
        data = json.load(f)
    members = data.get("members") if isinstance(data, dict) else None
    if not isinstance(members, list) or not members or len(set(members)) != len(members):
        raise ValueError('members must be a list of different character folders, like {"members": ["ruby", "pip"]}')
    for i, folder in enumerate(members):
        if is_npc(folder) and i:
            continue  # (an NPC can come along, to test a story she's in, but never leads)
        if not is_character(folder):
            raise ValueError(f"{folder!r} isn't a character's folder in character/"
                             + (" (an NPC can't lead: put her after someone)" if is_npc(folder) else ""))
    on_screen = rules()["on_screen"]
    if len(members) > on_screen:
        raise ValueError(f"{len(members)} members, but on_screen in roster.toml is {on_screen}")
    note = data.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError("note must be text")
    return Today(list(members), note=Character(members[0]).fill(note.rstrip(".")) + "." if note else None,
                 why="today.json")

def today(lead=DEFAULT, day=None, pick=random.choices, need=None):
    """Who comes today. Only the first character runs the roster; any other, opened by name, comes alone.
    While you have a today.json (forced), it decides instead, unless it's empty or has a mistake: then it's ignored
    (and says so). pick and need are for the tests."""
    if lead != DEFAULT:
        return Today([lead], why="opened by name")
    try:
        chosen = forced()
    except (ValueError, OSError) as e:  # empty, broken or wrong: the roster decides, as if it weren't there
        print(f"today.json: no one, relying on random\n  ({e})")
        chosen = None
    if chosen:
        print(f"today.json: {', '.join(chosen.members)} (delete it to go back to the roster)")
        return chosen
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
                return Today([u["who"]], why=f"her first day, invited by {Character(u['by']).name}")
        if any(e["visit_day"] is None and e["invited_on"] == iso for e in unlocked.values()):
            return Today([lead], invited_today=True, why="she invited someone today, so she's home")
        arrived = data["arrived"]
        for a in r["arrivals"]:  # an uninvited arrival: her clock starts when `after` reaches the trust...
            if a["who"] not in arrived and load_save(Character(a["after"]).save_path).get("trust", 1) >= a["at_trust"]:
                arrived[a["who"]] = {"started_on": iso, "visit_day": None}
                write_save(data)
            entry = arrived.get(a["who"])  # ...and on the day it runs out she comes on her own
            due = entry and datetime.date.fromisoformat(entry["started_on"]) + datetime.timedelta(days=a["days"])
            if entry and entry["visit_day"] is None and day >= due:
                entry["visit_day"] = iso
                write_save(data)
            if entry and entry["visit_day"] == iso:
                return Today([a["who"]], why="her first day, arrived on her own")
        settled = [DEFAULT] + [u["who"] for u in r["unlocks"]
                               if unlocked.get(u["who"], {}).get("visit_day") and iso > unlocked[u["who"]]["visit_day"]]
        settled += [a["who"] for a in r["arrivals"]
                    if arrived.get(a["who"], {}).get("visit_day") and iso > arrived[a["who"]]["visit_day"]]
        if len(settled) == 1:
            return Today([DEFAULT], why="the only one who can come yet")
        picked = data.get("today")
        if not picked or picked["day"] != iso:
            picked = {"day": iso, "story": None}
            intro = next((u for u in r["unlocks"] if u["who"] in settled and u.get("introduce")
                          and not unlocked[u["who"]].get("introduced")), None)
            needed = None if intro else (need or stories_need)(settled, r, day)
            if intro:  # the first day together: she introduces them
                picked["members"], picked["why"] = [intro["by"], intro["who"]], "the first day together: an introduction"
            elif needed:
                picked["members"], picked["story"] = needed.members, needed.owner
                picked["why"] = f"{Character(needed.owner).name}'s story" if needed.owner else "a private quest"
            else:
                options, chances = _choices(settled, r)
                picked["members"], picked["why"] = pick(options, weights=chances)[0]["members"], "random"
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
        return Today(list(members), note=note, story=owner, why=picked.get("why", "picked earlier today"))

def _choices(settled, r):
    """Today's possible lineups and the chance of each, for an ordinary day. Two rounds: first one or two
    (together percent for two), then which ones, evenly, so everyone who can come is as likely to as the others.
    A lineup in roster.toml with the same members gives the order (who leads) and the note; else the one who
    invited the other leads."""
    singles = [[f] for f in settled]
    pairs = ([_pair(a, b, r) for i, a in enumerate(settled) for b in settled[i + 1:]]
             if r["on_screen"] >= 2 else [])
    if not pairs:
        return [_lineup(singles[0], r)], [1]
    two = r["together"]
    options = [_lineup(m, r) for m in singles + pairs]
    chances = [(100 - two) / len(singles)] * len(singles) + [two / len(pairs)] * len(pairs)
    return options, chances

def _lineup(members, r):
    """roster.toml's lineup with these members (in its order, with its note), else a plain one."""
    return next((l for l in r["lineups"] if set(l["members"]) == set(members)), {"members": members, "note": ""})

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
    order = [u["who"] for u in r["unlocks"] + r["arrivals"] if u["who"] in settled] + [DEFAULT]
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
        if {m for m in members if not is_npc(m)} <= set(settled):  # (an NPC comes only like this)
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
