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
TOPICS = [  # (stage it unlocks at, what she speaks up about) for quiet nudges.
    # Picked at random from her stage and below, without repeating the last few.
    # Keep them concrete: vague topics ("the weather back home") make her fall back on rain and Everlily every time.
    # Each topic should only lean on lore/persona she has at that stage (see character/pip/).
    # stage 1: the desktop, the user, small likes
    (1, "noticing the user is busy, and quietly keeping them company"),
    (1, "a gentle question about what the user is up to"),
    (1, "something cozy she noticed on the desktop, like the glow of the screen or a neat little icon"),
    (1, "a warm drink she wishes she could share with the user"),
    (1, "an odd coin from her little coin collection"),
    (1, "the bread she baked this morning, and whether it rose properly"),
    (1, "the potted herb she keeps forgetting to water"),
    (1, "a strange gadget from her world, where magic and technology live side by side"),
    (1, "how sleepy or awake she feels today"),
    # stage 2: daily life at the chapel and the exchange
    (2, "one of her elderly Freeport visitors, and a story they told her"),
    (2, "a funny or chaotic customer at her currency exchange"),
    (2, "the stuffy bank clerks next door to the chapel"),
    (2, "prices jumping around again because nobody knows what Republicia will do"),
    (2, "a note she copied at the ancient library before it gets demolished"),
    (2, "a small favour she'd like to ask the user"),
    # stage 3: the gods and the fountains
    (3, "something she read at the library about Feras, Sally or Silas"),
    (3, "the fountains of knowledge being locked away from ordinary people"),
    (3, "the odd things people used to pray to the gods for"),
    (3, "a short prayer she says for the user"),
    # stage 4: her fears and her tiredness
    (4, "quiet news from another faction, told gently"),
    (4, "how tired she is back home, and how nice it is to rest here"),
    (4, "how long she can stay this visit before her body back home needs her"),
    # stage 5: hope
    (5, "the last warm lamp, and how warm it keeps the chapel"),
    (5, "an idea for the little chapel she might build on the desktop someday"),
    (5, "something hopeful she noticed lately"),
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

    def pip_spoke(self):
        """Pip just said something for another reason (like a quest): wait before nudging again."""
        self.last = time.time()

    def opening(self, news=None):
        """The stage direction for when Pip opens. news = something from her world to bring up (see events.py)."""
        text = "The user just opened the desktop and Pip has woken up. She greets them first."
        return direction(f"{text} {news}" if news else text)

    def due(self, stage=1):
        """A stage direction if Pip should speak up now, else None. stage = her trust stage (1-5)."""
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
            topic = random.choice([t for s, t in TOPICS if s <= stage and t not in self.recent])
            self.recent = (self.recent + [topic])[-5:]
            return self._spoke(direction(
                f"The user has been quiet for {quiet:.0f} minutes. Pip says something on her own, about {topic}. "
                f"Stick to that topic: don't bring up rain or Everlily unless it's about them."))
        return None

    def _spoke(self, text):
        self.last = time.time()
        return text

def direction(text):
    # in parentheses, so it reads as a stage direction, not as something the user said
    return f"(No message from the user. {text} Keep it to 1-2 short sentences and don't mention being told to speak.)"
