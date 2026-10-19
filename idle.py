"""When Pip speaks on her own, without being asked.

    - when she opens: she greets you first
    - when you go quiet: after 5 minutes she says something small, then waits longer each time
    - at certain clock times (morning, lunch, ...): once a day each, if she's open then

Each one becomes a hidden "stage direction" message that Pip answers in character.
"""
import datetime, random, time

QUIET_MINUTES = [5, 15, 30, 60]  # silence before each nudge; after the last, every 60 minutes
CLOCK = [  # (hour, minute, what she speaks up about) - checked for 30 minutes after the time
    (7, 0, "it's morning, so she wishes the user a good morning"),
    (12, 0, "it's lunchtime, so she asks if the user has eaten"),
    (18, 0, "it's evening, so she asks how the user's day went"),
    (23, 0, "it's late at night, so she gently tells the user to get some sleep"),
]
TOPICS = [  # for quiet nudges, picked at random without repeating the last few
    "something small that happened at the chapel",
    "how warm and cozy it is on the desktop",
    "a gentle question about what the user is up to",
    "something small she's looking forward to back home",
    "humming a little prayer to Everlily",
    "small everyday news from her world",
    "noticing the user is busy, and quietly keeping them company",
    "the weather back home",
]

class Idle:
    def __init__(self):
        self.last = time.time()  # last time anyone spoke
        self.user_last = time.time()  # last time the user spoke
        self.nudges = 0          # nudges since the user last talked
        self.fired = set()       # clock moments already used, like ("2026-10-19", 7, 0)
        self.recent = []         # topics used lately

    def user_spoke(self):
        self.last = self.user_last = time.time()
        self.nudges = 0

    def opening(self):
        """The stage direction for when Pip opens."""
        return direction("The user just opened the desktop and Pip has woken up. She greets them first.")

    def due(self):
        """A stage direction if Pip should speak up now, else None."""
        now = datetime.datetime.now()
        for hour, minute, about in CLOCK:
            moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            key = (now.date().isoformat(), hour, minute)
            if moment <= now < moment + datetime.timedelta(minutes=30) and key not in self.fired:
                self.fired.add(key)
                return self._spoke(direction(f"Pip says something on her own: {about}."))

        wait = QUIET_MINUTES[min(self.nudges, len(QUIET_MINUTES) - 1)]
        if time.time() - self.last >= wait * 60:
            quiet = (time.time() - self.user_last) / 60
            self.nudges += 1
            topic = random.choice([t for t in TOPICS if t not in self.recent])
            self.recent = (self.recent + [topic])[-3:]
            return self._spoke(direction(
                f"The user has been quiet for {quiet:.0f} minutes. Pip says something on her own, about {topic}."))
        return None

    def _spoke(self, text):
        self.last = time.time()
        return text

def direction(text):
    # in parentheses, so it reads as a stage direction, not as something the user said
    return f"(No message from the user. {text} Keep it to 1-2 short sentences and don't mention being told to speak.)"
