"""A character, loaded from her folder (character/pip/). The code never names a character, so another one is
just another folder.

    pip = Character("pip")
    pip.staged("lore.md", 2)      a file from her folder, with only what she shares at trust stage 2
    pip.fill("{name} says something on {their} own")  ->  "Pip says something on her own"
"""
import datetime, os, re, tomllib
from mind import events
from engine.config import HERE, LOG_DIR, SAVES_DIR

DEFAULT = "pip"  # who opens when no character is named
PORTAL = os.path.join(HERE, "character", "portal.png")  # shared by everyone

def cast():
    """Every character's names: the name they go by and their folder (Vesper / Mira)."""
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
        self.story_moods = set(c.get("story_moods", []))  # only a story step sets these, like injured
        self.stage_names = {i + 1: name for i, name in enumerate(c["stage_names"])}
        self.examples = [(e["user"], e["reply"]) for e in c["examples"]]
        self.idle_topics = [(int(stage), topic) for stage, topics in c["idle_topics"].items() for topic in topics]
        self.idle_note = c["idle_note"]  # required, so a key misplaced under a [table] fails loudly
        self.daily_minutes = c.get("daily_minutes")  # None = no limit
        if self.daily_minutes is not None and (not isinstance(self.daily_minutes, int) or self.daily_minutes <= 0):
            raise ValueError("daily_minutes must be a whole number of minutes above 0 (or left out for no limit)")
        needed = self.daily_minutes is not None
        self.time_warning = _by_stage(c, "time_warning", needed)
        self.time_up = _by_stage(c, "time_up", needed)
        # the stage she shows while her friend is on the desktop, so her secrets can't slip out
        self.with_friend_stage = c.get("with_friend_stage")
        if self.with_friend_stage is not None and self.with_friend_stage not in (1, 2, 3, 4, 5):
            raise ValueError("with_friend_stage must be a trust stage, 1-5 (or left out: no mask)")
        self.quests = [(quest_id, int(stage), about)
                       for stage, asks in c["quests"].items() for quest_id, about in asks.items()]
        self.major_quests = _major_quests(c.get("major_quests", {}), self.moods | self.story_moods, folder)
        self.first_visit = c.get("first_visit")  # what her very first greeting is about
        self.sprites = os.path.join(self.dir, "sprites")
        self.portal = PORTAL
        self.save_path = os.path.join(SAVES_DIR, folder + ".json")
        self.log_path = os.path.join(LOG_DIR, folder + ".log")
        self.events = events.parse(self.text("events.md"))

    @staticmethod
    def at_stage(lines, stage):
        """From {stage: line}, the line for this stage: the highest at or below it."""
        return lines[max(s for s in lines if s <= stage)]

    @property
    def gates(self):
        """Stage -> the quest id that opens the next stage."""
        return {stage: "major-" + q["id"] for stage, q in self.major_quests.items()}

    def text(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as f:
            return f.read()

    def staged(self, name, stage, today=None):
        """A file with only what she shares at this stage, and only the dated lines true today."""
        return for_stage(before_stage(on_date(self.text(name), today), stage), stage)

    def fill(self, text):
        """Fill {name}, {they}, {them}, {their} (and {They}...) in a prompt."""
        for key, word in self.pronouns.items():
            text = text.replace("{" + key + "}", word).replace("{" + key.capitalize() + "}", word.capitalize())
        return text.replace("{name}", self.name)

RETIRES = re.compile(r"\[until stage ([1-5])\]\s*")

def before_stage(text, stage):
    """Drop lines a later stage replaces, like:  - [until stage 4] Someone pays her, and she won't say who"""
    kept = []
    for line in text.splitlines():
        mark = RETIRES.search(line)
        if mark and stage >= int(mark.group(1)):
            continue
        kept.append(RETIRES.sub("", line))
    return "\n".join(kept)

DATED = re.compile(r"\[(until|from) (\d{4}-\d\d-\d\d)\]\s*")

def on_date(text, today=None):
    """Keep only the dated lines true today, like:  - [until 2026-11-20] the library is still standing
    (the model doesn't work it out from the date itself)."""
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
    """Keep the '# Stage N' blocks up to this stage, merging sections with the same heading so the model reads
    each topic once. Lines before the first block are always kept."""
    preamble = []
    tree = {"lines": [], "children": {}}
    block = None  # stage of the block we're in
    path = []     # headings we're inside
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
    """A [key] table of lines by the stage they start at, like [time_warning]: {1: "...", 3: "..."}."""
    table = {int(stage): line for stage, line in toml.get(key, {}).items()}
    if any(not 1 <= stage <= 5 for stage in table):
        raise ValueError(f"[{key}]: stages are 1-5")
    if required and 1 not in table:
        raise ValueError(f"[{key}] needs a line for stage 1 (they have a daily_minutes limit)")
    return table

def _major_quests(tables, moods, folder=None):
    """[major_quests.N], checked: one moment (starts, done_when) or a story in steps."""
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
    """One story step, checked, with its defaults filled in."""
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
    if not isinstance(step.setdefault("answer_words", ""), str):
        raise ValueError(f"{where}: answer_words must be text (a pattern a real answer has to contain)")
    try:
        re.compile(step["answer_words"])
    except re.error as e:
        raise ValueError(f"{where}: answer_words isn't a valid pattern: {e}")
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
    """Who has to be on the desktop for a step: needs, told_by or day (one of them, or none)."""
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
