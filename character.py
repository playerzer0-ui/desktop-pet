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
import datetime, os, re, tomllib
import events
from config import HERE, LOG_DIR, SAVES_DIR

DEFAULT = "pip"  # who main.py opens when no character is named
PORTAL = os.path.join(HERE, "character", "portal.png")  # every character arrives through the same portal (for now)

def cast():
    """Every character's names: the name they go by and their folder (Vesper's is her real name, Mira).
    Her diary never writes notes about any of them (memory.write_diary): the user is never one of them."""
    names = set()
    root = os.path.join(HERE, "character")
    for folder in sorted(os.listdir(root)):
        toml = os.path.join(root, folder, "character.toml")
        if os.path.isfile(toml):
            with open(toml, "rb") as f:
                names |= {tomllib.load(f)["name"], folder.capitalize()}
    return names

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
        self.story_moods = set(c.get("story_moods", []))  # moods only a story step puts her in (a sprite each, but
                                                           # never on the list the model picks from), like injured
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
        # her public self, when her friend is on the desktop too: her prompt, idle talk and events go no higher than
        # this stage then, and private memories are left out (Session.shown_stage), so her secrets can't slip out
        self.with_friend_stage = c.get("with_friend_stage")
        if self.with_friend_stage is not None and self.with_friend_stage not in (1, 2, 3, 4, 5):
            raise ValueError("with_friend_stage must be a trust stage, 1-5 (or left out: no mask)")
        self.quests = [(quest_id, int(stage), about)
                       for stage, asks in c["quests"].items() for quest_id, about in asks.items()]
        self.major_quests = _major_quests(c.get("major_quests", {}), self.moods | self.story_moods, folder)
        # stage -> {id, starts, done_when, memory, points}, or a story over several days: {id, memory, points, steps}
        self.first_visit = c.get("first_visit")  # what their very first greeting is about (a stage direction), or None
        self.sprites = os.path.join(self.dir, "sprites")
        self.portal = PORTAL
        self.save_path = os.path.join(SAVES_DIR, folder + ".json")  # (the player's own folder: see config.py)
        self.log_path = os.path.join(LOG_DIR, folder + ".log")
        self.events = events.parse(self.text("events.md"))

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

    def staged(self, name, stage, today=None):
        """A file from their folder with only what they're ready to share at this trust stage (see for_stage), and
        only the dated lines that are true today (see on_date), without lines a later stage replaced (before_stage)."""
        return for_stage(before_stage(on_date(self.text(name), today), stage), stage)

    def fill(self, text):
        """Put her name and pronouns into a prompt written with {name}, {they}, {them}, {their} (or {They}...)."""
        for key, word in self.pronouns.items():
            text = text.replace("{" + key + "}", word).replace("{" + key.capitalize() + "}", word.capitalize())
        return text.replace("{name}", self.name)

RETIRES = re.compile(r"\[until stage ([1-5])\]\s*")

def before_stage(text, stage):
    """Lines that a later stage replaces, so the top stage doesn't carry both (Vesper's "won't say who pays her",
    once stage 4 says it's Lind):
        - [until stage 4] Someone dangerous pays her to watch the chapel, and she won't say who
    kept below that stage, with the mark taken out, and left out from it on."""
    kept = []
    for line in text.splitlines():
        mark = RETIRES.search(line)
        if mark and stage >= int(mark.group(1)):
            continue
        kept.append(RETIRES.sub("", line))
    return "\n".join(kept)

DATED = re.compile(r"\[(until|from) (\d{4}-\d\d-\d\d)\]\s*")

def on_date(text, today=None):
    """Lines that are only true for a while, for things that happen on a set day (the library's last day):
        - [until 2026-11-20] the library is to be torn down on November 20, 2026
        - [from 2026-11-20] the library was torn down on November 20, 2026
    "until" lines are kept before that day, "from" lines from that day on, with the mark taken out. The model
    doesn't work it out from the date itself (told it was later, she still said the library was standing).
    The prompt changes on that day, so it's read once more then (pet.warm_up caches by its text)."""
    today = (today or datetime.date.today()).isoformat()
    kept = []
    for line in text.splitlines():
        mark = DATED.search(line)
        if mark:
            when, day = mark.groups()
            if (today < day) != (when == "until"):
                continue
            line = DATED.sub("", line, count=1)
        kept.append(line)
    return "\n".join(kept)

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

