"""At launch, before any model starts: who comes out today, whether they come out at all, and in what mood."""
from dataclasses import dataclass, field
from engine.character import Character
from engine.save import load_save
from progress import roster, story, visits

@dataclass
class Today:
    cast: list            # Characters who come out, the first one leads (her story decides for everyone)
    away: bool            # her story sent her home, or she invited someone today: nobody comes out
    resting: bool         # everyone's time today is used up: nobody comes out
    note: str | None      # for her greeting: why the others aren't here
    home: list = field(default_factory=list)  # folders in today's lineup whose own time is used up: they stay home

    @property
    def together(self):
        """More than one of them comes out (a Scene)."""
        return len(self.cast) > 1 and not (self.away or self.resting)

def _resting(character):
    """Her own daily time is used up (and her story doesn't ignore it)."""
    return visits.resting(character) and not story.ignores_time_limit(load_save(character.save_path), character)

def today(folder):
    """Who comes out today. Each one has her own daily time (daily_minutes): one whose time is used up stays home
    while the others come, and in a Scene each leaves on her own when hers runs out."""
    plan = roster.today(folder)
    cast = [Character(f) for f in plan.members]
    lead = cast[0]
    away = story.away(load_save(lead.save_path)) or plan.invited_today
    home = [] if away else [c.folder for c in cast if not c.npc and _resting(c)]
    out = [c for c in cast if c.folder not in home]
    if not any(not c.npc for c in out):  # (an NPC only comes along with someone)
        out = []
    resting = not away and not out
    day = Today(out or [lead], away, resting, plan.note if not home else None, home)
    if plan.why != "today.json":  # (that one says so itself)
        print(said(plan, day))
    if day.together and plan.why != "today.json":  # (your test days don't count: set "together" in roster.json)
        roster.shared_day([c.folder for c in day.cast])
    return day

def said(plan, day):
    """The launch line: who comes today and why, like "today: ruby, pip (random)". (Folders, as in today.json.)"""
    line = f"today: {', '.join(plan.members)} ({plan.why})"
    if day.resting:
        return line + ", but " + ("her" if len(plan.members) == 1 else "their") + " time today is used up: nobody comes out"
    if day.away and not plan.invited_today:
        return line + ", but her story has her away: nobody comes out"
    if day.home:
        return line + f", but {', '.join(day.home)}'s time today is used up: {', '.join(c.folder for c in day.cast)} only"
    return line

def story_mood(character, present):
    """The mood her story has her in today, or None. present = folders of everyone on the desktop."""
    save = load_save(character.save_path)
    save.gates = character.gates
    for key, empty in (("points", 0), ("quests_done", [])):  # a save that's never been opened has neither
        save.setdefault(key, empty)
    story.catch_up(save, character)
    return story.mood_today(save, character, present)
