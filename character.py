"""A character: everything that makes Pip Pip, loaded from her folder (character/pip/).
The code never names a character itself, so another one is just another folder.

    pip = Character("pip")
    pip.text("persona.md")        a prose file from her folder (persona.md, lore.md, events.md)
    pip.staged("lore.md", 2)      the same, with only the '# Stage N' blocks she's ready to share at trust stage 2
    pip.events                    her dated world events (events.md, parsed by events.py)
    pip.sprites                   the folder with her <mood>.png sprites
    pip.portal                    the portal she arrives through while her mind loads (character/portal.png, shared)
    pip.save_path                 her own save (saves/pip.json): trust, mood, memories... are per character
    pip.log_path                  her reply stats for tuning (pip.log)
    pip.fill("{name} says something on {their} own")  ->  "Pip says something on her own"

The rest comes from character.toml: name, pronouns, moods, stage_names, examples, idle_topics, quests.
(Pronouns fill {they} {them} {their}, and {They} etc. at the start of a sentence. The code's prompts are
written with singular verbs, "{They} greets", which suits she/he.)
"""
import os, re, tomllib
import events
from config import HERE

DEFAULT = "pip"  # who main.py opens when no character is named
PORTAL = os.path.join(HERE, "character", "portal.png")  # every character arrives through the same portal (for now)

class Character:
    def __init__(self, folder=DEFAULT):
        self.folder = folder
        self.dir = os.path.join(HERE, "character", folder)
        with open(os.path.join(self.dir, "character.toml"), "rb") as f:
            c = tomllib.load(f)
        self.name = c["name"]
        self.pronouns = dict(zip(("they", "them", "their"), c["pronouns"]))
        self.about = c["about"]
        self.moods = set(c["moods"])
        self.stage_names = {i + 1: name for i, name in enumerate(c["stage_names"])}
        self.examples = [(e["user"], e["reply"]) for e in c["examples"]]
        self.idle_topics = [(int(stage), topic) for stage, topics in c["idle_topics"].items() for topic in topics]
        self.idle_note = c["idle_note"]  # (required, even if "": a key misplaced under a [table] fails loudly)
        self.daily_minutes = c.get("daily_minutes")  # how long they can stay each day (visits.py); None = no limit
        if self.daily_minutes is not None and (not isinstance(self.daily_minutes, int) or self.daily_minutes <= 0):
            raise ValueError("daily_minutes must be a whole number of minutes above 0 (or left out for no limit)")
        needed = self.daily_minutes is not None  # (what they say when it runs low / runs out, by trust stage)
        self.time_warning = _by_stage(c, "time_warning", needed)
        self.time_up = _by_stage(c, "time_up", needed)
        self.quests = [(quest_id, int(stage), about)
                       for stage, asks in c["quests"].items() for quest_id, about in asks.items()]
        self.major_quests = _major_quests(c.get("major_quests", {}), self.moods)
        # stage -> {id, starts, done_when, memory, points}, or a story over several days: {id, memory, points, steps}
        self.friend = _friend(c.get("friend"))  # the friend they invite to the desktop ([friend], friends.py), or None
        self.first_visit = c.get("first_visit")  # what their very first greeting is about (a stage direction), or None
        self.sprites = os.path.join(self.dir, "sprites")
        self.portal = PORTAL
        self.save_path = os.path.join(HERE, "saves", folder + ".json")
        self.log_path = os.path.join(HERE, folder + ".log")
        self.events = events.parse(self.text("events.md"))
        if folder == DEFAULT:
            _move_old_save(self.save_path)

    @staticmethod
    def at_stage(lines, stage):
        """From {stage: line} (like time_warning), the line for this trust stage: the highest one at or below it."""
        return lines[max(s for s in lines if s <= stage)]

    @property
    def gates(self):
        """Stage -> the quest id (as saved in quests_done) that opens the next stage, for trust.py."""
        return {stage: "major-" + q["id"] for stage, q in self.major_quests.items()}

    def text(self, name):
        """A file from their folder, like persona.md."""
        with open(os.path.join(self.dir, name), encoding="utf-8") as f:
            return f.read()

    def staged(self, name, stage):
        """A file from their folder with only what they're ready to share at this trust stage (see for_stage)."""
        return for_stage(self.text(name), stage)

    def fill(self, text):
        """Put her name and pronouns into a prompt written with {name}, {they}, {them}, {their} (or {They}...)."""
        for key, word in self.pronouns.items():
            text = text.replace("{" + key + "}", word).replace("{" + key.capitalize() + "}", word.capitalize())
        return text.replace("{name}", self.name)

