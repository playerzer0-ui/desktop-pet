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
from dataclasses import dataclass
import events, llm, memory, trust, visits
from character import Character, DEFAULT
from directions import direction
from idle import Idle
from quests import Quests, MajorQuests, QUIET_FIRST
from config import N_CTX
from server import start_server
from pet import new_conversation, ask, context_used, warm_up
from save import write_save

@dataclass
class Turn:
    reply: str
    kind: str              # "opening", "user" (her answer to you), "idle" (spoke on her own), "quest" (asked one)
                           # or "major" (brought up her major quest on her own)
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
    major_raised: bool = False  # she brought up her major quest in this reply (in her greeting, or on her own)
    major_done: bool = False    # your message finished her major quest: the next stage is open
    time_up: bool = False       # her time here today is used up (visits.py): the screen sends her home after this

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
        self.save = trust.start(self.character.save_path, self.character.gates)  # counts today as a day logged
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
        self.major = MajorQuests(self.character)
        self._raising = False  # the reply being written brings up her major quest (for Turn.major_raised)
        self.warned = self.said_goodbye = False  # (her daily time: see wants_to_speak)
        self.n_ctx = N_CTX
        self.log(f"sitting started · persona and lore {self.prompt_was} in {self.warm_up_seconds:.1f}s · "
            f"trust {self.save['trust']} (stage {trust.stage(self.save)}, {self.save['points']} points) · "
            f"mood {self.mood} · {len(self.memories)} memories", fresh=True)

    def open(self, on_text=None):
        major = self.major.due(self.save)  # trust is held back: she brings up what's on her mind in her greeting
        self._raising = bool(major)
        return self._turn(self.idle.opening(" ".join(filter(None, [self._news(), major])) or None), "opening", on_text)

    def user_says(self, text, on_text=None):
        self.idle.user_spoke()
        return self._turn(text, "user", on_text)

    def tick(self, on_text=None):
        what = self.wants_to_speak()
        return self.speak(*what, on_text=on_text) if what else None

    def wants_to_speak(self):
        """(stage direction, kind) if she should speak up on her own now, else None. Quick, no model call.
        Her daily time comes first: a warning near the end ("time_warning"), then her goodbye ("time_up")."""
        if time.time() - self.opened >= 60:
            self._count_stay()  # (into the save once a minute, so closing abruptly can't wipe a sitting's time)
        left = self.minutes_left
        if left is not None and left <= 0 and not self.said_goodbye:
            self.said_goodbye = True
            return self._time_cue(self.character.time_up, left), "time_up"
        if left is not None and 0 < left <= visits.WARN_MINUTES and not self.warned:
            self.warned = True
            return self._time_cue(self.character.time_warning, left), "time_warning"
        if self.said_goodbye:
            return None  # (she's on her way home)
        if time.time() - self.idle.last >= QUIET_FIRST:  # her major quest comes first, after a quiet minute
            major = self.major.due(self.save)
            if major:
                self.idle.pip_spoke()
                self._raising = True
                return direction(self.character.fill("{name} says something on {their} own. ") + major), "major"
        ask_about = None if self.major.active(self.save) else self.quests.due(self.save)  # (world quests wait)
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
        try:
            notes = memory.write_diary(self.save, self.messages, self.keep, self.character)
        except llm.ServerGone:
            self.reconnect(reread=False)  # the diary is its own short prompt: no need to read hers back in
            notes = memory.write_diary(self.save, self.messages, self.keep, self.character)
        if notes:
            write_save(self.save)
        self.log(f"sitting closed · trust {self.save['trust']} ({self.save['points']} points) · "
            f"{len(notes)} new diary notes" + "".join(f"\n    ✎ {n['text']}" for n in notes)
            + f"\n  all {len(self.memories)} memories:" + "".join(f"\n    {m['when']} {m['kind']}: {m['text']}" for m in self.memories))
        return notes

    def _time_cue(self, lines, left):
        """Her warning or goodbye ([time_warning] / [time_up] in character.toml), the line for her trust stage:
        what she says about why she has to go depends on how much she shares yet."""
        n = max(1, round(left))
        line = self.character.at_stage(lines, trust.stage(self.save)).replace("{minutes}", f"{n} minute{'s' if n != 1 else ''}")
        return direction(self.character.fill("{name} says something on {their} own: " + line + "."))

    @property
    def minutes_left(self):
        """Minutes she has left here today, this sitting included (visits.py), or None if there's no limit."""
        return visits.minutes_left(self.save, self.character, (time.time() - self.opened) / 60)

    @property
    def memories(self):
        return self.save.get("memories", [])

    def snapshot(self):
        """A copy of what a screen shows (trust summary, memories), safe to hand to another thread:
        the save itself keeps changing while turns run."""
        summary = trust.summary(self.save, self.character.stage_names)
        summary["minutes_today"] = visits.minutes_used(self.save, (time.time() - self.opened) / 60)  # (this sitting too)
        summary["daily_minutes"] = self.character.daily_minutes
        return {"summary": summary, "memories": [dict(m) for m in self.memories]}

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
        raising, self._raising = self._raising, False
        note = judging = None  # she's waiting on a quest: she judges this message (her major quest first)
        if kind == "user":
            note = self.major.answer_note(self.save)
            judging = "major" if note else None
            if not note:
                note = self.quests.answer_note()
                judging = "world quest" if note else None
        try:
            reply, timings, feeling, mood, judged = self._ask(text, on_text, note)
        except llm.ServerGone:
            # the server went away (e.g. another copy of the pet that owned it was closed): start it again and retry once
            if self.messages and self.messages[-1] == {"role": "user", "content": text}:
                self.messages.pop()  # that question never got an answer
            self.reconnect()
            if on_text:
                on_text(None)  # tells the screen to start her reply over
            reply, timings, feeling, mood, judged = self._ask(text, on_text, note)
        self.save["mood"] = mood or self.mood  # (events.py checks it: some events wait for the right mood)
        done = major_done = None
        if kind == "user":  # her talking on her own earns nothing
            trust.talked(self.save, text, feeling)
            if note:
                self.log(f"{judging} judged: " + {True: "yes", False: "no", None: "no tag (doesn't count)"}[judged])
            if judging == "major":
                major_done = self.major.finished(self.save, text, feeling, judged)
                if major_done:
                    memory.remember(self.save, "milestone", f'{major_done["memory"]} The user said: "{text.strip()[:200]}"')
                    write_save(self.save)
            done = self.quests.answered(self.save, text, feeling, judged if judging == "world quest" else None)
            if done:
                memory.remember_answer(self.save, self.quests.topic(done), text, self.character)
                write_save(self.save)
        self._count_stay()
        self.replies += 1
        turn = Turn(reply, kind, feeling if kind == "user" else None, self.mood, time.time() - t0, timings,
                    trust_before, self.save["trust"], points_before, self.save["points"], bool(done),
                    self.replies, self.character.stage_names[trust.stage(self.save)], raising, bool(major_done),
                    self.minutes_left is not None and self.minutes_left <= 0)
        self._log_turn(turn, text, tagged=mood is not None)
        return turn

    def _ask(self, text, on_text, note=None):
        return ask(self.messages, text, on_text=on_text, keep=self.keep, moods=self.character.moods, note=note)

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
        if t.major_raised:
            stats.append("brought up her major quest")
        if t.major_done:
            stats.append("MAJOR QUEST DONE")
        if t.time_up:
            stats.append("time up for today")
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

    def reconnect(self, reread=True):
        """Start llama-server again if it's gone (llm.ServerGone), and (reread) get her prompt and this sitting's
        chat back into it. The caller then retries once."""
        self.log("lost llama-server: restarting it and retrying")
        start_server(self.say)
        if reread:
            warm_up(self.messages, self.fixed)

    def _count_stay(self):
        trust.stayed(self.save, (time.time() - self.opened) / 60)
        self.opened = time.time()
