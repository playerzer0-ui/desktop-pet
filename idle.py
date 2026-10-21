"""When a character speaks on their own, without being asked (the examples say Pip and "she").

    - when she opens: she greets you first
    - when you go quiet: after 5 minutes she says something small, then waits longer each time
    - at certain clock times (morning, lunch, ...): once a day each, if she's open then

Each one becomes a hidden "stage direction" message that the character answers in character.
"""
import datetime, random, time

QUIET_MINUTES = [5, 10, 10, 15]  # silence before each nudge; after the last, every 15 minutes
CLOCK = [  # (hour, minute, what she speaks up about) - checked for 30 minutes after the time
    (7, 0, "it's morning, so {they} wishes the user a good morning"),
    (12, 0, "it's lunchtime, so {they} asks if the user has eaten"),
    (18, 0, "it's evening, so {they} asks how the user's day went"),
    (23, 0, "it's late at night, so {they} gently tells the user to get some sleep"),
]
# (the quiet-nudge topics are the character's own: idle_topics in their character.toml)

class Idle:
    def __init__(self, character):
        self.character = character  # (character.py) whose topics, name and pronouns
        self.last = time.time()  # last time anyone spoke
        self.user_last = time.time()  # last time the user spoke
        self.nudges = 0          # nudges since the user last talked
        self.fired = set()       # clock moments already used, like ("2026-10-19", 7, 0)
        self.recent = []         # topics used lately

    def user_spoke(self):
        self.last = self.user_last = time.time()
        self.nudges = 0

    def pip_spoke(self):
        """The character just said something for another reason (like a quest): wait before nudging again."""
        self.last = time.time()

    def opening(self, news=None):
        """The stage direction for when the character opens. news = something from their world to bring up
        (see events.py)."""
        text = self.character.fill("The user just opened the desktop and {name} has woken up. {They} greets them first.")
        return direction(f"{text} {news}" if news else text)

    def due(self, stage=1):
        """A stage direction if the character should speak up now, else None. stage = their trust stage (1-5)."""
        now = datetime.datetime.now()
        for hour, minute, about in CLOCK:
            moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            key = (now.date().isoformat(), hour, minute)
            if moment <= now < moment + datetime.timedelta(minutes=30) and key not in self.fired:
                self.fired.add(key)
                return self._spoke(direction(self.character.fill(f"{{name}} says something on {{their}} own: {about}.")))

        wait = QUIET_MINUTES[min(self.nudges, len(QUIET_MINUTES) - 1)]
        if time.time() - self.last >= wait * 60:
            quiet = (time.time() - self.user_last) / 60
            self.nudges += 1
            topic = random.choice([t for s, t in self.character.idle_topics if s <= stage and t not in self.recent])
            self.recent = (self.recent + [topic])[-5:]
            return self._spoke(direction(
                f"The user has been quiet for {quiet:.0f} minutes. "
                + self.character.fill("{name} says something on {their} own, about ") + f"{topic}. "
                + self.character.idle_note))
        return None

    def _spoke(self, text):
        self.last = time.time()
        return text

def direction(text):
    # in parentheses, so it reads as a stage direction, not as something the user said
    return f"(No message from the user. {text} Keep it to 1-2 short sentences and don't mention being told to speak.)"
