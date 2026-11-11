"""One sitting with a character, with no screen code. The desktop pet (desktop/) draws it.

    s = Session("pip")           # starts the server, loads her save, gets her prompt ready
    turn = s.open()              # her greeting
    turn = s.user_says("hi")     # your message -> her reply
    turn = s.tick()              # every few seconds: she may speak up on her own (or None)
    notes = s.close()            # she writes in her diary

Calls take on_text(piece) to stream her reply and on_mood(mood), called before her words.
Every reply is logged to <character>.log in the data folder's logs/, for tuning.
"""
import datetime, os, time
from dataclasses import dataclass
from engine import llm
from mind import events, memory
from progress import roster, story, trust, visits
from engine.character import Character, DEFAULT, folder_of
from mind.directions import direction
from mind.idle import Idle
from progress.company import Company
from progress.quests import Quests, MajorQuests, QUIET_FIRST
from engine.config import N_CTX
from engine.server import start_server
from mind.pet import new_conversation, ask, context_used, warm_up
from mind.lore import Lore
from engine.save import write_save

@dataclass
class Turn:
    reply: str
    kind: str              # "opening", "user", "idle", "quest", "major" (raised her major quest) or "duet"
    feeling: str | None    # how your message felt to her (only for kind="user")
    mood: str
    seconds: float
    timings: dict          # llama-server's stats
    trust_before: int
    trust_after: int
    points_before: int
    points_after: int
    quest_done: bool = False
    number: int = 0             # which reply of the sitting (settle_mood needs it)
    stage_name: str = ""
    major_raised: bool = False
    major_done: bool = False    # the next stage is open
    time_up: bool = False       # today's time is used up: she goes home after this
    leaving: bool = False       # her story sends her home after this
    story_done: bool = False    # the next stage is open

    @property
    def stage_up(self):
        return trust.stage_of(self.trust_after) > trust.stage_of(self.trust_before)

    @property
    def stage_after(self):
        """(stage number, stage name), e.g. (2, "Learning to receive")."""
        return trust.stage_of(self.trust_after), self.stage_name

    @property
    def context_used(self):
        return context_used(self.timings)

