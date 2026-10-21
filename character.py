"""A character: everything that makes Pip Pip, loaded from her folder (character/pip/).
The code never names a character itself, so another one is just another folder.

    pip = Character("pip")
    pip.text("persona.md")        a prose file from her folder (persona.md, lore.md, events.md)
    pip.staged("lore.md", 2)      the same, with only the '# Stage N' blocks she's ready to share at trust stage 2
    pip.events                    her dated world events (events.md, parsed by events.py)
    pip.sprites                   the folder with her <mood>.png sprites
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
        self.quests = [(quest_id, int(stage), about)
                       for stage, asks in c["quests"].items() for quest_id, about in asks.items()]
        self.sprites = os.path.join(self.dir, "sprites")
        self.save_path = os.path.join(HERE, "saves", folder + ".json")
        self.log_path = os.path.join(HERE, folder + ".log")
        self.events = events.parse(self.text("events.md"))
        if folder == DEFAULT:
            _move_old_save(self.save_path)

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

def _move_old_save(path):
    """Before characters, Pip's save was save.json in the project folder: it becomes saves/pip.json."""
    old = os.path.join(HERE, "save.json")
    if os.path.exists(old) and not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.replace(old, path)
