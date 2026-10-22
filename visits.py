"""How long a character can stay each day: daily_minutes in their character.toml (Pip: 240, her real body back
home goes without food or water while she dreamwalks). It counts every sitting that day, and starts over at midnight.

    visits.minutes_used(save, open_minutes)              minutes she's been here today (save + this sitting so far)
    visits.minutes_left(save, character, open_minutes)   minutes she has left today (None = no limit)
    visits.resting(character)                            today's time is used up: she won't come out (checked at
                                                         launch, from her save alone, before the model starts)

The minutes themselves are kept in the save by trust.stayed (today.minutes), the same count that earns stay points.
Session warns WARN_MINUTES before the end, and says goodbye when it's up (see Session.wants_to_speak).
"""
import datetime
from save import load_save

WARN_MINUTES = 10  # she says her time is nearly up this long before the end

def minutes_used(save, open_minutes=0.0):
    """Minutes she's been here today: what the save has for today, plus open_minutes not counted into it yet."""
    today = datetime.date.today().isoformat()
    counted = save.get("today", {}).get("minutes", 0) if save.get("last_day") == today else 0
    return counted + open_minutes

def minutes_left(save, character, open_minutes=0.0):
    """Minutes she has left today (can go below 0), or None if the character has no daily limit."""
    if character.daily_minutes is None:
        return None
    return character.daily_minutes - minutes_used(save, open_minutes)

def resting(character):
    """True if she's used up today's time: she stays home until tomorrow."""
    left = minutes_left(load_save(character.save_path), character)
    return left is not None and left <= 0
