"""A character's lore in two layers, so her prompt stays small:

    ## Bloodcult
    words: bloodcult, lind, cult, brawl, resurrect
    in short: the faction of chaos and violence; its boss is Lind (a man: he/him)
    - details ...

Her prompt gets the "in short" lines. The details come in as a hidden note on a message that mentions one of the
words, and stay for her next few replies. A section without "words:" stays whole in her prompt.
"""
import re

WORDS = re.compile(r"^words:\s*(.*)$", re.I)
SHORT = re.compile(r"^in short:\s*(.*)$", re.I)
LINGER = 2  # replies a section stays after it came up (for follow-up questions)
MOST = 3    # sections in one note at most

NOTE = ("(Not part of the message: more of what {name} knows about this, beyond the short version above. {They} "
        "uses only what fits the conversation, in {their} own words, and never recites it as a list:)\n")

def split(text):
    """Staged lore -> (the text for her prompt, {heading: {"words", "details", "pattern"}})."""
    groups, top = [], []  # top: lines before the first section
    for line in text.splitlines():
        if re.match(r"## ", line):
            groups.append((line[3:].strip(), []))
        elif groups:
            groups[-1][1].append(line)
        else:
            top.append(line)
    out, sections = list(top), {}
    for heading, lines in groups:
        words = [w.strip().lower() for line in lines if WORDS.match(line.strip())
                 for w in WORDS.match(line.strip()).group(1).split(",") if w.strip()]
        if not words:  # the whole section stays in her prompt
            out += ["## " + heading] + [SHORT.sub(r"- \1", line.strip()) if SHORT.match(line.strip()) else line
                                        for line in lines]
            continue
        shorts = [SHORT.match(line.strip()).group(1) for line in lines if SHORT.match(line.strip())]
        details = [line for line in lines if not WORDS.match(line.strip()) and not SHORT.match(line.strip())]
        out += ["## " + heading] + ["- " + s for s in shorts]
        if details:
            sections[heading] = {"words": words, "details": "\n".join(details), "pattern": _pattern(words)}
    return "\n".join(out), sections

def _pattern(words):
    """Whole words, plurals and 's too: "lind" finds "Lind's", not "Linda"."""
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")(?:s|es|'s|’s)?\b", re.I)

class Lore:
    def __init__(self, character, stage, today=None):
        self.character = character
        self.prompt, self.sections = split(character.staged("lore.md", stage, today))
        self.replies = 0
        self.last = {}   # heading -> the reply it last came up on
        self.shown = []  # sections in the last note (for her log)

    def found(self, *texts):
        return [h for h, s in self.sections.items() if any(t and s["pattern"].search(t) for t in texts)]

    def note(self, *texts):
        """The hidden note for her next reply, or None: sections the first matching text mentions, then recent ones."""
        self.replies += 1
        new = next((found for found in map(self.found, texts) if found), [])
        for heading in new:
            self.last[heading] = self.replies
        self.last = {h: n for h, n in self.last.items() if self.replies - n <= LINGER}
        older = sorted((h for h in self.last if h not in new), key=lambda h: -self.last[h])
        self.shown = (new + older)[:MOST]
        if not self.shown:
            return None
        return self.character.fill(NOTE) + "\n".join(f"## {h}\n{self.sections[h]['details']}" for h in self.shown)
