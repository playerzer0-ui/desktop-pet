"""Two characters on the desktop chatting with each other: a duet. The topics are the pair's own, in
character/duets/<one>-<other>.toml (folder names, either order), e.g. character/duets/pip-mira.toml.

Each character only ever sees her own conversation, so the other's line reaches her as a stage direction:

    Vesper  <- "(No message from the user. Vesper turns to Pip and starts a little chat with her about ...)"
    Vesper  -> "Your loaves are flatter than Republicia's mercy, Pip."
    Pip     <- "(No message from the user. Vesper says to Pip: "Your loaves are ...". Pip answers Vesper ...)"
    Pip     -> "*hides in her sleeves* They rise in spirit!"
    ...     (lines alternate, the last one wraps it up)

Both remember the chat (it's in both conversations), it earns no trust, and the diary skips it (stage directions
aren't the user's words). desktop/scene.py decides when one starts and plays the lines.

    pair = duets.load(["pip", "mira"])        # the pair's topics (None if there's no file for them)
    topic = pair.pick(stage)                  # a topic for this trust stage (the lower of the two), not a recent one
    duets.opener(speaker, listener, topic)    # stage direction for the first line
    duets.reply(speaker, listener, heard, last=False)   # stage direction for each line after it
"""
import os, random, tomllib
from config import HERE
from directions import direction

DUET_DIR = os.path.join(HERE, "character", "duets")

class Pair:
    def __init__(self, path):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        self.folders = set(os.path.basename(path)[:-5].split("-", 1))
        self.every = tuple(data.get("every", (4, 10)))  # minutes of quiet before they chat (random in this range)
        self.lines = tuple(data.get("lines", (3, 4)))   # lines in a chat (random in this range)
        self.topics = data["topics"]
        for i, t in enumerate(self.topics, 1):
            missing = [key for key in ("stage", "starts", "about") if key not in t]
            if missing:
                raise ValueError(f"{path}: topic {i} is missing: {', '.join(missing)}")
            if t["starts"] not in self.folders:
                raise ValueError(f"{path}: topic {i} starts = {t['starts']!r}, which isn't one of {sorted(self.folders)}")
            if not 1 <= t["stage"] <= 5:
                raise ValueError(f"{path}: topic {i} stage must be 1-5")
        if not (1 <= self.lines[0] <= self.lines[1]) or not (0 < self.every[0] <= self.every[1]):
            raise ValueError(f"{path}: lines and every are [low, high], above 0")
        self.recent = []  # topics used lately (not repeated until a few others have come up)

    def pick(self, stage, rng=random):
        """A topic ({stage, starts, about}) open at this trust stage and not used lately, or None."""
        open_ = [t for t in self.topics if t["stage"] <= stage]
        fresh = [t for t in open_ if t["about"] not in self.recent] or open_
        if not fresh:
            return None
        topic = rng.choice(fresh)
        self.recent = (self.recent + [topic["about"]])[-max(1, len(open_) // 2):]
        return topic

    def gap(self, rng=random):
        """Seconds of quiet before the next chat."""
        return rng.uniform(*self.every) * 60

    def length(self, rng=random):
        return rng.randint(*self.lines)

def load(folders):
    """The topics for these two characters (their folders), or None if they have no duet file."""
    a, b = folders
    for name in (f"{a}-{b}.toml", f"{b}-{a}.toml"):
        path = os.path.join(DUET_DIR, name)
        if os.path.exists(path):
            return Pair(path)
    return None

def opener(speaker, listener, topic):
    """The stage direction for the chat's first line (speaker and listener are Characters)."""
    them = listener.pronouns["them"]
    return direction(speaker.fill(f"{{name}} turns to {listener.name} and starts a little chat with {them} about "
                                  f"{topic['about']}. {{They}} talks to {listener.name}, not to the user (who can see "
                                  f"and hear them both, and is \"you\" or \"the user\": never guess their gender)."))

def reply(speaker, listener, heard, last=False):
    """The stage direction for a line answering what the listener just said (heard)."""
    text = speaker.fill(f'{listener.name} says to {{name}}: "{heard}" {{name}} answers {listener.name}, not the user.')
    if last:
        text += speaker.fill(" {They} wraps the little chat up.")
    return direction(text)
