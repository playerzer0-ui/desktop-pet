"""One sitting with a character, with no screen code at all. The desktop pet (desktop/) draws it.
Who it is comes from their folder (character.py); the examples here say Pip and "she".

    s = Session("pip")           # starts the server, loads her save, gets her prompt ready
    turn = s.open()              # Pip greets you
    turn = s.user_says("hi")     # your message -> her reply
    turn = s.tick()              # call every few seconds: she may speak up on her own (or None)
                                 # (or split it: what = s.wants_to_speak(), then s.speak(*what))
    notes = s.close()            # counts the last stretch of time, and Pip writes in her diary (see memory.py)

Every call takes an optional on_text(piece) to stream her reply as it's written.

For tuning, every reply is written to <character>.log, e.g. pip.log (started fresh each sitting, like server.log):
what was said, how it felt to her, her mood, how long it took, how full the context is, and trust gained.
"""
import datetime, time
import requests
from dataclasses import dataclass
import events, memory, trust
from character import Character, DEFAULT
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
    mood: str              # how she feels now: one of her Character.moods (each has a sprite in her sprites/)
    seconds: float
    timings: dict          # llama-server's stats for this reply
    trust_before: int
    trust_after: int
    points_before: int
    points_after: int
    quest_done: bool = False  # your message finished the quest she was waiting on
    number: int = 0           # which reply of the sitting this is (1, 2, ...): settle_mood() needs it
    stage_name: str = ""      # her name for the trust stage after this reply, like "Learning to receive"

    @property
    def stage_up(self):
        return trust.stage_of(self.trust_after) > trust.stage_of(self.trust_before)

    @property
    def stage_after(self):
        """(stage number, stage name) after this reply, e.g. (2, "Learning to receive")."""
        return trust.stage_of(self.trust_after), self.stage_name

    @property
    def context_used(self):
        return context_used(self.timings)

