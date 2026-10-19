"""One sitting with Pip, with no screen code at all.
The CLI (cli/) draws it today; the desktop pet can drive the exact same thing later.

    s = Session()                # starts the server, loads the save, gets Pip's prompt ready
    turn = s.open()              # Pip greets you
    turn = s.user_says("hi")     # your message -> her reply
    turn = s.tick()              # call every few seconds: she may speak up on her own (or None)
                                 # (or split it: what = s.wants_to_speak(), then s.speak(*what))
    s.close()                    # counts the last stretch of time spent together

Every call takes an optional on_text(piece) to stream her reply as it's written.
"""
import time
from dataclasses import dataclass
import trust
from idle import Idle
from quests import Quests
from load import start_server, N_CTX
from pet import new_conversation, ask, context_used, warm_up

@dataclass
class Turn:
    reply: str
    kind: str              # "opening", "user" (her answer to you), "idle" (spoke on her own) or "quest" (asked one)
    feeling: str | None    # how your message felt to her: nice / neutral / rude (only for kind="user")
    seconds: float
    timings: dict          # llama-server's stats for this reply
    trust_before: int
    trust_after: int
    points_before: int
    points_after: int
    quest_done: bool = False  # your message finished the quest she was waiting on

    @property
    def stage_up(self):
        return trust.stage_of(self.trust_after) > trust.stage_of(self.trust_before)

    @property
    def context_used(self):
        return context_used(self.timings)

class Session:
    def __init__(self, say=print):
        start_server(say)
        self.save = trust.start()  # counts today as a day logged
        self.opened = time.time()  # for "duration of stay"
        self.messages = new_conversation(stage=trust.stage(self.save))
        t0 = time.time()
        self.prompt_was = warm_up(self.messages)  # "read" (slow, first time since persona/lore changed) or "loaded"
        self.warm_up_seconds = time.time() - t0
        self.idle = Idle()
        self.quests = Quests()
        self.n_ctx = N_CTX

    def open(self, on_text=None):
        return self._turn(self.idle.opening(), "opening", on_text)

    def user_says(self, text, on_text=None):
        self.idle.user_spoke()
        return self._turn(text, "user", on_text)

    def tick(self, on_text=None):
        what = self.wants_to_speak()
        return self.speak(*what, on_text=on_text) if what else None

    def wants_to_speak(self):
        """(stage direction, kind) if Pip should speak up on her own now, else None. Quick, no model call."""
        ask_about = self.quests.due(self.save)
        if ask_about:
            self.idle.pip_spoke()
            return ask_about, "quest"
        nudge = self.idle.due()
        return (nudge, "idle") if nudge else None

    def speak(self, direction, kind, on_text=None):
        return self._turn(direction, kind, on_text)

    def close(self):
        self._count_stay()

    @property
    def quest_waiting(self):
        return self.quests.pending is not None

    def _turn(self, text, kind, on_text):
        trust_before, points_before = self.save["trust"], self.save["points"]
        t0 = time.time()
        reply, timings, feeling = ask(self.messages, text, on_text=on_text)
        done = False
        if kind == "user":  # Pip talking on her own earns nothing
            trust.talked(self.save, text, feeling)
            done = self.quests.answered(self.save, text, feeling)
        self._count_stay()
        return Turn(reply, kind, feeling if kind == "user" else None, time.time() - t0, timings,
                    trust_before, self.save["trust"], points_before, self.save["points"], done)

    def _count_stay(self):
        trust.stayed(self.save, (time.time() - self.opened) / 60)
        self.opened = time.time()
