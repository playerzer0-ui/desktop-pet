"""Bringing a friend along: [friend] in a character's character.toml. Pip, at the highest trust, says on her way out
(Say goodbye, or when her time is up) that she'll send her best friend Vesper to rest here, and the next day the
friend comes instead of her. From the day after that, they mostly come together (desktop/scene.py), but now
and then one of them is busy back home and the other comes alone: picked once a day (plan).

It's kept in the inviter's save (Pip's), so the friend's own save stays hers alone:

    save["friend"] = {"folder": "mira", "invited_on": "2026-10-23", "visit_day": None}

    friends.invite_due(save, character)        she's ready to invite, and hasn't yet
    friends.invite(save, character)            the invite for her goodbye (a stage direction's text), or None.
                                               Marks it in her save, with a memory
    friends.gone_today(save)                   at launch: she invited her friend today, so she's away until tomorrow
    friends.visiting_today(save)               at launch: the friend's folder if today is the friend's day, else None
    friends.together(save)                     the friend's folder from the day after her own day, else None
    friends.plan(save, character)              at launch, from then on: who comes today, "together", "only_her"
                                               or "only_friend" (picked on the day's first launch, kept in her save)
    friends.introduce(save, character)         the first day they come together: how she introduces her friend in
                                               her greeting (a stage direction's text), or None. Marks it in her save

Like a story step (story.py), the friend's day waits for your next visit: skip a few days and nothing is missed.
"""
import datetime, random
import memory
from save import write_save

def invite_due(save, character):
    """True if she should invite her friend on her way out: she has one, trust is high enough, and she hasn't yet."""
    friend = character.friend
    return bool(friend and save.get("trust", 1) >= friend["at_trust"] and "friend" not in save)

def invite(save, character, today=None):
    """What she says on her way out to invite her friend (text for a stage direction), or None if it isn't due.
    Marks the invite in her save, so it's said only once, and she remembers it."""
    if not invite_due(save, character):
        return None
    today = today or datetime.date.today()
    save["friend"] = {"folder": character.friend["folder"], "invited_on": today.isoformat(), "visit_day": None}
    memory.remember(save, "milestone", character.fill(character.friend["memory"]))
    write_save(save)
    return character.fill(character.friend["invite"])

def gone_today(save, today=None):
    """True on the day she invited her friend: she's said her goodbye, so she's away for the rest of it
    (only the portal shows, like story.away). Her friend comes on your next visit after today."""
    invited = save.get("friend")
    today = (today or datetime.date.today()).isoformat()
    return bool(invited and invited["visit_day"] is None and invited["invited_on"] == today)

def together(save, today=None):
    """The friend's folder if she comes along with her today (any day after the friend's own day), else None."""
    invited = save.get("friend")
    today = (today or datetime.date.today()).isoformat()
    return invited["folder"] if invited and invited["visit_day"] and today > invited["visit_day"] else None

def plan(save, character, today=None, pick=random.choices, story_day=None):
    """Who comes today, once they can come together (together(save)): "together", "only_her" or "only_friend",
    picked by [friend] chances on the day's first launch and kept in her save, so opening the app again the same day
    brings the same ones. The first day is always together: it's the day she introduces her friend. After that, a
    story step that needs a certain lineup (story.py's day) decides instead of the chances (by_story is then True).
    None before then. pick = random.choices and story_day = stories_need (the tests stand in for them)."""
    if not together(save, today):
        return None
    invited, day = save["friend"], (today or datetime.date.today()).isoformat()
    if invited.get("today", {}).get("day") != day:
        chances = character.friend["chances"]
        needed = (story_day or stories_need)(save, character) if invited.get("introduced") else None
        if not invited.get("introduced"):
            who = "together"
        else:
            who = needed or pick(list(chances), weights=list(chances.values()))[0]
        invited["today"] = {"day": day, "who": who, "story": bool(needed)}
        write_save(save)
    return invited["today"]["who"]

def by_story(save):
    """True if today's lineup (plan) was set by a story step, not by chance: no "she's busy today" line then."""
    return bool(save.get("friend", {}).get("today", {}).get("story"))

def _friends_save(character):
    """Her friend (a Character) and the friend's save, ready for story.py (with the friend's gates)."""
    from character import Character
    from save import load_save
    friend = Character(character.friend["folder"])
    data = load_save(friend.save_path)
    data.gates = friend.gates
    for key, empty in (("points", 0), ("quests_done", [])):  # (a save that's never been opened has neither)
        data.setdefault(key, empty)
    return friend, data

def stories_need(save, character):
    """The lineup a story step of theirs needs today (story.day_needed), as plan's "together", "only_her" or
    "only_friend", or None. Her friend's story is asked first."""
    import story
    from save import Save
    friend, theirs = _friends_save(character)
    mine = Save(getattr(save, "path", None), {"points": 0, "quests_done": [], **save})
    mine.gates = character.gates
    for data, c, alone, away in ((theirs, friend, "only_friend", "only_her"), (mine, character, "only_her", "only_friend")):
        day = story.day_needed(data, c)
        if day:
            return {"together": "together", "alone": alone, "away": away}[day]
    return None

def tell_for_friend(character, today=None):
    """On a day only she comes because of her friend's story (an "away" step: the friend is missing), what she
    says about it in her greeting (a stage direction's text), and that step is over. Else None."""
    import story
    friend, theirs = _friends_save(character)
    told = story.tell(theirs, friend, character, today)
    return told + "." if told else None

def introduce(save, character, today=None):
    """The first day they come together, her greeting introduces her friend ([friend] introduce): its text for a
    stage direction, or None (already done, or nothing to say). Marked in her save, so it's only once."""
    invited = save.get("friend")
    text = (character.friend or {}).get("introduce")
    if not invited or not text or invited.get("introduced"):
        return None
    invited["introduced"] = (today or datetime.date.today()).isoformat()
    write_save(save)
    return character.fill(text)

def visiting_today(save, today=None):
    """The friend's folder if today is the friend's day (the first day you open her after the invite), else None.
    The first time it's asked on a later day, that day becomes the friend's day (kept in the save)."""
    invited = save.get("friend")
    if not invited:
        return None
    today = (today or datetime.date.today()).isoformat()
    if invited["visit_day"] is None and today > invited["invited_on"]:
        invited["visit_day"] = today
        write_save(save)
    return invited["folder"] if invited["visit_day"] == today else None
