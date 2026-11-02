"""Several characters on the desktop at once: whoever roster.today() picked (character/roster.toml), like Pip and
the friend she brought over. Each one is a whole App (desktop/app.py) with her own body, bubble, menu, mind and save,
on her own slot of the model server (llm.py). The scene only makes them get along:

    taking turns   one talks at a time: nobody speaks up (greeting, idle talk, quest, news) while anyone else is
                   talking or you're typing to her, and you can't open a chat with one while another is talking
    arriving       side by side, each out of her own portal. The first one greets first (the first day, she
                   introduces whoever she invited: roster.introduce), then the others in order, each once everyone
                   before her is done, hearing what the first one said
    leaving        together: Say goodbye to any one, or the first one's time running out, and all go home
                   (the others have no daily limit of their own here: they stay as long as she does)
    chatting       after a few quiet minutes two of them sometimes chat with each other (a duet, duets.py): any two
                   here whose pair has a file in character/duets/. They walk up to each other and turn face to face,
                   then a topic from their pair's file, a few lines back and forth, each one waiting for the other's
                   words to be read. Then they wander off again. You can't talk to anyone until it's over (a few
                   lines); someone leaving ends it early
    closing        the app quits once everyone has faded away

    scene = Scene([pip, vesper])    # the first one leads: she decides whether they come today, and her time counts
"""
import itertools, random, time
import duets
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from desktop.app import App
from desktop.body import SIZE

TICK_MS = 2000   # how often someone may speak up on her own (each tick gives one of them the chance, in turn)
SPACING = SIZE * 1.4  # how far apart they come out of their portals
CHAT_GAP = SIZE * 1.1  # how far apart they stand to chat (between their feet)
MEET_SECONDS = 20      # if one hasn't reached the other by then (being dragged around...), they talk anyway
STORY_QUIET = 45       # seconds of quiet before a chat one of their stories wants (story.py: a step ending in a duet)
STORY_LINES = 3        # lines in a story's chat between two who have no duet file of their own

