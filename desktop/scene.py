"""Two characters on the desktop at once: Pip and the friend she brought over (friends.py), from the day after the
friend's first visit. Each one is a whole App (desktop/app.py) with her own body, bubble, menu, mind and save, on
her own slot of the model server (llm.py). The scene only makes them get along:

    taking turns   one talks at a time: nobody speaks up (greeting, idle talk, quest, news) while the other is
                   talking or you're typing to her, and you can't open a chat with one while the other is talking
    arriving       side by side, each out of her own portal. Pip greets first (the first day, she introduces her
                   friend: friends.introduce), and once she's done, her friend greets you too, hearing what she said
    leaving        together: Say goodbye to either one, or Pip's time running out, and both go home
                   (the friend has no daily limit of her own here: she stays as long as Pip does)
    chatting       after a few quiet minutes they sometimes chat with each other (a duet, duets.py): they walk up
                   to each other and turn face to face, then a topic from their pair's file, a few lines back and
                   forth, each one waiting for the other's words to be read. Then they wander off again.
                   You can't talk to them until it's over (a few lines); someone leaving ends it early
    closing        the app quits once both have faded away

    scene = Scene([pip, vesper])    # the first one leads: she decides whether they come today, and her time counts
"""
import random, time
import duets
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from desktop.app import App
from desktop.body import SIZE

TICK_MS = 2000   # how often someone may speak up on her own (each tick gives one of them the chance, in turn)
SPACING = SIZE * 1.4  # how far apart they come out of their portals
CHAT_GAP = SIZE * 1.1  # how far apart they stand to chat (between their feet)
MEET_SECONDS = 20      # if one hasn't reached the other by then (being dragged around...), they talk anyway

