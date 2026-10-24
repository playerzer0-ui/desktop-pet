"""One sitting with a character, with no screen code at all. The desktop pet (desktop/) draws it.
Who it is comes from their folder (character.py); the examples here say Pip and "she".

    s = Session("pip")           # starts the server, loads her save, gets her prompt ready
    turn = s.open()              # Pip greets you
    turn = s.user_says("hi")     # your message -> her reply
    turn = s.tick()              # call every few seconds: she may speak up on her own (or None)
                                 # (or split it: what = s.wants_to_speak(), then s.speak(*what))
    notes = s.close()            # counts the last stretch of time, and Pip writes in her diary (see memory.py)

Every call takes an optional on_text(piece) to stream her reply as it's written, and on_mood(mood), called with
her mood as soon as it's known (it comes before her words: see pet.ask), so her face can change as she starts.

For tuning, every reply is written to <character>.log, e.g. pip.log (started fresh each sitting, like server.log):
what was said, how it felt to her, her mood, how long it took, how full the context is, and trust gained.
"""
import datetime, time
from dataclasses import dataclass
import events, friends, llm, memory, story, trust, visits
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
    kind: str              # "opening", "user" (her answer to you), "idle" (spoke on her own), "quest" (asked one),
                           # "major" (brought up her major quest on her own) or "duet" (a line to her friend)
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
    leaving: bool = False       # a story quest sends her home after this reply (story.py), for a day or more
    story_done: bool = False    # this reply finished a story quest: the next stage is open

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
    def __init__(self, character=DEFAULT, say=print, slot=0, slots=1, company=(), greeting_note=None):
        """character = a Character, or the name of their folder in character/.
        slot = their own slot on the server, of `slots` (one per character on the desktop: see llm.py).
        company = the names of anyone else on the desktop with them today (desktop/scene.py).
        greeting_note = something for their greeting to bring up (a stage direction's text), like why their
        friend isn't here today (friends.plan)."""
        self.character = character if isinstance(character, Character) else Character(character)
        self.say, self.slot, self.slots, self.company = say, slot, slots, list(company)
        self.greeting_note = greeting_note
        start_server(say, slots)
        self.save = trust.start(self.character.save_path, self.character.gates)  # counts today as a day logged
        self.save["mood"] = "neutral"  # every sitting starts calm: yesterday's mood never holds back today's events
        write_save(self.save)
        self.replies = 0           # replies so far this sitting (Turn.number)
        self.opened = time.time()  # for "duration of stay"
        # (with her friend there, she wears her mask: her prompt is her public self, see shown_stage and _public)
        self.messages = new_conversation(self.character, stage=self.shown_stage)
        self.fixed = len(self.messages)  # system prompt + examples: the part warm_up caches
        remembered = memory.as_message(self._public(), self.character)  # her memories of you from earlier visits
        if remembered:
            self.messages.append(remembered)
        self.keep = len(self.messages)  # never forgotten during the sitting; the chat starts after these
        self.transcript = []  # every line of this sitting's chat, for her diary (old lines leave self.messages)
        t0 = time.time()
        self.prompt_was = warm_up(self.messages, self.fixed, self.slot)  # "read" (slow, first time since persona/lore changed) or "loaded"
        self.warm_up_seconds = time.time() - t0
        self.idle = Idle(self.character)
        self.quests = Quests(self.character)
        self.major = MajorQuests(self.character)
        self.story = story.Story(self.character)  # a major quest told over several days (story.py)
        if self.story.day_over(self.save):  # (a step that lasted all of an earlier day is over now)
            write_save(self.save)
        self._leaving_after = False  # her next reply is her story goodbye: she goes home after it
        self._raising = False  # the reply being written brings up her major quest (for Turn.major_raised)
        self.warned = self.said_goodbye = False  # (her daily time: see wants_to_speak)
        self.n_ctx = N_CTX
        self.log(f"sitting started · persona and lore {self.prompt_was} in {self.warm_up_seconds:.1f}s · "
            f"trust {self.save['trust']} (stage {trust.stage(self.save)}, {self.save['points']} points) · "
            f"mood {self.mood} · {len(self.memories)} memories", fresh=True)

    def open(self, heard=None, on_text=None, on_mood=None):
        """Her greeting. heard = (name, words): someone else on the desktop just greeted the user (desktop/scene.py),
        so hers can answer it, like Vesper after Pip introduces her."""
        begins = self.story.begin_text(self.save, greeting=True, lineup=self.lineup)  # a story step due today begins
        major = None if begins else self._major_due()  # trust is held back: she brings it up in her greeting
        self._raising = bool((begins and self.story.unfinished(self.save)) or major)  # (not an epilogue step's)
        extra = " ".join(filter(None, [self._first_visit(), self._with_company(heard), self.greeting_note, self._news(), major, begins])) or None
        return self._turn(self.idle.opening(extra), "opening", on_text, on_mood)

    def goodbye(self):
        """Say goodbye (the menu) while she has something to say about it (talks_on_goodbye in snapshot()):
        (stage direction, kind) for what she says, or None if goodbye should just send her home.
        A story step that wants goodbyes comes first (she begs to stay or, the last time, goes home); else her
        invitation to her friend (friends.py), after which she goes home."""
        said = self.story.goodbye(self.save)
        if not said:
            invite = friends.invite(self.save, self.character)
            if not invite:
                return None
            said = invite, True
        text, self._leaving_after = said
        self.idle.pip_spoke()
        return direction(self.character.fill("{name} says something on {their} own: ") + text + "."), "goodbye"

    def user_says(self, text, on_text=None, on_mood=None):
        self.idle.user_spoke()
        return self._turn(text, "user", on_text, on_mood)

    def tick(self, on_text=None, on_mood=None):
        what = self.wants_to_speak()
        return self.speak(*what, on_text=on_text, on_mood=on_mood) if what else None

    def wants_to_speak(self):
        """(stage direction, kind) if she should speak up on her own now, else None. Quick, no model call.
        Her daily time comes first: a warning near the end ("time_warning"), then her goodbye ("time_up")."""
        if time.time() - self.opened >= 60:
            self._count_stay()  # (into the save once a minute, so closing abruptly can't wipe a sitting's time)
        left = self.minutes_left
        if left is not None and left <= 0 and not self.said_goodbye:
            self.said_goodbye = True
            invite = friends.invite(self.save, self.character)  # (her invitation takes the place of her goodbye)
            if invite:
                self._leaving_after = True  # (she won't be back tomorrow: her friend comes instead)
                return direction(self.character.fill("{name} says something on {their} own: ") + invite + "."), "time_up"
            return self._time_cue(self.character.time_up, left), "time_up"
        if left is not None and 0 < left <= visits.WARN_MINUTES and not self.warned:
            self.warned = True
            return self._time_cue(self.character.time_warning, left), "time_warning"
        if self.said_goodbye:
            return None  # (she's on her way home)
        if time.time() - self.idle.last >= QUIET_FIRST:  # her major quest comes first, after a quiet minute
            begins = self.story.begin_text(self.save, greeting=False, lineup=self.lineup)
            major = begins or self._major_due()
            if major:
                self.idle.pip_spoke()
                self._raising = not begins or self.story.unfinished(self.save)  # (an epilogue step isn't the quest)
                return direction(self.character.fill("{name} says something on {their} own. ") + major), "major"
        ask_about = None if self.major.active(self.save) else self.quests.due(self.save)  # (world quests wait)
        if ask_about:
            self.idle.pip_spoke()
            return ask_about, "quest"
        nudge = self.idle.due(self.shown_stage)
        if not nudge:
            return None
        news = self._news()  # a world event she hasn't told yet today takes the place of the small talk
        if not news:
            return nudge, "idle"
        return direction(self.character.fill("{name} says something on {their} own. ") + news), "idle"

    def speak(self, direction, kind, on_text=None, on_mood=None):
        return self._turn(direction, kind, on_text, on_mood)

    def duet(self, direction, on_text=None, on_mood=None):
        """One line of a chat with the other character on the desktop (duets.py: the direction carries what they
        said). Counts as her speaking, so her own idle talk waits; earns nothing."""
        self.idle.pip_spoke()
        return self._turn(direction, "duet", on_text, on_mood)

    def close(self):
        """End of the sitting. Returns the diary notes she wrote about you (may be empty). Takes a few seconds."""
        self._count_stay()
        try:
            notes = memory.write_diary(self.save, self.transcript, 0, self.character, self.slot)
        except llm.ServerGone:
            self.reconnect(reread=False)  # the diary is its own short prompt: no need to read hers back in
            notes = memory.write_diary(self.save, self.transcript, 0, self.character, self.slot)
        if notes:
            write_save(self.save)
        self.log(f"sitting closed · trust {self.save['trust']} ({self.save['points']} points) · "
            f"{len(notes)} new diary notes" + "".join(f"\n    ✎ {n['text']}" for n in notes)
            + f"\n  {len(self.memories)} memories, {len(memory.archive(self.save))} of them only recalled when mentioned;"
            + " always in her prompt:" + "".join(f"\n    {m['when']} {m['kind']}{' (lasting)' if m.get('lasting') else ''}: "
                                                 f"{m['text']}" for m in memory.in_prompt(self.save)))
        return notes

    def _time_cue(self, lines, left):
        """Her warning or goodbye ([time_warning] / [time_up] in character.toml), the line for her trust stage:
        what she says about why she has to go depends on how much she shares yet."""
        n = max(1, round(left))
        line = self.character.at_stage(lines, self.shown_stage).replace("{minutes}", f"{n} minute{'s' if n != 1 else ''}")
        return direction(self.character.fill("{name} says something on {their} own: " + line + "."))

    @property
    def minutes_left(self):
        """Minutes she has left here today, this sitting included (visits.py), or None if there's no limit
        (also while a story step ignores it)."""
        if story.ignores_time_limit(self.save, self.character):
            return None
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
        summary["talks_on_goodbye"] = (self.story.begs_on_goodbye(self.save)  # (Say goodbye: she begs to stay,
                                       or friends.invite_due(self.save, self.character))  # or invites her friend)
        summary["mood_locked"] = self.story.mood(self.save, self.lineup)  # (her mood doesn't settle back to neutral)
        summary["story_duet"] = self.story.duet(self.save)  # (a chat with her friend her story wants: scene.py)
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

    def _turn(self, text, kind, on_text, on_mood=None):
        trust_before, points_before = self.save["trust"], self.save["points"]
        t0 = time.time()
        raising, self._raising = self._raising, False
        leaving, self._leaving_after = self._leaving_after, False
        note = judging = None  # she's waiting on a quest: she judges this message (her major quest first)
        stepping = self.story.note(self.save, self.lineup)  # (a story step's note on every line of hers while it lasts)
        answering = self.story.answer_note(self.save) if kind == "user" else None  # (a step that ends on your answer)
        if answering:
            note, judging = "\n\n".join(filter(None, [stepping, answering])), "story"
        elif stepping:
            note = stepping
        elif kind == "user":
            note = self.major.answer_note(self.save)
            judging = "major" if note else None
            if not note:
                note = self.quests.answer_note()
                judging = "world quest" if note else None
        recalled = memory.recall(self._public(), text) if kind == "user" else []  # old memories this message mentions
        if recalled:
            self.log("brought back: " + " · ".join(m["text"] for m in recalled))
            note = "\n\n".join(filter(None, [memory.recall_note(recalled, self.character), note]))  # (judging last)
        if kind == "user" and self.company:  # (who's who, when her friend is on the desktop with her)
            note = "\n\n".join(filter(None, [self._company_note(), note]))
        try:
            reply, timings, feeling, mood, judged = self._ask(text, on_text, note, on_mood)
        except llm.ServerGone:
            # the server went away (e.g. another copy of the pet that owned it was closed): start it again and retry once
            if self.messages and self.messages[-1] == {"role": "user", "content": text}:
                self.messages.pop()  # that question never got an answer
            self.reconnect()
            if on_text:
                on_text(None)  # tells the screen to start her reply over
            reply, timings, feeling, mood, judged = self._ask(text, on_text, note, on_mood)
        self.transcript += self.messages[-2:]  # (this question and her answer)
        mood = self.story.mood(self.save, self.lineup) or mood  # (a story step can keep her in one mood, whatever her tag says)
        self.save["mood"] = mood or self.mood  # (events.py checks it: some events wait for the right mood)
        done = major_done = None
        if kind == "user":  # her talking on her own earns nothing
            trust.talked(self.save, text, feeling)
            if judging:
                self.log(f"{judging} judged: " + {True: "yes", False: "no", None: "no tag (doesn't count)"}[judged])
            if judging == "major":
                major_done = self.major.finished(self.save, text, feeling, judged)
                if major_done:
                    kept = memory.remember(self.save, "milestone",
                                           f'{major_done["memory"]} The user said: "{text.strip()[:200]}"')
                    if major_done["private"]:
                        kept["private"] = True  # (left out of her prompt when her friend is there: _public)
                    write_save(self.save)
            done = self.quests.answered(self.save, text, feeling, judged if judging == "world quest" else None)
            if done:
                memory.remember_answer(self.save, self.quests.topic(done), text, self.character)
                write_save(self.save)
        outcome = self.story.after_reply(self.save)  # (a step that ends right after its first line ends now)
        if judging == "story":  # (or one that ends on your answer, if this was it)
            outcome = self.story.answered(self.save, text, feeling, judged) or outcome
        leaving = leaving or outcome == "leave"
        self._count_stay()
        self.replies += 1
        turn = Turn(reply, kind, feeling if kind == "user" else None, self.mood, time.time() - t0, timings,
                    trust_before, self.save["trust"], points_before, self.save["points"], bool(done),
                    self.replies, self.character.stage_names[trust.stage(self.save)], raising, bool(major_done),
                    self.minutes_left is not None and self.minutes_left <= 0, leaving, outcome == "done")
        self._log_turn(turn, text, tagged=mood is not None)
        return turn

    def _ask(self, text, on_text, note=None, on_mood=None):
        early = {}
        if on_mood:  # (a story step that keeps her in one mood wins over her tag, as in _turn)
            early["on_mood"] = lambda mood: on_mood(self.story.mood(self.save, self.lineup) or mood)
        return ask(self.messages, text, on_text=on_text, keep=self.keep, moods=self.character.moods, note=note, **early,
                   slot=self.slot)

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
        if t.leaving:
            stats.append("story: she goes home")
        if t.story_done:
            stats.append("STORY QUEST DONE")
        self.log(" · ".join(stats) + f"\n    {'you' if t.kind == 'user' else 'cue'}: {text}"
                 f"\n    {self.character.folder}: {t.reply}")

    def _with_company(self, heard=None):
        """For her greeting: who else is on the desktop with her today (desktop/scene.py), or None.
        heard = (name, words) if one of them has just greeted the user: she greets the user after them.
        The first day she brings her friend along (friends.introduce), her greeting introduces her friend."""
        if not self.company:
            return None
        if heard:
            name, words = heard
            return self.character.fill(f"{{Their}} friend {name} is on the desktop with {{them}} today, and just "
                f'greeted the user, saying: "{words}" {{They}} greets the user too, after {name}, and can react to '
                f"what {name} said.")
        introduce = friends.introduce(self.save, self.character)
        if introduce:
            return introduce + "."
        return self.character.fill("{Their} friend ") + " and ".join(self.company) + self.character.fill(
            " is on the desktop with {them} today too, but this greeting is {their} own, to the user.")

    @property
    def lineup(self):
        """Who's on the desktop, for her story's steps (story.py's day): "together" with her friend, or "alone"."""
        return "together" if self.company else "alone"

    def story_duet_done(self):
        """The chat her story wanted with her friend has been had (desktop/scene.py): on to the next step."""
        outcome = self.story.duet_done(self.save)
        if outcome:
            self.log(f"story duet done: {outcome}")
        return outcome

    def _company_note(self):
        """On a day her friend is on the desktop with her (desktop/scene.py): a hidden note on each of your messages,
        so she keeps straight who's who. Without it, "who bakes better?" made Vesper talk as if YOU were Pip."""
        others = " and ".join(self.company)
        return self.character.fill(
            f"(Not part of the user's message: {others} is on the desktop beside {{name}} and can hear everything, "
            f"but this message is from the user, the human who owns the desktop, and {{name}} answers the user. "
            f'In {{their}} reply, "you" is the user. {others} is someone else: when the message is about {others}, '
            f"{{they}} talks about {others} by name. {{They}} never mixes up what is {{their}} own, what is {others}'s "
            f"and what is the user's.)")

    # --- her mask: what she shows when her friend is on the desktop too ---
    # Told "never say these in front of Pip", Vesper still let her secrets slip ("someone dangerous is watching her"),
    # however it was worded: a small model leaks what's in its prompt. So with her friend there, the secrets aren't in
    # it: she's her public self (with_friend_stage in character.toml), and private memories are left out.

    @property
    def masked(self):
        """True while her friend is on the desktop and she has a public self to show (with_friend_stage)."""
        return bool(self.company and self.character.with_friend_stage)

    @property
    def shown_stage(self):
        """Her trust stage as she shows it: her prompt, idle talk, event reactions and time lines go by this.
        With her friend there, no higher than with_friend_stage."""
        stage = trust.stage(self.save)
        return min(stage, self.character.with_friend_stage) if self.masked else stage

    def _public(self):
        """Her save as she shows it (for memories and events): with her friend there, private memories (from private
        quests) left out and trust no higher than her shown stage. Else the save itself."""
        if not self.masked:
            return self.save
        private = {self.character.fill(q["memory"]) for q in self.character.major_quests.values() if q["private"]}
        memories = [m for m in self.save.get("memories", [])
                    if not m.get("private") and not any(m["text"].startswith(p) for p in private)]
        return dict(self.save, memories=memories, trust=min(self.save["trust"], self.shown_stage * 2))

    def _major_due(self):
        """Her major quest to bring up now (major.due), but not a private one while her friend is there."""
        quest = self.major.active(self.save)
        if self.masked and quest and quest["private"]:
            return None
        return self.major.due(self.save)

    def _first_visit(self):
        """What her very first greeting is about (first_visit in character.toml, like Vesper being sent by Pip),
        the first time she's ever opened, else None. Marked in her save, so it's only once."""
        if not self.character.first_visit or self.save.get("met"):
            return None
        self.save["met"] = True
        write_save(self.save)
        return self.character.fill(self.character.first_visit) + "."

    def _news(self):
        """Today's world event, if she's ready to tell it and hasn't yet (marked told as it's handed out), else None."""
        today = datetime.date.today()
        news = events.due(today, self._public(), self.character)  # (her reactions as she shows them: see _public)
        if not news:
            return None
        events.told(today, self.save, news)
        write_save(self.save)
        return news["text"]

    def reconnect(self, reread=True):
        """Start llama-server again if it's gone (llm.ServerGone), and (reread) get her prompt and this sitting's
        chat back into it. The caller then retries once."""
        self.log("lost llama-server: restarting it and retrying")
        start_server(self.say, self.slots)
        if reread:
            warm_up(self.messages, self.fixed, self.slot)

    def _count_stay(self):
        trust.stayed(self.save, (time.time() - self.opened) / 60)
        self.opened = time.time()