class Scene:
    def __init__(self, characters, rng=random):
        self.characters = list(characters)
        self.pets = [App(c, scene=self, slot=i) for i, c in enumerate(self.characters)]
        self.gone = set()   # pets that have faded away
        self._spread()
        for pet in self.pets:
            pet.body.met.connect(lambda pet=pet: self.arrived(pet))
        self.greetings = {}  # what each one said in her greeting (id(pet) -> words), for the ones after her
        self.pairs = {}      # frozenset of two folders -> their duets.Pair, for every two here who have a duet file
        for a, b in itertools.combinations(self.characters, 2):
            pair = duets.load([a.folder, b.folder])
            if pair:
                self.pairs[frozenset((a.folder, b.folder))] = pair
        self.duet = None     # while two chat: {"speaker": pet, "listener": pet, "left": lines to go, "heard": the
                             #   last line, "walking": pets still on their way, "opener": the first line's cue, ...}
        self.quiet_since = time.time()  # the last time anyone spoke (or you sent something)
        self.story_duets_had = set()    # story chats had this sitting (their topics), so none is had twice
        self._next_chat(rng)
        self.turn = 0  # whose chance it is first on the next tick
        self.ticker = QTimer(timeout=self.tick)
        self.ticker.start(TICK_MS)

    def _spread(self):
        """Side by side, not out of the same portal: the others at SPACING steps from the first one, left first,
        then right, skipping spots off the screen (on a screen too narrow for everyone, squeezed onto its edges)."""
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

    def _pet(self, folder):
        return next((p for p in self.pets if p.character.folder == folder), None)

    def others_talking(self, pet):
        """Anyone but `pet` is talking, about to, or being typed to."""
        return any(p.talking or p.input.isVisible() for p in self.pets if p is not pet)

    def may_greet(self, pet):
        """In order: the first one greets first, each other one once everyone before her has (or their greeting
        failed, or they're leaving)."""
        before = self.pets[:self.pets.index(pet)]
        return all(p.leaving or (p.ready and not p.wants_open and not p.talking) for p in before)

    def heard_for(self, pet):
        """(name, words) of the first one's greeting, for the others' greetings to answer, or None."""
        lead = self.pets[0]
        words = self.greetings.get(id(lead))
        return (lead.character.name, words) if pet is not lead and words else None

    def greeted(self, pet, words):
        self.greetings[id(pet)] = words

    def tick(self):
        """Give each one, in turn, the chance to speak up; once one does (or greets you), the rest wait.
        After a few quiet minutes, two of them may chat with each other instead."""
        if self.duet:
            return  # (their lines follow each other: line_done)
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
        """Someone spoke, or you sent something: the quiet starts over."""
        self.quiet_since = time.time()

    def free(self):
        """Everyone is here and has greeted you, and nobody's talking, typing or leaving."""
        return all(p.ready and p.body.here and not p.wants_open and not p.leaving and not p.saying_goodbye
                   and not p.talking and not p.input.isVisible() for p in self.pets)

    def _next_chat(self, rng=random):
        """Which two chat next (any pair here with a duet file), and after how much quiet (their file's `every`)."""
        self.next_pair = rng.choice(list(self.pairs.values())) if self.pairs else None
        self.duet_gap = self.next_pair.gap(rng) if self.next_pair else None

    def duet_due(self):
        """Time for a chat: two of them have topics, everyone's free, and it has been quiet long enough."""
        return bool(self.next_pair and self.free() and time.time() - self.quiet_since >= self.duet_gap)

    def story_duet(self):
        """(pet, {starts, about}) if one of them is in a story step that wants a chat (her snapshot's story_duet)
        that they haven't had yet this sitting, and the one who starts it is here, else None."""
        for pet in self.pets:
            wanted = pet.snap and pet.snap["summary"].get("story_duet")
            if wanted and wanted["about"] not in self.story_duets_had and self._pet(wanted["starts"]):
                return pet, wanted
        return None

    def start_duet(self, rng=random, topic=None, owner=None):
        """Two of them walk up to each other and chat. topic = a set one (a story's: owner = whose story, told once
        it's over, see story_duet_done), else the next pair's (_next_chat), for the lower of their trust stages."""
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
        if listener is None:  # (a story's chat: with whoever's story it is, or else the next one here)
            listener = owner if owner is not None and owner is not speaker else next(p for p in self.pets
                                                                                       if p is not speaker)
        if pair is None:
            pair = self.pairs.get(frozenset((speaker.character.folder, listener.character.folder)))
        opener = duets.opener(speaker.character, listener.character, topic)
        self.duet = duet = {"speaker": speaker, "listener": listener, "heard": None,
                            "left": pair.length(rng) if pair else STORY_LINES,
                            "walking": {speaker, listener}, "opener": opener, "topic": topic, "owner": owner}
        left, right = sorted((speaker, listener), key=lambda p: p.body.foot_x)  # they meet halfway, face to face
        middle = (left.body.foot_x + right.body.foot_x) / 2
        screen = left.body._screen()
        middle = max(screen.left() + CHAT_GAP, min(screen.right() - CHAT_GAP, middle))
        left.body.meet(middle - CHAT_GAP / 2, 1)
        right.body.meet(middle + CHAT_GAP / 2, -1)
        QTimer.singleShot(MEET_SECONDS * 1000, lambda: self.begin_duet(duet))

    def arrived(self, pet):
        """pet has walked up to the one she chats with: once both are there, the chat begins."""
        if self.duet and pet in self.duet["walking"]:
            self.duet["walking"].discard(pet)
            if not self.duet["walking"]:
                self.begin_duet(self.duet)

    def begin_duet(self, duet):
        """The first line, once they've met (or MEET_SECONDS have passed). Called off if you started typing to anyone
        on the way, or someone is leaving."""
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
            self.end_duet(finished=self.duet["left"] <= 0 and bool(self.duet["heard"]))
            return
        listener, heard = self.duet["listener"], self.duet["heard"]
        self.duet.update(speaker=listener, listener=pet, heard=None)
        listener.brain.duet(duets.reply(listener.character, pet.character, heard, last=self.duet["left"] == 1))

    def end_duet(self, finished=False):
        """The chat is over. finished = all its lines were said: a story's chat then moves her story on (cut
        short, it's had again later)."""
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
        """`pet` is going home: so is everyone else (her goodbye, or her time running out)."""
        self.ticker.stop()
        for other in self.pets:
            if other is not pet:
                other.leave(going_home=going_home, following=True)

    def vanished(self, pet):
        self.gone.add(id(pet))
        if len(self.gone) == len(self.pets):
            QApplication.quit()
