"""One sitting with Pip, with no screen code at all.
The CLI (cli/) draws it today; the desktop pet can drive the exact same thing later.

    s = Session()                # starts the server, loads the save, gets Pip's prompt ready
    turn = s.open()              # Pip greets you
    turn = s.user_says("hi")     # your message -> her reply
    turn = s.tick()              # call every few seconds: she may speak up on her own (or None)
                                 # (or split it: what = s.wants_to_speak(), then s.speak(*what))
    notes = s.close()            # counts the last stretch of time, and Pip writes in her diary (see memory.py)

Every call takes an optional on_text(piece) to stream her reply as it's written.
"""
import datetime, time
from dataclasses import dataclass
import events, memory, quests, trust
from idle import Idle, direction
from quests import Quests
from load import start_server, N_CTX
from pet import new_conversation, ask, context_used, warm_up
from save import write_save

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
        remembered = memory.as_message(self.save)  # her memories of you from earlier visits
        if remembered:
            self.messages.append(remembered)
        self.keep = len(self.messages)  # never forgotten during the sitting; the chat starts after these
        t0 = time.time()
        self.prompt_was = warm_up(self.messages)  # "read" (slow, first time since persona/lore changed) or "loaded"
        self.warm_up_seconds = time.time() - t0
        self.idle = Idle()
        self.quests = Quests()
        self.n_ctx = N_CTX

    def open(self, on_text=None):
        return self._turn(self.idle.opening(self._news()), "opening", on_text)

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
        nudge = self.idle.due(trust.stage(self.save))
        if not nudge:
            return None
        news = self._news()  # a world event she hasn't told yet today takes the place of the small talk
        return (direction(f"Pip says something on her own. {news}"), "idle") if news else (nudge, "idle")

    def speak(self, direction, kind, on_text=None):
        return self._turn(direction, kind, on_text)

    def close(self):
        """End of the sitting. Returns the diary notes Pip wrote about you (may be empty). Takes a few seconds."""
        self._count_stay()
        notes = memory.write_diary(self.save, self.messages, self.keep)
        if notes:
            write_save(self.save)
        return notes

    @property
    def memories(self):
        return self.save.get("memories", [])

    @property
    def quest_waiting(self):
        return self.quests.pending is not None

    def _turn(self, text, kind, on_text):
        trust_before, points_before = self.save["trust"], self.save["points"]
        t0 = time.time()
        reply, timings, feeling = ask(self.messages, text, on_text=on_text, keep=self.keep)
        done = None
        if kind == "user":  # Pip talking on her own earns nothing
            trust.talked(self.save, text, feeling)
            done = self.quests.answered(self.save, text, feeling)
            if done:
                memory.remember_answer(self.save, quests.topic(done), text)
                write_save(self.save)
        self._count_stay()
        return Turn(reply, kind, feeling if kind == "user" else None, time.time() - t0, timings,
                    trust_before, self.save["trust"], points_before, self.save["points"], bool(done))

    def _news(self):
        """Today's world event, if Pip is ready to tell it and hasn't yet (marked told as it's handed out), else None."""
        today = datetime.date.today()
        news = events.due(today, self.save)
        if not news:
            return None
        events.told(today, self.save, news)
        write_save(self.save)
        return news["text"]

    def _count_stay(self):
        trust.stayed(self.save, (time.time() - self.opened) / 60)
        self.opened = time.time()