class Scene:
    def __init__(self, characters):
        self.characters = list(characters)
        self.pets = [App(c, scene=self, slot=i) for i, c in enumerate(self.characters)]
        self.gone = set()   # pets that have faded away
        lead = self.pets[0].body
        for i, pet in enumerate(self.pets[1:], 1):  # (side by side, not out of the same portal)
            pet.body.foot_x = pet.body.target = lead.foot_x - i * SPACING
            pet.body._place()
            pet.follow()
        for pet in self.pets:
            pet.body.met.connect(lambda pet=pet: self.arrived(pet))
        self.greetings = {}  # what each one said in her greeting (id(pet) -> words), for the ones after her
        self.pair = duets.load([c.folder for c in self.characters]) if len(self.characters) == 2 else None
        self.duet = None     # while they chat: {"speaker": pet, "left": lines to go, "heard": the last line,
                             #                   "walking": pets still on their way, "opener": the first line's cue}
        self.quiet_since = time.time()  # the last time anyone spoke (or you sent something)
        self.duet_gap = self.pair.gap() if self.pair else None
        self.turn = 0  # whose chance it is first on the next tick
        self.ticker = QTimer(timeout=self.tick)
        self.ticker.start(TICK_MS)

    def others_talking(self, pet):
        """Anyone but `pet` is talking, about to, or being typed to."""
        return any(p.talking or p.input.isVisible() for p in self.pets if p is not pet)

    def may_greet(self, pet):
        """The first one greets first; the others once she has (or once her greeting failed, or she's leaving)."""
        lead = self.pets[0]
        return pet is lead or lead.leaving or (lead.ready and not lead.wants_open and not lead.talking)

    def heard_for(self, pet):
        """(name, words) of the first one's greeting, for the others' greetings to answer, or None."""
        lead = self.pets[0]
        words = self.greetings.get(id(lead))
        return (lead.character.name, words) if pet is not lead and words else None

    def greeted(self, pet, words):
        self.greetings[id(pet)] = words

    def tick(self):
        """Give each one, in turn, the chance to speak up; once one does (or greets you), the rest wait.
        After a few quiet minutes, they may chat with each other instead."""
        if self.duet:
            return  # (their lines follow each other: line_done)
        if self.duet_due():
            self.start_duet()
            return
        for i in range(len(self.pets)):
            pet = self.pets[(self.turn + i) % len(self.pets)]
            pet.tick()
            if pet.talking:
                break
        self.turn = (self.turn + 1) % len(self.pets)

    # --- chatting with each other (duets.py) ---

    def activity(self):
        """Someone spoke, or you sent something: the quiet starts over."""
        self.quiet_since = time.time()

    def duet_due(self):
        """Time for a chat: they have topics, both are here and greeted, nobody's talking or typing or leaving,
        and it has been quiet long enough."""
        return bool(self.pair and all(p.ready and p.body.here and not p.wants_open and not p.leaving
                                      and not p.saying_goodbye and not p.talking and not p.input.isVisible()
                                      for p in self.pets)
                    and time.time() - self.quiet_since >= self.duet_gap)

    def start_duet(self, rng=random):
        stages = [p.snap["summary"]["stage"] for p in self.pets if p.snap]
        topic = self.pair.pick(min(stages) if len(stages) == len(self.pets) else 1, rng)
        if not topic:
            return
        speaker = next(p for p in self.pets if p.character.folder == topic["starts"])
        opener = duets.opener(speaker.character, self._partner(speaker).character, topic)
        self.duet = duet = {"speaker": speaker, "left": self.pair.length(rng), "heard": None,
                            "walking": set(self.pets), "opener": opener}
        left, right = sorted(self.pets, key=lambda p: p.body.foot_x)  # they meet halfway, face to face
        middle = (left.body.foot_x + right.body.foot_x) / 2
        screen = left.body._screen()
        middle = max(screen.left() + CHAT_GAP, min(screen.right() - CHAT_GAP, middle))
        left.body.meet(middle - CHAT_GAP / 2, 1)
        right.body.meet(middle + CHAT_GAP / 2, -1)
        QTimer.singleShot(MEET_SECONDS * 1000, lambda: self.begin_duet(duet))

    def arrived(self, pet):
        """pet has walked up to the other one: once both are there, the chat begins."""
        if self.duet and pet in self.duet["walking"]:
            self.duet["walking"].discard(pet)
            if not self.duet["walking"]:
                self.begin_duet(self.duet)

    def begin_duet(self, duet):
        """The first line, once they've met (or MEET_SECONDS have passed). Called off if you started typing to one
        of them on the way, or someone is leaving."""
        if self.duet is not duet or duet["opener"] is None:
            return  # (already begun, or over)
        if any(p.leaving or p.saying_goodbye or p.input.isVisible() for p in self.pets):
            self.end_duet()
            return
        duet["walking"].clear()
        duet["speaker"].brain.duet(duet["opener"])
        duet["opener"] = None

    def duet_said(self, pet, words):
        if self.duet and pet is self.duet["speaker"]:
            self.duet["heard"] = words

    def line_done(self, pet):
        """pet's line has been read: the other answers, or the chat is over (its last line, or you started
        typing, or someone is leaving)."""
        if not self.duet or pet is not self.duet["speaker"]:
            return
        self.duet["left"] -= 1
        stop = any(p.leaving or p.saying_goodbye or p.input.isVisible() for p in self.pets)
        if self.duet["left"] <= 0 or stop or not self.duet["heard"]:
            self.end_duet()
            return
        listener = self._partner(pet)
        self.duet["speaker"], heard = listener, self.duet["heard"]
        self.duet["heard"] = None
        listener.brain.duet(duets.reply(listener.character, pet.character, heard, last=self.duet["left"] == 1))

    def end_duet(self):
        if self.duet:
            self.duet = None
            self.activity()
            self.duet_gap = self.pair.gap()
            for pet in self.pets:
                pet.body.part()

    def _partner(self, pet):
        return next(p for p in self.pets if p is not pet)

    def leave_with(self, pet, going_home):
        """`pet` is going home: so is everyone else (her goodbye, or her time running out)."""
        self.ticker.stop()
        for other in self.pets:
            if other is not pet:
                other.leave(going_home=going_home, following=True)

    def vanished(self, pet):
        self.gone.add(id(pet))
        if len(self.gone) == len(self.pets):
            QApplication.quit()