class Session:
    def __init__(self, character=DEFAULT, say=print, slot=0, slots=1, company=(), greeting_note=None):
        """slot = her slot on the server, of `slots`. company = names of others on the desktop today.
        greeting_note = something for her greeting to bring up."""
        self.character = character if isinstance(character, Character) else Character(character)
        self.say, self.slot, self.slots = say, slot, slots
        self.friends = Company(self.character, company)
        self.greeting_note = greeting_note
        start_server(say, slots)
        self.save = trust.start(self.character.save_path, self.character.gates)  # counts today as a day logged
        self.save["mood"] = "neutral"  # every sitting starts calm
        write_save(self.save)
        self.replies = 0
        self.opened = time.time()
        self.messages = []
        self._build_prompt()
        self.transcript = []  # every line of this sitting, for her diary (old lines leave self.messages)
        t0 = time.time()
        self.prompt_was, self.context_tokens = warm_up(self.messages, self.fixed, self.slot)
        self.warm_up_seconds = time.time() - t0
        self.idle = Idle(self.character)
        self.quests = Quests(self.character)
        self.major = MajorQuests(self.character)
        self.story = story.Story(self.character)
        if self.story.day_over(self.save):
            write_save(self.save)
        self._leaving_after = False  # her next reply is a goodbye: she goes home after it
        self._raising = False  # the reply being written raises her major quest
        self.warned = self.said_goodbye = False  # her daily time
        self.n_ctx = N_CTX
        self.log(f"sitting started · persona and lore {self.prompt_was} in {self.warm_up_seconds:.1f}s · "
            f"trust {self.save['trust']} (stage {trust.stage(self.save)}, {self.save['points']} points) · "
            f"mood {self.mood} · {len(self.memories)} memories", fresh=True)

    def open(self, heard=None, on_text=None, on_mood=None):
        """Her greeting. heard = (name, words) if someone else on the desktop just greeted the user."""
        begins = self.story.begin_text(self.save, greeting=True, present=self.present)
        major = None if begins else self.friends.major_due(self.save, self.major)
        self._raising = bool((begins and self.story.unfinished(self.save)) or major)
        extra = " ".join(filter(None, [self._first_visit(), self.friends.greeting(heard), self.greeting_note, self._news(), major, begins])) or None
        return self._turn(self.idle.opening(extra), "opening", on_text, on_mood)

    def goodbye(self):
        """Say goodbye from the menu: (stage direction, kind) if she has something to say (her story begs her
        to stay, or she invites someone), else None."""
        said = self.story.goodbye(self.save)
        if not said:
            invite = roster.invite(self.save, self.character)
            if not invite:
                return None
            said = invite, True
        text, self._leaving_after = said
        self.idle.pip_spoke()
        return self._says(text), "goodbye"

    def user_says(self, text, on_text=None, on_mood=None):
        self.idle.user_spoke()
        return self._turn(text, "user", on_text, on_mood)

    def tick(self, on_text=None, on_mood=None):
        what = self.wants_to_speak()
        return self.speak(*what, on_text=on_text, on_mood=on_mood) if what else None

    def wants_to_speak(self):
        """(stage direction, kind) if she should speak up now, else None. No model call.
        Order: her daily time, her major quest, a world quest, then idle talk or today's news."""
        if time.time() - self.opened >= 60:
            self._count_stay()  # once a minute, so closing abruptly can't lose a sitting's time
        left = self.minutes_left
        if left is not None and left <= 0 and not self.said_goodbye:
            self.said_goodbye = True
            invite = roster.invite(self.save, self.character)  # her invitation takes the place of her goodbye
            if invite:
                self._leaving_after = True
                return self._says(invite), "time_up"
            return self._time_cue(self.character.time_up, left), "time_up"
        if left is not None and 0 < left <= visits.WARN_MINUTES and not self.warned:
            self.warned = True
            return self._time_cue(self.character.time_warning, left), "time_warning"
        if self.said_goodbye:
            return None
        if time.time() - self.idle.last >= QUIET_FIRST:
            begins = self.story.begin_text(self.save, greeting=False, present=self.present)
            major = begins or self.friends.major_due(self.save, self.major)
            if major:
                self.idle.pip_spoke()
                self._raising = not begins or self.story.unfinished(self.save)  # (an epilogue step isn't the quest)
                return self._brings_up(major), "major"
        ask_about = None if self.major.active(self.save) else self.quests.due(self._public())
        if ask_about:
            self.idle.pip_spoke()
            return ask_about, "quest"
        nudge = self.idle.due(self.shown_stage)
        if not nudge:
            return None
        news = self._news()  # today's news takes the place of small talk
        if not news:
            return nudge, "idle"
        return self._brings_up(news), "idle"

    def speak(self, direction, kind, on_text=None, on_mood=None):
        return self._turn(direction, kind, on_text, on_mood)

    def duet(self, direction, on_text=None, on_mood=None):
        """One line of a chat with the other character (the direction carries their line). Earns nothing."""
        self.idle.pip_spoke()
        return self._turn(direction, "duet", on_text, on_mood)

    def close(self):
        """End of the sitting. Returns the diary notes she wrote (may be empty)."""
        self._count_stay()
        try:
            notes = memory.write_diary(self.save, self.transcript, 0, self.character, self.slot)
        except llm.ServerGone:
            self.reconnect(reread=False)  # the diary is its own short prompt
            notes = memory.write_diary(self.save, self.transcript, 0, self.character, self.slot)
        if notes:
            write_save(self.save)
        self.log(f"sitting closed · trust {self.save['trust']} ({self.save['points']} points) · "
            f"{len(notes)} new diary notes" + "".join(f"\n    ✎ {n['text']}" for n in notes)
            + f"\n  {len(self.memories)} memories, {len(memory.archive(self.save))} of them only recalled when mentioned;"
            + " always in her prompt:" + "".join(f"\n    {m['when']} {m['kind']}{' (lasting)' if m.get('lasting') else ''}: "
                                                 f"{m['text']}" for m in memory.in_prompt(self.save)))
        return notes

    def _says(self, text):
        """A stage direction: she says `text` on her own."""
        return direction(self.character.fill("{name} says something on {their} own: ") + text + ".")

    def _brings_up(self, text):
        """A stage direction: she speaks up on her own, about what `text` describes."""
        return direction(self.character.fill("{name} says something on {their} own. ") + text)

    def _time_cue(self, lines, left):
        """Her time warning or goodbye line for her stage (time_warning / time_up in character.toml)."""
        n = max(1, round(left))
        line = self.character.at_stage(lines, self.shown_stage).replace("{minutes}", f"{n} minute{'s' if n != 1 else ''}")
        return self._says(self.character.fill(line))

    @property
    def minutes_left(self):
        """Minutes left today, or None if there's no limit (or her story ignores it)."""
        if story.ignores_time_limit(self.save, self.character):
            return None
        return visits.minutes_left(self.save, self.character, (time.time() - self.opened) / 60)

    @property
    def memories(self):
        return self.save.get("memories", [])

    def snapshot(self):
        """A copy of what the screen shows, safe to hand to another thread."""
        summary = trust.summary(self.save, self.character.stage_names)
        summary["minutes_today"] = visits.minutes_used(self.save, (time.time() - self.opened) / 60)
        summary["daily_minutes"] = self.character.daily_minutes
        summary["talks_on_goodbye"] = (self.story.begs_on_goodbye(self.save)
                                       or roster.invite_due(self.save, self.character))
        summary["mood_locked"] = self.story.mood(self.save, self.present)  # her mood doesn't settle back
        summary["story_duet"] = self.story.duet(self.save)
        summary["context"] = (self.context_tokens, self.n_ctx)
        return {"summary": summary, "memories": [dict(m) for m in self.memories]}

    @property
    def mood(self):
        return self.save.get("mood") or "neutral"

    def settle_mood(self, number):
        """Her mood eases back to neutral, unless she has replied since reply `number`."""
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
        """A line in her log. fresh = start the file over."""
        os.makedirs(os.path.dirname(self.character.log_path), exist_ok=True)
        with open(self.character.log_path, "w" if fresh else "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%H:%M:%S}  {text}\n")

    def _turn(self, text, kind, on_text, on_mood=None):
        """One reply: gather her hidden notes, ask the model, then update trust, quests and her story."""
        self.restage()
        trust_before, points_before = self.save["trust"], self.save["points"]
        t0 = time.time()
        raising, self._raising = self._raising, False
        leaving, self._leaving_after = self._leaving_after, False

        note, judging = self._notes_for(text, kind)
        reply, timings, feeling, mood, judged = self._ask_retrying(text, on_text, note, on_mood)
        self.transcript += self.messages[-2:]
        mood = self.story.mood(self.save, self.present) or mood  # a story step can hold her mood
        self.save["mood"] = mood or self.mood
        done, major_done, outcome = self._after_reply(text, kind, feeling, judging, judged)

        leaving = leaving or outcome == "leave"
        self._count_stay()
        self.replies += 1
        turn = Turn(reply=reply, kind=kind, feeling=feeling if kind == "user" else None, mood=self.mood,
                    seconds=time.time() - t0, timings=timings,
                    trust_before=trust_before, trust_after=self.save["trust"],
                    points_before=points_before, points_after=self.save["points"],
                    quest_done=bool(done), number=self.replies,
                    stage_name=self.character.stage_names[trust.stage(self.save)],
                    major_raised=raising, major_done=bool(major_done),
                    time_up=self.minutes_left is not None and self.minutes_left <= 0,
                    leaving=leaving, story_done=outcome == "done")
        if turn.context_used:
            self.context_tokens = turn.context_used
        self._log_turn(turn, text, tagged=mood is not None)
        return turn

    def _notes_for(self, text, kind):
        """The hidden note for this message (quest, story, old memories, friends, lore), and which quest
        she judges it for: (note or None, judging or None)."""
        note = judging = None
        stepping = self.story.note(self.save, self.present)
        answering = self.story.answer_note(self.save) if kind == "user" else None
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
        recalled = memory.recall(self._public(), text) if kind == "user" else []
        if recalled:
            self.log("brought back: " + " · ".join(m["text"] for m in recalled))
            note = "\n\n".join(filter(None, [memory.recall_note(recalled, self.character), note]))
        if kind == "user" and self.company:
            note = "\n\n".join(filter(None, [self.friends.note(), note]))
        # lore details for what you said (not her own reply: she names half her world in every greeting)
        told = self.lore.note(text)
        if told:
            self.log("lore details: " + " · ".join(self.lore.shown))
            note = "\n\n".join(filter(None, [told, note]))
        return note, judging

    def _ask_retrying(self, text, on_text, note, on_mood):
        """Ask the model. If the server went away, start it again and retry once."""
        try:
            return self._ask(text, on_text, note, on_mood)
        except llm.ServerGone:
            if self.messages and self.messages[-1] == {"role": "user", "content": text}:
                self.messages.pop()
            self.reconnect()
            if on_text:
                on_text(None)  # the screen starts her reply over
            return self._ask(text, on_text, note, on_mood)

    def _after_reply(self, text, kind, feeling, judging, judged):
        """Trust for your message, and whether it finished a quest or moved her story on.
        Returns (world quest done, major quest done, story outcome)."""
        done = major_done = None
        if kind == "user":  # talking on her own earns nothing
            trust.talked(self.save, text, feeling)
            if judging:
                self.log(f"{judging} judged: " + {True: "yes", False: "no", None: "no tag (doesn't count)"}[judged])
            if judging == "major":
                major_done = self.major.finished(self.save, text, feeling, judged)
                if major_done:
                    kept = memory.remember(self.save, "milestone",
                                           f'{major_done["memory"]} The user said: "{text.strip()[:200]}"')
                    if major_done["private"]:
                        kept["private"] = True
                    write_save(self.save)
            done = self.quests.answered(self.save, text, feeling, judged if judging == "world quest" else None)
            if done:
                memory.remember_answer(self.save, self.quests.topic(done), text, self.character)
                write_save(self.save)
        outcome = self.story.after_reply(self.save)
        if judging == "story":
            outcome = self.story.answered(self.save, text, feeling, judged) or outcome
        return done, major_done, outcome

    def _build_prompt(self):
        """Her prompt for the stage she shows, then her memories, with this sitting's chat kept after it.
        self.fixed = the cached part, self.keep = never forgotten."""
        chat = self.messages[self.keep:] if self.messages else []
        self.prompt_stage = self.shown_stage
        self.messages = new_conversation(self.character, stage=self.prompt_stage)
        self.lore = Lore(self.character, self.prompt_stage)
        self.fixed = len(self.messages)
        remembered = memory.as_message(self._public(), self.character)
        if remembered:
            self.messages.append(remembered)
        self.keep = len(self.messages)
        self.messages += chat

    @property
    def restage_due(self):
        """A gate opened this sitting, but her prompt is still the old stage's."""
        return self.shown_stage != self.prompt_stage

    def restage(self):
        """Right after a gate opens, rebuild her prompt for the new stage and read it, keeping the chat.
        (Without it, Vesper said "I'll stick with Vesper for now" just after telling you her real name.)"""
        if not self.restage_due:
            return False
        was, t0 = self.prompt_stage, time.time()
        self._build_prompt()
        try:
            how, self.context_tokens = warm_up(self.messages, self.fixed, self.slot)
        except llm.ServerGone:
            self.reconnect()
            how = "read"
        self.log(f"stage {was} -> {self.prompt_stage}: her prompt is now her new stage's ({how} in {time.time() - t0:.1f}s)")
        return True

    def _ask(self, text, on_text, note=None, on_mood=None):
        early = {}
        if on_mood:  # a story step's mood wins over her tag
            early["on_mood"] = lambda mood: on_mood(self.story.mood(self.save, self.present) or mood)
        return ask(self.messages, text, on_text=on_text, keep=self.keep, moods=self.character.moods, note=note, **early,
                   slot=self.slot)

    def _log_turn(self, t, text, tagged):
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

    # --- others on the desktop (progress/company.py) ---

    @property
    def company(self):
        """Names of the others on the desktop today."""
        return self.friends.names

    @company.setter
    def company(self, names):
        self.friends.names = list(names)

    @property
    def shown_stage(self):
        """Her trust stage as she shows it (lower while her friend is there)."""
        return self.friends.shown_stage(self.save)

    def _public(self):
        """Her save as she shows it (without secrets while her friend is there)."""
        return self.friends.public(self.save)

    @property
    def present(self):
        """Folders of everyone on the desktop, hers first (for her story)."""
        return [self.character.folder] + [folder_of(name) or name for name in self.company]

    def story_duet_done(self):
        """The chat her story wanted with her friend has been had: on to the next step."""
        outcome = self.story.duet_done(self.save)
        if outcome:
            self.log(f"story duet done: {outcome}")
        return outcome

    def _first_visit(self):
        """What her very first greeting is about (first_visit in character.toml), only once."""
        if not self.character.first_visit or self.save.get("met"):
            return None
        self.save["met"] = True
        write_save(self.save)
        return self.character.fill(self.character.first_visit) + "."

    def _news(self):
        """Today's world event if she's ready and hasn't told it (marked told now), else None."""
        today = datetime.date.today()
        news = events.due(today, self._public(), self.character)
        if not news:
            return None
        events.told(today, self.save, news)
        write_save(self.save)
        return news["text"]

    def reconnect(self, reread=True):
        """Restart llama-server and (reread) read her prompt and chat back in. The caller retries once."""
        self.log("lost llama-server: restarting it and retrying")
        start_server(self.say, self.slots)
        if reread:
            _, self.context_tokens = warm_up(self.messages, self.fixed, self.slot)

    def _count_stay(self):
        trust.stayed(self.save, (time.time() - self.opened) / 60)
        self.opened = time.time()
