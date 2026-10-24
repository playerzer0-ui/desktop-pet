"""Runs session.py (Pip's whole mind: the model, trust, memory, quests, idle talk, events) on its own
thread, so the window keeps animating smoothly while she thinks. It reports back with Qt signals.

Jobs run one at a time, in order: start, then open/say/tick, and finally close.
"""
import queue, threading, traceback
from PySide6.QtCore import QObject, Signal

class Brain(QObject):
    ready = Signal(str)          # the session is up: "read" (first time since persona/lore changed) or "loaded"
    speaking = Signal(str)       # she started a reply of this kind: opening, user, idle or quest
    piece = Signal(str)          # the next bit of her reply, as it's written
    mood = Signal(str)           # her mood for the reply she's starting (it comes before her words)
    spoke = Signal(object)       # her finished reply (a session.Turn)
    closed = Signal(list)        # the sitting is over: the diary notes she wrote
    snapshot = Signal(dict)      # after every job: a copy of trust/today/memories (session.snapshot()) for the
                                 # screen to show, so the UI never reads the save while this thread writes it
    failed = Signal(str)

    def __init__(self, character, slot=0, slots=1, company=(), greeting_note=None):
        """slot, slots, company, greeting_note: see Session (her server slot, how many there are, who else is on
        the desktop, something for her greeting to bring up)."""
        super().__init__()
        self.character = character  # who this mind is (character.py)
        self.slot, self.slots, self.company, self.greeting_note = slot, slots, list(company), greeting_note
        self.session = None
        self.jobs = queue.Queue()
        self.busy = False
        threading.Thread(target=self._work, daemon=True).start()

    def start(self):
        self.jobs.put(("start",))

    def open(self, heard=None):
        """Her greeting. heard = (name, words) someone else on the desktop greeted the user with just before her."""
        self.jobs.put(("open", heard))

    def say(self, text):
        self.jobs.put(("say", text))

    @property
    def working(self):
        """Busy with a job, or holding one it hasn't started yet (like your message, just sent)."""
        return self.busy or not self.jobs.empty()

    def tick(self):
        """Let her speak up on her own if she wants to (an idle thought, a quest, today's news)."""
        if not self.working:
            self.jobs.put(("tick",))

    def settle(self, number):
        """Her mood after reply `number` eases back to neutral (in the save too, so events and Status agree)."""
        self.jobs.put(("settle", number))

    def goodbye(self):
        """You used Say goodbye while her story wants goodbyes: she begs to stay, or the last time goes home."""
        self.jobs.put(("goodbye",))

    def duet(self, direction):
        """One line of a chat with the other character on the desktop (duets.py)."""
        self.jobs.put(("duet", direction))

    def story_duet_done(self):
        """The chat her story wanted with her friend is over (story.py): her story moves on."""
        self.jobs.put(("story_duet_done",))

    def close(self):
        self.jobs.put(("close",))

    def _work(self):
        while True:
            job = self.jobs.get()
            self.busy = True
            try:
                self._do(*job)
                if self.session:
                    self.snapshot.emit(self.session.snapshot())
            except Exception:
                self.failed.emit(traceback.format_exc(limit=3))
            finally:
                self.busy = False

    def _do(self, what, *args):
        if what == "start":
            from session import Session  # imported here: it starts nothing until asked
            self.session = Session(self.character, say=lambda *_: None, slot=self.slot, slots=self.slots,
                                   company=self.company, greeting_note=self.greeting_note)
            self.ready.emit(self.session.prompt_was)
        elif what == "close":
            self.closed.emit(self.session.close() if self.session else [])
        elif self.session is None:
            return
        elif what == "open":
            self._speak("opening", self.session.open, args[0] if args else None)
        elif what == "say":
            self._speak("user", self.session.user_says, args[0])
        elif what == "duet":
            self._speak("duet", self.session.duet, args[0])
        elif what == "story_duet_done":
            self.session.story_duet_done()
        elif what == "settle":
            self.session.settle_mood(args[0])
        elif what == "goodbye":
            wanted = self.session.goodbye()
            if wanted:
                self._speak(wanted[1], self.session.speak, *wanted)
        elif what == "tick":
            wanted = self.session.wants_to_speak()
            if wanted:
                self._speak(wanted[1], self.session.speak, *wanted)

    def _speak(self, kind, call, *args):
        self.speaking.emit(kind)

        def on_text(piece):
            if piece is None:  # the server had to be restarted: her reply starts over
                self.speaking.emit(kind)
            else:
                self.piece.emit(piece)
        turn = call(*args, on_text=on_text, on_mood=self.mood.emit)
        self.spoke.emit(turn)
