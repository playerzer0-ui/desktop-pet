"""How long a character can stay each day (daily_minutes in her character.toml), over all sittings that day.
The minutes are counted into the save by trust.stayed.
"""
import datetime
from engine.save import load_save

WARN_MINUTES = 10  # she says her time is nearly up this long before the end

def minutes_used(save, open_minutes=0.0):
    """Minutes here today: the save's count plus open_minutes not counted into it yet."""
    today = datetime.date.today().isoformat()
    counted = save.get("today", {}).get("minutes", 0) if save.get("last_day") == today else 0
    return counted + open_minutes

def minutes_left(save, character, open_minutes=0.0):
    """Minutes left today (can go below 0), or None if she has no daily limit."""
    if character.daily_minutes is None:
        return None
    return character.daily_minutes - minutes_used(save, open_minutes)

def resting(character):
    """True if today's time is used up (checked at launch, before the model starts)."""
    left = minutes_left(load_save(character.save_path), character)
    return left is not None and left <= 0
