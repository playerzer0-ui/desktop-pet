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
    failed = Signal(str)

    def __init__(self):
        super().__init__()
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

    def tick(self):
        """Let her speak up on her own if she wants to (an idle thought, a quest, today's news)."""
        if not self.busy and self.jobs.empty():
            self.jobs.put(("tick",))

    def close(self):
        self.jobs.put(("close",))

    def _work(self):
        while True:
            job = self.jobs.get()
            self.busy = True
            try:
                self._do(*job)
            except Exception:
                self.failed.emit(traceback.format_exc(limit=3))
            finally:
                self.busy = False

    def _do(self, what, *args):
        if what == "start":
            from session import Session  # imported here: it starts nothing until asked
            self.session = Session(say=lambda *_: None)
            self.ready.emit(self.session.prompt_was)
        elif what == "close":
            self.closed.emit(self.session.close() if self.session else [])
        elif self.session is None:
            return
        elif what == "open":
            self._speak("opening", self.session.open)
        elif what == "say":
            self._speak("user", self.session.user_says, args[0])
        elif what == "tick":
            wanted = self.session.wants_to_speak()
            if wanted:
                self._speak(wanted[1], self.session.speak, *wanted)

    def _speak(self, kind, call, *args):
        self.speaking.emit(kind)
        turn = call(*args, on_text=self.piece.emit)
        self.spoke.emit(turn)
