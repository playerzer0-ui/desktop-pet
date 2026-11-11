"""Two characters on the desktop chatting with each other. Topics are in character/duets/<one>-<other>.toml.
Each one only sees her own conversation, so the other's line reaches her as a stage direction.
desktop/scene.py decides when a chat starts and plays the lines.
"""
import os, random, tomllib
from engine.config import HERE
from mind.directions import direction

DUET_DIR = os.path.join(HERE, "character", "duets")

class Pair:
    def __init__(self, path):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        self.folders = set(os.path.basename(path)[:-5].split("-", 1))
        self.every = tuple(data.get("every", (4, 10)))  # minutes of quiet before they chat
        self.lines = tuple(data.get("lines", (3, 4)))   # lines in a chat
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
        self.recent = []

    def pick(self, stage, rng=random):
        """A topic open at this stage and not used lately, or None."""
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
    """The pair's topics, or None if they have no duet file."""
    a, b = folders
    for name in (f"{a}-{b}.toml", f"{b}-{a}.toml"):
        path = os.path.join(DUET_DIR, name)
        if os.path.exists(path):
            return Pair(path)
    return None

def opener(speaker, listener, topic):
    them = listener.pronouns["them"]
    return direction(speaker.fill(f"{{name}} turns to {listener.name} and starts a little chat with {them} about "
                                  f"{topic['about']}. {{They}} talks to {listener.name}, not to the user (who can see "
                                  f"and hear them both, and is \"you\" or \"the user\": never guess their gender). "
                                  + TOGETHER.format(listener=listener.name)))

TOGETHER = ("{{They}} speaks straight to {listener}, not about {listener}. They are both standing on the user's desktop, "
            "far from home: nothing from back home (an oven, a lamp, a plant) is here to touch.")

def reply(speaker, listener, heard, last=False):
    """The stage direction for answering what the listener just said."""
    text = speaker.fill(f'{listener.name} says to {{name}}: "{heard}" {{name}} answers {listener.name}, not the user, '
                        f"in {{their}} own new words, never repeating what {listener.name} just said. "
                        + TOGETHER.format(listener=listener.name))
    if last:
        text += speaker.fill(" {They} wraps the little chat up.")
    return direction(text)
