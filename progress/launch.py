"""At launch, before any model starts: who comes out today, whether they come out at all, and in what mood."""
from dataclasses import dataclass
from engine.character import Character
from engine.save import load_save
from progress import roster, story, visits

@dataclass
class Today:
    cast: list            # Characters, the first one leads: her story and daily time decide for everyone
    away: bool            # her story sent her home, or she invited someone today: nobody comes out
    resting: bool         # today's time is used up: nobody comes out
    note: str | None      # for her greeting: why the others aren't here

    @property
    def together(self):
        """More than one of them comes out (a Scene)."""
        return len(self.cast) > 1 and not (self.away or self.resting)

def today(folder):
    plan = roster.today(folder)
    cast = [Character(f) for f in plan.members]
    lead = cast[0]
    save = load_save(lead.save_path)
    away = story.away(save) or plan.invited_today
    resting = not away and visits.resting(lead) and not story.ignores_time_limit(save, lead)
    day = Today(cast, away, resting, plan.note)
    if plan.why != "today.json":  # (that one says so itself)
        print(said(plan, day))
    if day.together:
        if plan.why != "today.json":  # (your test days don't count: set "together" in roster.json by hand instead)
            roster.shared_day(plan.members)
        for c in cast[1:]:
            c.daily_minutes = None  # they leave together, when her time is up
    return day

def said(plan, day):
    """The launch line: who comes today and why, like "today: ruby, pip (random)". (Folders, as in today.json.)"""
    line = f"today: {', '.join(plan.members)} ({plan.why})"
    if day.resting:
        return line + ", but her time today is used up: nobody comes out"
    if day.away and not plan.invited_today:
        return line + ", but her story has her away: nobody comes out"
    return line

def story_mood(character, present):
    """The mood her story has her in today, or None. present = folders of everyone on the desktop."""
    save = load_save(character.save_path)
    save.gates = character.gates
    for key, empty in (("points", 0), ("quests_done", [])):  # a save that's never been opened has neither
        save.setdefault(key, empty)
    story.catch_up(save, character)
    return story.mood_today(save, character, present)
