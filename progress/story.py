"""A major quest told as a story over several days: [[major_quests.N.steps]] in character.toml (the fields are
explained there). Pip's run-away quest, for example:

    day 1   trust reaches the gate: she senses something is wrong at the chapel and rushes home   (1 day away)
    day 3   she's back and means to stay forever; Say goodbye twice and she begs, the third time she goes
    day 5   she comes back and apologizes: the quest is done, and trust can grow again

A step that's due waits for your next visit. Progress is kept in the save:

    save["story"] = {"quest": "run-away", "step": 1, "begun": True, "back_on": None, "goodbyes": 2}
"""
import datetime, re
from mind import memory
from progress import quests, trust
from engine.save import write_save

def away(save, today=None):
    """True if a story step sent her home and the day she's due back hasn't come yet."""
    progress = save.get("story")
    today = (today or datetime.date.today()).isoformat()
    return bool(progress and progress.get("back_on") and today < progress["back_on"])

def current_step(save, character):
    """The step she's in the middle of, or None."""
    progress = save.get("story")
    if not progress or not progress["begun"]:
        return None
    return _quest(character, progress["quest"])["steps"][progress["step"]]

def ignores_time_limit(save, character):
    step = current_step(save, character)
    return bool(step and step["no_time_limit"])

def _quest(character, quest_id):
    return next(q for q in character.major_quests.values() if q["id"] == quest_id)

def next_step(save, character, today=None):
    """The step she's in, or the one due to begin (not while away), or a story quest's first step once trust
    reaches its gate (the save needs .gates). Else None."""
    progress = save.get("story")
    if progress is None:
        quest = character.major_quests.get(trust.at_gate(save))
        return quest["steps"][0] if quest and "steps" in quest else None
    if not progress["begun"] and away(save, today):
        return None
    return _quest(character, progress["quest"])["steps"][progress["step"]]

def catch_up(save, character, today=None):
    """At launch: a step that lasted all of an earlier day (ends = "day") is over now."""
    return bool(Story(character).day_over(save, today))

def lingering(save, today=None, character=None):
    """A step's mood that stays for `lingers` days after it ends: {mood, note, until}, or None.
    With character, the note is read from her character.toml, not from the save."""
    left = save.get("lingering")
    today = (today or datetime.date.today()).isoformat()
    if not left or today > left["until"]:
        return None
    step = _lingering_step(left, character) if character else None
    return dict(left, note=step.get("lingers_note")) if step else left

def _lingering_step(left, character):
    """The step a lingering mood came from (an old save only kept the mood: then the step that lingers with it)."""
    for quest in character.major_quests.values():
        for i, step in enumerate(quest.get("steps", [])):
            if "quest" in left:
                if (left["quest"], left.get("step")) == (quest["id"], i):
                    return step
            elif step.get("lingers") and step.get("mood") == left["mood"]:
                return step
    return None

def fits(step, owner, present):
    """True if this step can be played with these folders on the desktop (None = unknown)."""
    if "needs" in step:
        return present is not None and set(present) == set(step["needs"])
    if "told_by" in step or step.get("day") == "away":
        return False  # told by someone else while she's away (see tell)
    day = step.get("day")
    if day is None:
        return True
    if present is None:
        return False
    return len(present) > 1 if day == "together" else list(present) == [owner]

def who_comes(step, owner, partner=None):
    """(folders, teller or None) who have to come for this step, or None if anyone may."""
    if "needs" in step:
        return list(step["needs"]), None
    if "told_by" in step:
        return [step["told_by"]], step["told_by"]
    day = step.get("day")
    if day == "alone":
        return [owner], None
    if day == "together" and partner:
        return [owner, partner], None
    if day == "away" and partner:
        return [partner], partner
    return None

