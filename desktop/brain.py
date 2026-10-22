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
    spoke = Signal(object)       # her finished reply (a session.Turn)
    closed = Signal(list)        # the sitting is over: the diary notes she wrote
    snapshot = Signal(dict)      # after every job: a copy of trust/today/memories (session.snapshot()) for the
                                 # screen to show, so the UI never reads the save while this thread writes it
    failed = Signal(str)

    def __init__(self, character):
        super().__init__()
        self.character = character  # who this mind is (character.py)
        self.session = None
        self.jobs = queue.Queue()
        self.busy = False
        threading.Thread(target=self._work, daemon=True).start()

    def start(self):
        self.jobs.put(("start",))

    def open(self):
        self.jobs.put(("open",))

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
            self.session = Session(self.character, say=lambda *_: None)
            self.ready.emit(self.session.prompt_was)
        elif what == "close":
            self.closed.emit(self.session.close() if self.session else [])
        elif self.session is None:
            return
        elif what == "open":
            self._speak("opening", self.session.open)
        elif what == "say":
            self._speak("user", self.session.user_says, args[0])
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
        turn = call(*args, on_text=on_text)
        self.spoke.emit(turn)
