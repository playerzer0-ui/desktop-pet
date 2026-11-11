"""Several characters on the desktop at once, each a whole App with her own mind and server slot.
The scene makes them get along: one talks at a time, they arrive side by side and greet in order,
they leave together, and after a few quiet minutes two of them sometimes chat with each other (duets.py).

    scene = Scene([pip, vesper])    # the first one leads: her time counts for everyone
"""
import itertools, random, time
from progress import duets
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from desktop.app import App
from desktop.body import SIZE

TICK_MS = 2000   # each tick, one of them in turn may speak up
SPACING = SIZE * 1.4   # how far apart their portals are
CHAT_GAP = SIZE * 1.1  # how far apart they stand to chat
MEET_SECONDS = 20      # if one hasn't reached the other by then (being dragged), they talk anyway
STORY_QUIET = 45       # seconds of quiet before a chat a story wants
STORY_LINES = 3        # lines in a story chat for two with no duet file

class Scene:
    def __init__(self, characters, rng=random):
        self.characters = list(characters)
        self.pets = [App(c, scene=self, slot=i) for i, c in enumerate(self.characters)]
        self.gone = set()
        self._spread()
        for pet in self.pets:
            pet.body.met.connect(lambda pet=pet: self.arrived(pet))
            pet.body.keep_clear = lambda pet=pet: self._taken(pet)
        self.greetings = {}  # id(pet) -> her greeting, for the ones after her
        self.pairs = {}      # frozenset of two folders -> duets.Pair
        for a, b in itertools.combinations(self.characters, 2):
            pair = duets.load([a.folder, b.folder])
            if pair:
                self.pairs[frozenset((a.folder, b.folder))] = pair
        self.duet = None     # while two chat: speaker, listener, lines left, the last line heard...
        self.quiet_since = time.time()
        self.story_duets_had = set()    # story chat topics had this sitting
        self._next_chat(rng)
        self.turn = 0  # who goes first on the next tick
        self.ticker = QTimer(timeout=self.tick)
        self.ticker.start(TICK_MS)

    def _spread(self):
        """Place the others at SPACING steps from the first one, left then right, staying on screen."""
        lead = self.pets[0].body
        screen = lead._screen()
        left, right = screen.left() + SIZE / 2, screen.right() - SIZE / 2
        spots = [lead.foot_x + side * step * SPACING for step in range(1, len(self.pets)) for side in (-1, 1)]
        fits = [x for x in spots if left <= x <= right]
        for i, pet in enumerate(self.pets[1:]):
            x = fits[i] if i < len(fits) else max(left, min(right, spots[i]))
            pet.body.foot_x = pet.body.target = x
            pet.body._place()
            pet.follow()

    def _taken(self, pet):
        """Where everyone else stands and is headed, so `pet` doesn't wander onto them."""
        return [x for p in self.pets if p is not pet for x in (p.body.foot_x, p.body.target)]

    def _pet(self, folder):
        return next((p for p in self.pets if p.character.folder == folder), None)

    def others_talking(self, pet):
        """Anyone but `pet` is talking, about to, or being typed to."""
        return any(p.talking or p.input.isVisible() for p in self.pets if p is not pet)

    def may_greet(self, pet):
        """Greetings go in order: each once everyone before her has greeted."""
        before = self.pets[:self.pets.index(pet)]
        return all(p.leaving or (p.ready and not p.wants_open and not p.talking) for p in before)

    def heard_for(self, pet):
        """(name, words) of the first one's greeting, for the others to answer, or None."""
        lead = self.pets[0]
        words = self.greetings.get(id(lead))
        return (lead.character.name, words) if pet is not lead and words else None

    def greeted(self, pet, words):
        self.greetings[id(pet)] = words

    def tick(self):
        """Give each one in turn the chance to speak up, or start a chat between two of them."""
        if self.duet:
            return  # their lines follow each other (line_done)
        wanted = self.story_duet()
        if wanted and self.free() and time.time() - self.quiet_since >= STORY_QUIET:
            self.start_duet(topic=wanted[1], owner=wanted[0])
            return
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
        """Someone spoke: the quiet starts over."""
        self.quiet_since = time.time()

    def free(self):
        """Everyone has greeted you, and nobody's talking, typing or leaving."""
        return all(p.ready and p.body.here and not p.wants_open and not p.leaving and not p.saying_goodbye
                   and not p.talking and not p.input.isVisible() for p in self.pets)

    def _next_chat(self, rng=random):
        """Pick which two chat next, and after how much quiet."""
        self.next_pair = rng.choice(list(self.pairs.values())) if self.pairs else None
        self.duet_gap = self.next_pair.gap(rng) if self.next_pair else None

    def duet_due(self):
        return bool(self.next_pair and self.free() and time.time() - self.quiet_since >= self.duet_gap)

    def story_duet(self):
        """(pet, {starts, about}) if one's story step wants a chat not had yet this sitting, else None."""
        for pet in self.pets:
            wanted = pet.snap and pet.snap["summary"].get("story_duet")
            if wanted and wanted["about"] not in self.story_duets_had and self._pet(wanted["starts"]):
                return pet, wanted
        return None

    def start_duet(self, rng=random, topic=None, owner=None):
        """Two of them walk up to each other and chat, on a story's topic (owner = whose story) or their pair's."""
        pair = None
        if topic is None:
            pair = self.next_pair
            if not pair:
                return
            two = [self._pet(f) for f in pair.folders]
            stages = [p.snap["summary"]["stage"] for p in two if p.snap]
            topic = pair.pick(min(stages) if len(stages) == 2 else 1, rng)
            if not topic:
                return
        speaker = self._pet(topic["starts"])
        listener = self._pet(topic["with"]) if topic.get("with") else None
        if listener is None:  # a story's chat: with whoever's story it is, else the next one here
            listener = owner if owner is not None and owner is not speaker else next(p for p in self.pets
                                                                                       if p is not speaker)
        if pair is None:
            pair = self.pairs.get(frozenset((speaker.character.folder, listener.character.folder)))
        opener = duets.opener(speaker.character, listener.character, topic)
        self.duet = duet = {"speaker": speaker, "listener": listener, "heard": None,
                            "left": pair.length(rng) if pair else STORY_LINES,
                            "walking": {speaker, listener}, "opener": opener, "topic": topic, "owner": owner}
        left, right = sorted((speaker, listener), key=lambda p: p.body.foot_x)  # meet halfway, face to face
        middle = (left.body.foot_x + right.body.foot_x) / 2
        screen = left.body._screen()
        middle = max(screen.left() + CHAT_GAP, min(screen.right() - CHAT_GAP, middle))
        left.body.meet(middle - CHAT_GAP / 2, 1)
        right.body.meet(middle + CHAT_GAP / 2, -1)
        QTimer.singleShot(MEET_SECONDS * 1000, lambda: self.begin_duet(duet))

    def arrived(self, pet):
        """Once both have walked up to each other, the chat begins."""
        if self.duet and pet in self.duet["walking"]:
            self.duet["walking"].discard(pet)
            if not self.duet["walking"]:
                self.begin_duet(self.duet)

    def begin_duet(self, duet):
        """The first line, once they've met. Called off if you started typing or someone is leaving."""
        if self.duet is not duet or duet["opener"] is None:
            return  # already begun, or over
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
        """pet's line has been read: the other answers, or the chat is over."""
        if not self.duet or pet is not self.duet["speaker"]:
            return
        self.duet["left"] -= 1
        stop = any(p.leaving or p.saying_goodbye or p.input.isVisible() for p in self.pets)
        if self.duet["left"] <= 0 or stop or not self.duet["heard"]:
            self.end_duet(finished=self.duet["left"] <= 0 and bool(self.duet["heard"]))
            return
        listener, heard = self.duet["listener"], self.duet["heard"]
        self.duet.update(speaker=listener, listener=pet, heard=None)
        listener.brain.duet(duets.reply(listener.character, pet.character, heard, last=self.duet["left"] == 1))

    def end_duet(self, finished=False):
        """The chat is over. finished = all lines said: a story's chat then moves her story on."""
        if self.duet:
            duet, self.duet = self.duet, None
            if finished and duet["owner"]:
                self.story_duets_had.add(duet["topic"]["about"])
                duet["owner"].brain.story_duet_done()
            self.activity()
            self._next_chat()
            for pet in (duet["speaker"], duet["listener"]):
                pet.body.part()

    def leave_with(self, pet, going_home):
        """`pet` is going home: so is everyone else."""
        self.ticker.stop()
        for other in self.pets:
            if other is not pet:
                other.leave(going_home=going_home, following=True)

    def vanished(self, pet):
        self.gone.add(id(pet))
        if len(self.gone) == len(self.pets):
            QApplication.quit()
