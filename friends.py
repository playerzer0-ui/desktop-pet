"""Bringing a friend along: [friend] in a character's character.toml. Pip, at the highest trust, says on her way out
(Say goodbye, or when her time is up) that she'll send her best friend Vesper to rest here, and the next day the
friend comes instead of her. (After that day, Pip comes back on her own; both together is still to come.)

It's kept in the inviter's save (Pip's), so the friend's own save stays hers alone:

    save["friend"] = {"folder": "mira", "invited_on": "2026-10-23", "visit_day": None}

    friends.invite_due(save, character)        she's ready to invite, and hasn't yet
    friends.invite(save, character)            the invite for her goodbye (a stage direction's text), or None.
                                               Marks it in her save, with a memory
    friends.gone_today(save)                   at launch: she invited her friend today, so she's away until tomorrow
    friends.visiting_today(save)               at launch: the friend's folder if today is the friend's day, else None

Like a story step (story.py), the friend's day waits for your next visit: skip a few days and nothing is missed.
"""
import datetime
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