class Session:
    def __init__(self, character=DEFAULT, say=print):
        """character = a Character, or the name of their folder in character/."""
        self.character = character if isinstance(character, Character) else Character(character)
        self.say = say
        start_server(say)
        self.save = trust.start(self.character.save_path)  # counts today as a day logged
        self.save["mood"] = "neutral"  # every sitting starts calm: yesterday's mood never holds back today's events
        write_save(self.save)
        self.replies = 0           # replies so far this sitting (Turn.number)
        self.opened = time.time()  # for "duration of stay"
        self.messages = new_conversation(self.character, stage=trust.stage(self.save))
        self.fixed = len(self.messages)  # system prompt + examples: the part warm_up caches
        remembered = memory.as_message(self.save, self.character)  # her memories of you from earlier visits
        if remembered:
            self.messages.append(remembered)
        self.keep = len(self.messages)  # never forgotten during the sitting; the chat starts after these
        t0 = time.time()
        self.prompt_was = warm_up(self.messages, self.fixed)  # "read" (slow, first time since persona/lore changed) or "loaded"
        self.warm_up_seconds = time.time() - t0
        self.idle = Idle(self.character)
        self.quests = Quests(self.character)
        self.n_ctx = N_CTX
        self.log(f"sitting started · persona and lore {self.prompt_was} in {self.warm_up_seconds:.1f}s · "
            f"trust {self.save['trust']} (stage {trust.stage(self.save)}, {self.save['points']} points) · "
            f"mood {self.mood} · {len(self.memories)} memories", fresh=True)

    def open(self, on_text=None):
        return self._turn(self.idle.opening(self._news()), "opening", on_text)

    def user_says(self, text, on_text=None):
        self.idle.user_spoke()
        return self._turn(text, "user", on_text)

    def tick(self, on_text=None):
        what = self.wants_to_speak()
        return self.speak(*what, on_text=on_text) if what else None

    def wants_to_speak(self):
        """(stage direction, kind) if she should speak up on her own now, else None. Quick, no model call."""
        ask_about = self.quests.due(self.save)
        if ask_about:
            self.idle.pip_spoke()
            return ask_about, "quest"
        nudge = self.idle.due(trust.stage(self.save))
        if not nudge:
            return None
        news = self._news()  # a world event she hasn't told yet today takes the place of the small talk
        if not news:
            return nudge, "idle"
        return direction(self.character.fill("{name} says something on {their} own. ") + news), "idle"

    def speak(self, direction, kind, on_text=None):
        return self._turn(direction, kind, on_text)

    def close(self):
        """End of the sitting. Returns the diary notes she wrote about you (may be empty). Takes a few seconds."""
        self._count_stay()
        notes = memory.write_diary(self.save, self.messages, self.keep, self.character)
        if notes:
            write_save(self.save)
        self.log(f"sitting closed · trust {self.save['trust']} ({self.save['points']} points) · "
            f"{len(notes)} new diary notes" + "".join(f"\n    ✎ {n['text']}" for n in notes)
            + f"\n  all {len(self.memories)} memories:" + "".join(f"\n    {m['when']} {m['kind']}: {m['text']}" for m in self.memories))
        return notes

    @property
    def memories(self):
        return self.save.get("memories", [])

    def snapshot(self):
        """A copy of what a screen shows (trust summary, memories), safe to hand to another thread:
        the save itself keeps changing while turns run."""
        return {"summary": trust.summary(self.save, self.character.stage_names), "memories": [dict(m) for m in self.memories]}

    @property
    def mood(self):
        return self.save.get("mood") or "neutral"

    def settle_mood(self, number):
        """Her mood eases back to neutral (the screen calls this when it calms her sprite down).
        number = the Turn.number whose mood is settling: if she has replied since, her newer mood stays."""
        if number != self.replies or self.mood == "neutral":
            return False
        self.log(f"mood {self.mood} settled back to neutral")
        self.save["mood"] = "neutral"
        write_save(self.save)
        return True

    @property
    def quest_waiting(self):
        return self.quests.pending is not None

    def log(self, text, fresh=False):
        """A line in her log (pip.log), for tuning. fresh = start the file over (each new sitting)."""
        with open(self.character.log_path, "w" if fresh else "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%H:%M:%S}  {text}\n")

    def _turn(self, text, kind, on_text):
        trust_before, points_before = self.save["trust"], self.save["points"]
        t0 = time.time()
        try:
            reply, timings, feeling, mood = self._ask(text, on_text)
        except requests.ConnectionError:
            # the server went away (e.g. another copy of the pet that owned it was closed): start it again and retry once
            if self.messages and self.messages[-1] == {"role": "user", "content": text}:
                self.messages.pop()  # that question never got an answer
            self.reconnect()
            if on_text:
                on_text(None)  # tells the screen to start her reply over
            reply, timings, feeling, mood = self._ask(text, on_text)
        self.save["mood"] = mood or self.mood  # (events.py checks it: some events wait for the right mood)
        done = None
        if kind == "user":  # her talking on her own earns nothing
            trust.talked(self.save, text, feeling)
            done = self.quests.answered(self.save, text, feeling)
            if done:
                memory.remember_answer(self.save, self.quests.topic(done), text, self.character)
                write_save(self.save)
        self._count_stay()
        self.replies += 1
        turn = Turn(reply, kind, feeling if kind == "user" else None, self.mood, time.time() - t0, timings,
                    trust_before, self.save["trust"], points_before, self.save["points"], bool(done),
                    self.replies, self.character.stage_names[trust.stage(self.save)])
        self._log_turn(turn, text, tagged=mood is not None)
        return turn

    def _ask(self, text, on_text):
        return ask(self.messages, text, on_text=on_text, keep=self.keep, moods=self.character.moods)

    def _log_turn(self, t, text, tagged):
        """One reply in her log. tagged = she wrote a [mood: ...] tag (else her last mood was kept)."""
        stats = [t.kind]
        if t.feeling:
            stats.append(f"felt {t.feeling}")
        stats += [f"mood {t.mood}" + ("" if tagged else " (no tag, kept)"),
                  f"{t.seconds:.1f}s",
                  f"re-read {t.timings.get('prompt_n', '?')} · reused {t.timings.get('cache_n', '?')} tokens",
                  f"{t.timings.get('predicted_per_second', 0):.1f} tok/s",
                  f"context {t.context_used / N_CTX:.0%}"]
        if t.points_after > t.points_before:
            stats.append(f"+{t.points_after - t.points_before} points")
        if t.trust_after > t.trust_before:
            stats.append(f"trust {t.trust_before} -> {t.trust_after}")
        if t.quest_done:
            stats.append("quest done")
        self.log(" · ".join(stats) + f"\n    {'you' if t.kind == 'user' else 'cue'}: {text}"
                 f"\n    {self.character.folder}: {t.reply}")

    def _news(self):
        """Today's world event, if she's ready to tell it and hasn't yet (marked told as it's handed out), else None."""
        today = datetime.date.today()
        news = events.due(today, self.save, self.character)
        if not news:
            return None
        events.told(today, self.save, news)
        write_save(self.save)
        return news["text"]

    def reconnect(self):
        """Start llama-server again if it's gone, and get her prompt (and this sitting's chat) back into it."""
        self.log("lost llama-server: restarting it and retrying the reply")
        start_server(self.say)
        warm_up(self.messages, self.fixed)

    def _count_stay(self):
        trust.stayed(self.save, (time.time() - self.opened) / 60)
        self.opened = time.time()