def for_stage(text, stage):
    """Character files are sorted by trust: '# Stage N' blocks, each holding '##'/'###' sections.
    Keep the blocks up to this trust stage (1-5) and merge sections with the same heading,
    so the model reads e.g. Republic once, with everything they're ready to share about it.
    Lines before the first '# Stage' block are always kept as they are."""
    preamble = []
    tree = {"lines": [], "children": {}}  # heading -> section, in the order headings first appear
    block = None  # stage of the block we're in (None = before the first block)
    path = []     # headings we're currently inside
    for line in text.splitlines():
        if not line.strip():
            continue
        stage_heading = re.match(r"# Stage ([1-5])\s*$", line)
        if stage_heading:
            block, path = int(stage_heading.group(1)), []
        elif block is None:
            preamble.append(line)
        elif block <= stage:
            heading = re.match(r"(#{2,}) (.*)", line)
            if heading:
                depth = len(heading.group(1)) - 2  # '##' = top level
                path = path[:depth] + [heading.group(2).strip()]
                continue
            section = tree
            for name in path:
                section = section["children"].setdefault(name, {"lines": [], "children": {}})
            section["lines"].append(line)

    parts = ["\n".join(preamble)] if preamble else []
    def write(section, level):
        for name, child in section["children"].items():
            parts.append("\n".join(["#" * level + " " + name] + child["lines"]))
            write(child, level + 1)
    write(tree, 2)
    return "\n\n".join(parts)

def _by_stage(toml, key, required):
    """A [key] table of lines by the trust stage they start at, like [time_warning]: {1: "...", 3: "..."}.
    required = it must exist, with a line for stage 1 (so every stage has one)."""
    table = {int(stage): line for stage, line in toml.get(key, {}).items()}
    if any(not 1 <= stage <= 5 for stage in table):
        raise ValueError(f"[{key}]: stages are 1-5")
    if required and 1 not in table:
        raise ValueError(f"[{key}] needs a line for stage 1 (they have a daily_minutes limit)")
    return table

def _major_quests(tables, moods):
    """[major_quests.N] from character.toml, checked: one per stage 1-4 at most, with every field filled in.
    Either one moment (starts, done_when) or a story told in steps over several days (steps: see story.py)."""
    found = {}
    for stage, q in tables.items():
        where = f"[major_quests.{stage}]"
        if not stage.isdigit() or not 1 <= int(stage) <= 4:
            raise ValueError(f"{where}: a major quest opens the next stage, so it belongs to stage 1-4")
        needed = ("id", "memory", "points", "steps") if "steps" in q else ("id", "starts", "done_when", "memory", "points")
        missing = [key for key in needed if key not in q]
        if missing:
            raise ValueError(f"{where} is missing: {', '.join(missing)}")
        if not isinstance(q.setdefault("needs_nice", True), bool):
            raise ValueError(f"{where} needs_nice must be true or false")
        for i, step in enumerate(q.get("steps", []), 1):
            _check_step(f"{where} step {i}", step, moods)
        if "steps" in q and not q["steps"]:
            raise ValueError(f"{where} has no steps")
        found[int(stage)] = q
    return found

def _check_step(where, step, moods):
    """One step of a story quest (story.py), with its defaults filled in."""
    if "opens" not in step:
        raise ValueError(f"{where} is missing: opens")
    step.setdefault("leaves", False)
    step.setdefault("away_days", 0)
    step.setdefault("no_time_limit", False)
    if step.setdefault("ends", "after_it") not in ("after_it", "goodbyes"):
        raise ValueError(f'{where}: ends must be "after_it" or "goodbyes"')
    if step["ends"] == "goodbyes":
        missing = [key for key in ("goodbyes", "begs", "leaves_line") if key not in step]
        if missing:
            raise ValueError(f"{where} ends with goodbyes, so it needs: {', '.join(missing)}")
        if not isinstance(step["goodbyes"], int) or step["goodbyes"] < 1:
            raise ValueError(f"{where}: goodbyes must be a whole number above 0")
    if "mood" in step and step["mood"] not in moods:
        raise ValueError(f"{where}: mood {step['mood']!r} isn't one of the character's moods")
    if not isinstance(step["away_days"], int) or step["away_days"] < 0:
        raise ValueError(f"{where}: away_days must be a whole number, 0 or more")

def _friend(table):
    """[friend] from character.toml, checked: who they invite (a folder in character/), at what trust (1-10),
    what they say about it on their way out, and what they remember afterwards."""
    if table is None:
        return None
    missing = [key for key in ("folder", "at_trust", "invite", "memory") if key not in table]
    if missing:
        raise ValueError(f"[friend] is missing: {', '.join(missing)}")
    if not isinstance(table["at_trust"], int) or not 1 <= table["at_trust"] <= 10:
        raise ValueError("[friend] at_trust must be a whole number from 1 to 10")
    if not os.path.isfile(os.path.join(HERE, "character", table["folder"], "character.toml")):
        raise ValueError(f"[friend] folder {table['folder']!r} isn't a character in character/")
    return table

def _move_old_save(path):
    """Before characters, Pip's save was save.json in the project folder: it becomes saves/pip.json."""
    old = os.path.join(HERE, "save.json")
    if os.path.exists(old) and not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.replace(old, path)
