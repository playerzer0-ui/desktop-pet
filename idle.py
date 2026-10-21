"""When a character speaks on their own, without being asked (the examples say Pip and "she").

    - when she opens: she greets you first
    - when you go quiet: after 5 minutes she says something small, then waits longer each time
    - at certain clock times (morning, lunch, ...): once a day each, if she's open then

Each one becomes a hidden "stage direction" message that the character answers in character.
"""
import datetime, random, time
from directions import direction

QUIET_MINUTES = [5, 10, 10, 15]  # silence before each nudge; after the last, every 15 minutes
CLOCK = [  # (hour, minute, what she speaks up about) - checked for 30 minutes after the time
    (7, 0, "it's morning, so {they} wishes the user a good morning"),
    (12, 0, "it's lunchtime, so {they} asks if the user has eaten"),
    (18, 0, "it's evening, so {they} asks how the user's day went"),
    (23, 0, "it's late at night, so {they} gently tells the user to get some sleep"),
]
PARTS_OF_DAY = [(5, "morning"), (12, "afternoon"), (17, "evening"), (21, "night")]  # (from this hour on)
# (the quiet-nudge topics are the character's own: idle_topics in their character.toml)

def part_of_day(now):
    """"morning", "afternoon", "evening" or "night" (21:00 until 5:00) for a datetime."""
    return next((part for hour, part in reversed(PARTS_OF_DAY) if now.hour >= hour), "night")

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
        (see events.py). She's told the time of day, so she doesn't say "good morning" in the afternoon.
        Opened inside a clock moment (like 7:10), the greeting covers it instead ("it's morning, so she wishes
        the user a good morning"), and that moment is used up: it won't come again as a nudge."""
        text = self.character.fill("The user just opened the desktop and {name} has woken up. {They} greets them first.")
        about = self._clock_moment()
        if about:
            text += " " + self.character.fill(about[0].upper() + about[1:]) + "."
        else:
            now = datetime.datetime.now()
            text += self.character.fill(f" It's {part_of_day(now)} for the user right now ({now:%H:%M}), "
                                        "so {they} greets them for that time of day.")
        return direction(f"{text} {news}" if news else text)

    def due(self, stage=1):
        """A stage direction if the character should speak up now, else None. stage = their trust stage (1-5)."""
        about = self._clock_moment()
        if about:
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

    def _clock_moment(self):
        """What she speaks up about for the clock moment happening now (see CLOCK), if she hasn't yet today, else None.
        Marks it used: each moment comes once a day."""
        now = datetime.datetime.now()
        for hour, minute, about in CLOCK:
            moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            key = (now.date().isoformat(), hour, minute)
            if moment <= now < moment + datetime.timedelta(minutes=30) and key not in self.fired:
                self.fired.add(key)
                return about
        return None

    def _spoke(self, text):
        self.last = time.time()
        return text
