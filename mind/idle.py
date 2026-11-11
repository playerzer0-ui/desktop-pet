"""When a character speaks on her own: her greeting, a nudge after you go quiet, and clock moments
(morning, lunch...) once a day each. Each becomes a stage direction she answers in character.
"""
import datetime, random, time
from mind.directions import direction

QUIET_MINUTES = [5, 10, 10, 15]  # silence before each nudge; after the last, every 15 minutes
CLOCK = [  # (hour, minute, what she speaks up about), for 30 minutes after the time
    (7, 0, "it's morning, so {they} wishes the user a good morning"),
    (12, 0, "it's lunchtime, so {they} asks if the user has eaten"),
    (18, 0, "it's evening, so {they} asks how the user's day went"),
    (23, 0, "it's late at night, so {they} gently tells the user to get some sleep"),
]
PARTS_OF_DAY = [(5, "morning"), (12, "afternoon"), (17, "evening"), (21, "night")]  # from this hour on

def part_of_day(now):
    return next((part for hour, part in reversed(PARTS_OF_DAY) if now.hour >= hour), "night")

class Idle:
    def __init__(self, character):
        self.character = character
        self.last = time.time()       # last time anyone spoke
        self.user_last = time.time()  # last time the user spoke
        self.nudges = 0               # since the user last talked
        self.fired = set()            # clock moments used, like ("2026-10-19", 7, 0)
        self.recent = []              # topics used lately

    def user_spoke(self):
        self.last = self.user_last = time.time()
        self.nudges = 0

    def pip_spoke(self):
        """She spoke for another reason (like a quest): wait before nudging again."""
        self.last = time.time()

    def opening(self, news=None):
        """Her greeting cue, for the time of day. Inside a clock moment, the greeting uses it up."""
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
        """A stage direction if she should speak up now, else None."""
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
        """The clock moment happening now, if not used yet today (and marks it used), else None."""
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
