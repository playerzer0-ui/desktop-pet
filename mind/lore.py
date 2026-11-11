"""A character's lore in two layers, so her prompt stays small even at the top stage:

    ## Bloodcult
    words: bloodcult, lind, cult, brawl, resurrect
    in short: the faction of chaos and violence; its boss is Lind (a man: he/him)
    - details ...

Her prompt (which the server reads once and caches) gets every section's "in short" lines. The other lines of a
section that has "words:" are its details: they come in as a hidden note on a message only when something mentions
one of its words, and stay for her next few replies so follow-up questions still have them. A section without a
"words:" line stays whole in her prompt, as before (so lore.md files written without them work unchanged).

The note goes with that one request and isn't kept in her chat (like a quest note), so it never piles up in her
context, the cached prompt never changes (no slow re-read), and her diary never takes lore for something you said.

    lore = Lore(character, stage)
    lore.prompt                         her lore as her prompt has it (the short version)
    lore.note(message)                  the hidden note for one request, or None (session.py: your message, or the
                                        stage direction she's speaking to, never her own last reply)
"""
import re

WORDS = re.compile(r"^words:\s*(.*)$", re.I)
SHORT = re.compile(r"^in short:\s*(.*)$", re.I)
LINGER = 2  # a section that came up stays for this many more of her replies (for "and what is her power?")
MOST = 3    # sections in one note at most (the newest first): each one is a few hundred tokens

NOTE = ("(Not part of the message: more of what {name} knows about this, beyond the short version above. {They} "
        "uses only what fits the conversation, in {their} own words, and never recites it as a list:)\n")

def split(text):
    """Staged lore (Character.staged) -> (the text for her prompt, {heading: {"words": [...], "details": text}})."""
    groups, top = [], []  # top: lines before the first "## " section
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
        if not words:  # (no "words:": the whole section stays in her prompt, any "in short:" as a plain line)
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
    """Any of these words or phrases, whole (plurals and 's too), in any case: "lind" finds "Lind's", not "Linda"."""
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")(?:s|es|'s|’s)?\b", re.I)

class Lore:
    def __init__(self, character, stage, today=None):
        self.character = character
        self.prompt, self.sections = split(character.staged("lore.md", stage, today))
        self.replies = 0
        self.last = {}  # heading -> the reply it last came up on
        self.shown = []  # the sections in the last note (for her log)

    def found(self, *texts):
        """The sections these texts mention, in the file's order."""
        return [h for h, s in self.sections.items() if any(t and s["pattern"].search(t) for t in texts)]

    def note(self, *texts):
        """The hidden note for her next reply: the details of the sections a text mentions, then of ones that came
        up in her last LINGER replies (newest first), MOST at most. None if there are none.
        texts are tried in order, and only the first that mentions anything counts (a fallback text is used only
        when the first names nothing)."""
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