def mood_today(save, character, present=None, today=None):
    """The mood her story has her in as she arrives (so the portal shows it): her step's, or a lingering one."""
    step = current_step(save, character) or next_step(save, character, today)
    if step and fits(step, character.folder, present) and not away(save, today):
        return step.get("mood")
    left = lingering(save, today, character)
    return left["mood"] if left else None

def needed(save, character, partner=None, today=None):
    step = next_step(save, character, today)
    return who_comes(step, character.folder, partner) if step else None

def tell(save, character, teller, today=None):
    """A due step that `teller` tells for her in her greeting: its text, and the step is over. Else None."""
    step = next_step(save, character, today)
    if not step or not (step.get("told_by") == teller.folder or step.get("day") == "away"):
        return None
    story = Story(character)
    story._progress(save)["begun"] = True
    save.pop("lingering", None)  # a new step: the last one's lingering mood is over
    story._end(save, today)
    return teller.fill(step["opens"])

class Story:
    """One sitting's part in the story: beginning a step, its note and mood, and what happens after each reply."""

    def __init__(self, character):
        self.character = character
        self.opening_now = False  # the reply being written begins a step

    def _progress(self, save):
        """Her story's progress, started if trust sits at a story quest's gate. Else None."""
        if save.get("story") is None:
            quest = self.character.major_quests.get(trust.at_gate(save))
            if not quest or "steps" not in quest:
                return None
            save["story"] = {"quest": quest["id"], "step": 0, "begun": False, "back_on": None, "goodbyes": 0}
        return save["story"]

    def begin_text(self, save, greeting, today=None, present=None):
        """What she says to begin a step now, or None. Any due step begins in her greeting; on her own, only
        the first one does. A step that needs certain characters only begins with them present."""
        today = today or datetime.date.today()
        progress = self._progress(save)
        if progress is None:
            return None
        if progress["begun"] or (progress["step"] > 0 and not greeting) or away(save, today):
            return None
        step = _quest(self.character, progress["quest"])["steps"][progress["step"]]
        if not fits(step, self.character.folder, present):
            return None
        progress.update(begun=True, back_on=None, begun_on=today.isoformat())
        save.pop("lingering", None)
        write_save(save)
        self.opening_now = True
        return self.character.fill(_quest(self.character, progress["quest"])["steps"][progress["step"]]["opens"])

    def note(self, save, present=None):
        """The step's hidden note on each of her replies, or a lingering mood's note, or None."""
        step = current_step(save, self.character)
        if step and step.get("note"):
            return self.character.fill(step["note"])
        left = lingering(save, character=self.character)
        return self.character.fill(left["note"]) if left and left.get("note") else None

    def mood(self, save, present=None):
        """The mood the step (or its lingering) holds her in, whatever her tag says."""
        step = current_step(save, self.character)
        if step and step.get("mood"):
            return step["mood"]
        left = lingering(save, character=self.character)
        return left["mood"] if left else None

    def unfinished(self, save):
        """True while the story's quest isn't done (False in its epilogue)."""
        progress = save.get("story")
        return bool(progress) and "major-" + progress["quest"] not in save.get("quests_done", [])

    def day_over(self, save, today=None):
        """End an ends = "day" step once a later day has come."""
        step = current_step(save, self.character)
        today = today or datetime.date.today()
        if step and step["ends"] == "day" and save["story"].get("begun_on", today.isoformat()) < today.isoformat():
            return self._end(save, today)
        return None

    def begs_on_goodbye(self, save):
        step = current_step(save, self.character)
        return bool(step and step["ends"] == "goodbyes")

    def after_reply(self, save, today=None):
        """After each reply: ends an ends = "after_it" step. Returns "leave", "done", "next" or None."""
        if not self.opening_now:
            return None
        self.opening_now = False
        if current_step(save, self.character)["ends"] == "after_it":
            return self._end(save, today)
        return None

    def goodbye(self, save, today=None):
        """Say goodbye during an ends = "goodbyes" step: (what she says, whether she goes home), or None.
        She begs until the last one, which ends the step."""
        step = current_step(save, self.character)
        if not step or step["ends"] != "goodbyes":
            return None
        progress = save["story"]
        progress["goodbyes"] += 1
        write_save(save)
        if progress["goodbyes"] < step["goodbyes"]:  # (told which time it is, or she repeats herself)
            times = {1: "once", 2: "twice"}.get(progress["goodbyes"], f"{progress['goodbyes']} times")
            return self.character.fill(step["begs"] + f". The user has told {{them}} to go {times} now, so {{they}} "
                                       "begs in new words, not what {they} said before"), False
        self._end(save, today)
        return self.character.fill(step["leaves_line"]), step["leaves"]

    def duet(self, save):
        """The chat this step wants with her friend, if it ends with one."""
        step = current_step(save, self.character)
        return step["duet"] if step and step["ends"] == "duet" else None

    def duet_done(self, save, today=None):
        return self._end(save, today) if self.duet(save) else None

    def answer_note(self, save):
        """During an ends = "answer" step: a hidden note asking her to judge your message with [done]."""
        step = current_step(save, self.character)
        if not step or step["ends"] != "answer":
            return None
        # what she asked, not her whole opening: given that, she repeated it word for word and judged loosely
        waiting = step.get("waiting_on") or "what {they} brought up"
        return self.character.fill(
            "(Not part of the user's message: {name} has already told the user what happened, and is waiting for their "
            f"answer to what {{they}} asked: {waiting}. {{They}} answers what the user just said, in new words: {{they}} "
            "doesn't greet them again or repeat what {they} already said. Then, at the very end of {their} reply, "
            "{they} judges strictly whether this message settles it, and adds one more tag: [done] only if "
            ) + step["done_when"] + self.character.fill(
            ". [not yet] if it doesn't: a question back, a change of subject, kind words that don't answer it, or "
            "brushing it off.)")

    def answered(self, save, message, feeling, judged, today=None):
        """Ends the step if she judged [done] (and it felt nice, with needs_nice). Never rude, a dodge or mashing."""
        step = current_step(save, self.character)
        if not step or step["ends"] != "answer" or judged is not True or feeling == "rude":
            return None
        if step["needs_nice"] and feeling != "nice":
            return None
        if len(message.split()) < 2 or quests.is_dodge(message) or not quests.looks_like_words(message):
            return None
        if step["answer_words"] and not re.search(step["answer_words"], message, re.I):
            return None  # (a kind "are you okay?" once ended Vesper's confession)
        return self._end(save, today)

    def _end(self, save, today=None):
        """The step is over: on to the next (after away_days at home), or the quest is done."""
        today = today or datetime.date.today()
        progress = save["story"]
        quest = _quest(self.character, progress["quest"])
        step = quest["steps"][progress["step"]]
        if step.get("mood") and step.get("lingers"):  # an injury doesn't heal the moment the step is over
            last = today + datetime.timedelta(days=step["lingers"] - 1)
            save["lingering"] = {"mood": step["mood"], "until": last.isoformat(),
                                 "quest": quest["id"], "step": progress["step"]}
        last_step = progress["step"] + 1 >= len(quest["steps"])
        completed = (last_step or step["completes"]) and "major-" + quest["id"] not in save.get("quests_done", [])
        if completed:  # the gate opens; any later steps are its epilogue
            trust.quest_done(save, "major-" + quest["id"], quest["points"])
            kept = memory.remember(save, "milestone", self.character.fill(quest["memory"]))
            if quest["private"]:
                kept["private"] = True
        if not last_step:
            back = today + datetime.timedelta(days=step["away_days"] + 1) if step["away_days"] else None
            progress.update(step=progress["step"] + 1, begun=False, goodbyes=0, back_on=back and back.isoformat())
            write_save(save)
            return "done" if completed else "leave" if step["leaves"] else "next"
        del save["story"]
        write_save(save)
        return "done" if completed else "next"