def _major_quests(tables, moods, folder=None):
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
        if not isinstance(q.setdefault("private", False), bool):
            raise ValueError(f"{where} private must be true or false (only raised, and remembered, when it's just you)")
        if not isinstance(q.setdefault("note", ""), str):
            raise ValueError(f"{where} note must be text (a hidden note on each message she judges for it)")
        if not isinstance(q.setdefault("answer_words", ""), str):
            raise ValueError(f"{where} answer_words must be text (a pattern a real answer has to contain)")
        try:
            re.compile(q["answer_words"])
        except re.error as e:
            raise ValueError(f"{where} answer_words isn't a valid pattern: {e}")
        for i, step in enumerate(q.get("steps", []), 1):
            _check_step(f"{where} step {i}", step, moods, folder)
        if "steps" in q and not q["steps"]:
            raise ValueError(f"{where} has no steps")
        found[int(stage)] = q
    return found

def is_character(folder):
    """True if character/<folder>/ is a character (has a character.toml)."""
    return isinstance(folder, str) and os.path.isfile(os.path.join(HERE, "character", folder, "character.toml"))

def folder_of(name):
    """The folder of the character who goes by this name ("Vesper" -> "mira"), or None."""
    root = os.path.join(HERE, "character")
    for folder in sorted(os.listdir(root)):
        if is_character(folder):
            with open(os.path.join(root, folder, "character.toml"), "rb") as f:
                if tomllib.load(f)["name"] == name:
                    return folder
    return None

def _check_step(where, step, moods, folder=None):
    """One step of a story quest (story.py), with its defaults filled in. folder = whose quest it is."""
    if "opens" not in step:
        raise ValueError(f"{where} is missing: opens")
    step.setdefault("leaves", False)
    step.setdefault("away_days", 0)
    step.setdefault("no_time_limit", False)
    if step.setdefault("ends", "after_it") not in ("after_it", "goodbyes", "duet", "answer", "day"):
        raise ValueError(f'{where}: ends must be "after_it", "goodbyes", "duet", "answer" or "day"')
    if not isinstance(step.setdefault("completes", False), bool):
        raise ValueError(f"{where}: completes must be true or false (the quest is done when this step ends)")
    _check_who(where, step, folder)
    if step["ends"] == "answer" and "done_when" not in step:
        raise ValueError(f"{where} ends with an answer, so it needs: done_when")
    step.setdefault("needs_nice", False)
    if not isinstance(step.setdefault("lingers", 0), int) or step["lingers"] < 0:
        raise ValueError(f"{where}: lingers must be a whole number of days, 0 or more")
    if step["lingers"] and "mood" not in step:
        raise ValueError(f"{where}: lingers keeps the step's mood for days after it, so it needs a mood")
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

def _check_who(where, step, folder=None):
    """Who has to be on the desktop for a story step (story.who_comes), one of:
        needs = ["pip", "mira"]   exactly these come (folders, the first one leads), her own folder among them
        told_by = "pip"           she stays away, and this one comes on her own and tells the step in her greeting
        day = "together" / "alone" / "away"   the same, said about the one she comes with (roster.py's partner)
    Or none of them: whoever comes that day. A step that ends with a duet chats with someone there."""
    said = [key for key in ("needs", "told_by", "day") if key in step]
    if len(said) > 1:
        raise ValueError(f"{where}: use one of needs, told_by and day, not {' and '.join(said)}")
    if "day" in step and step["day"] not in ("together", "alone", "away"):
        raise ValueError(f'{where}: day must be "together", "alone" or "away"')
    needs = step.get("needs")
    if needs is not None:
        if not isinstance(needs, list) or not needs or len(set(needs)) != len(needs):
            raise ValueError(f"{where}: needs must be a list of different folders")
        for f in needs:
            if not is_character(f):
                raise ValueError(f"{where}: needs {f!r}, which isn't a character in character/")
        if folder and folder not in needs:
            raise ValueError(f"{where}: needs must include {folder!r} herself (a step she's away for: told_by)")
    if "told_by" in step:
        if not is_character(step["told_by"]) or step["told_by"] == folder:
            raise ValueError(f"{where}: told_by must be another character's folder in character/")
    told = "told_by" in step or step.get("day") == "away"
    if told and step["ends"] != "after_it":
        raise ValueError(f"{where}: a step told for her while she's away (told_by, or day = \"away\") is told "
                         'in a greeting, so it ends "after_it"')
    if step["ends"] == "duet":
        duet = step.get("duet", {})
        if not {"starts", "about"} <= set(duet):
            raise ValueError(f'{where} ends with a duet, so it needs: duet = {{ starts = "<folder>", about = "..." }}')
        if step.get("day") != "together" and len(needs or []) < 2:
            raise ValueError(f'{where} ends with a duet, so it needs two there: needs = ["...", "..."] '
                             '(or day = "together")')
        for key in ("starts", "with"):
            if key in duet and needs and duet[key] not in needs:
                raise ValueError(f"{where}: duet {key} = {duet[key]!r} isn't one of needs")
        if duet.get("with") == duet["starts"]:
            raise ValueError(f"{where}: a duet is with someone else (with = {duet['with']!r} starts it too)")
