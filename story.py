"""A major quest told as a story over several days: [[major_quests.N.steps]] in a character's character.toml
(what each field means is written there). Pip's run-away quest, for example:

    day 1   trust reaches the gate: she senses something is wrong at the chapel and rushes home    (then 1 day away)
    day 3   she's back, overjoyed, and means to stay forever (always happy, no daily limit);
            Say goodbye twice and she begs to stay, the third time she goes home                    (then 1 day away)
    day 5   she comes back and apologizes: the quest is done, and trust can grow again

Days are calendar days, and a step that's due waits for your next visit (skip a day and nothing is missed).
Its progress is kept in the save:

    save["story"] = {"quest": "run-away", "step": 1, "begun": True, "back_on": None, "goodbyes": 2}

    story.away(save)                      at launch: she's away today (only the portal shows, no note)
    story.ignores_time_limit(save, c)     the step she's in ignores daily_minutes
    story.day_needed(save, c)             who has to come for her next step: "together", "alone", "away" or None
    story.tell(save, c, teller)           a step her friend tells for her ("away"): the text, and the step is over
    s = story.Story(character)            one per sitting: begin_text, note, mood, after_reply, goodbye,
                                          duet / duet_done, answer_note / answered

For a character with a friend on the desktop (friends.py), a story can be told by both of them, like Vesper's
summons (day 1 together: Pip nearly finds her out in a chat; day 2 only Pip, worried she's gone; day 3 only
Vesper, hurt, and she confesses). Each step can say:
    day = "together"   both have to be there (friends.plan brings both that day)
          "alone"      only she comes
          "away"       only her friend comes, and tells this step in their greeting (opens is written about the friend)
    ends = "duet"      the step is a chat with her friend on a set topic (duet = {starts, about}), and ends with it
    ends = "answer"    like a single-moment major quest: she judges your messages with a hidden [done] / [not yet]
                       tag (done_when, needs_nice) until one settles it; waiting_on = what she asked
    ends = "day"       the step lasts the whole day it begins on, however many visits (its note on every line of
                       hers), and is over on the first launch of a later day (catch_up)
    completes = true   the quest is done when this step ends (the gate opens): the steps after it are an epilogue
And any step with a mood can keep it after it ends: lingers = days (today counts as one), with lingers_note.
"""
import datetime
import memory, quests, trust
from save import write_save

def away(save, today=None):
    """True if she's away today: a story step sent her home, and the day she's due back hasn't come yet."""
    progress = save.get("story")
    today = (today or datetime.date.today()).isoformat()
    return bool(progress and progress.get("back_on") and today < progress["back_on"])

def current_step(save, character):
    """The step she's in the middle of (begun, not ended yet), or None."""
    progress = save.get("story")
    if not progress or not progress["begun"]:
        return None
    return _quest(character, progress["quest"])["steps"][progress["step"]]

def ignores_time_limit(save, character):
    """True while she's in a step with no_time_limit (Pip's stay-forever day ignores daily_minutes)."""
    step = current_step(save, character)
    return bool(step and step["no_time_limit"])

def _quest(character, quest_id):
    return next(q for q in character.major_quests.values() if q["id"] == quest_id)

def next_step(save, character, today=None):
    """Her next step: the one she's in, or the one due to begin (not while she's away), or None.
    Before the story has started, the first step of a story quest whose gate trust has reached (the save needs
    .gates for that, as trust.start gives it)."""
    progress = save.get("story")
    if progress is None:
        quest = character.major_quests.get(trust.at_gate(save))
        return quest["steps"][0] if quest and "steps" in quest else None
    if not progress["begun"] and away(save, today):
        return None
    return _quest(character, progress["quest"])["steps"][progress["step"]]

def catch_up(save, character, today=None):
    """At launch, before anything asks about her story: a step that lasted the whole of an earlier day
    (ends = "day") is over now. True if one was."""
    return bool(Story(character).day_over(save, today))

def lingering(save, today=None, character=None):
    """A step's mood that stays after it ends (lingers = days, today counting as the first, with lingers_note),
    like Vesper still hurt for the rest of the day after her confession: {mood, note, until}, or None once it has
    passed. character = whose: its note is then read from her character.toml (so an older save, or one that was
    edited, still gets it right), else from what the save kept."""
    left = save.get("lingering")
    today = (today or datetime.date.today()).isoformat()
    if not left or today > left["until"]:
        return None
    step = _lingering_step(left, character) if character else None
    return dict(left, note=step.get("lingers_note")) if step else left

def _lingering_step(left, character):
    """The step a lingering mood came from: by the quest and step the save kept, or (a save from before it kept
    them) the step that lingers with that mood."""
    for quest in character.major_quests.values():
        for i, step in enumerate(quest.get("steps", [])):
            if "quest" in left:
                if (left["quest"], left.get("step")) == (quest["id"], i):
                    return step
            elif step.get("lingers") and step.get("mood") == left["mood"]:
                return step
    return None

def mood_today(save, character, lineup=None, today=None):
    """The mood her story has her in when she arrives (so her portal shows it, not neutral first): the step she's
    in, or the one her greeting will begin (on a day with the right lineup), or a lingering one. Else None."""
    step = current_step(save, character) or next_step(save, character, today)
    if step and step.get("day") in (None, lineup) and not away(save, today):
        return step.get("mood")  # (a step beginning today: its mood, or none, whatever the last one left behind)
    left = lingering(save, today, character)
    return left["mood"] if left else None

def day_needed(save, character, today=None):
    """Who has to come for her next step ("together", "alone" or "away": see the top), or None if anyone may."""
    step = next_step(save, character, today)
    return step.get("day") if step else None

def tell(save, character, teller, today=None):
    """A step of hers that her friend tells ("away"), if it's due: its text (written about the teller, filled in for
    them, for their greeting), and the step is over. Else None."""
    step = next_step(save, character, today)
    if not step or step.get("day") != "away":
        return None
    story = Story(character)
    story._progress(save)["begun"] = True
    save.pop("lingering", None)  # (a new step: the last one's lingering mood is over)
    story._end(save, today)
    return teller.fill(step["opens"])

class Story:
    """One sitting's part in the story: which line begins a step, the step's note and mood while it lasts, and what
    happens after each of her replies (she goes home, or the quest is done)."""

    def __init__(self, character):
        self.character = character
        self.opening_now = False  # the reply being written is the one that begins a step

    def _progress(self, save):
        """Her story's progress, started if trust sits at a gate with a story quest and it hasn't yet. Else None."""
        if save.get("story") is None:
            quest = self.character.major_quests.get(trust.at_gate(save))
            if not quest or "steps" not in quest:
                return None
            save["story"] = {"quest": quest["id"], "step": 0, "begun": False, "back_on": None, "goodbyes": 0}
        return save["story"]

    def begin_text(self, save, greeting, today=None, lineup=None):
        """What she says to begin a step now (a stage direction's text), or None.
        greeting = it's her greeting: any step that's due begins there. Otherwise it's a nudge on her own, and only
        the first step begins that way (when trust reaches the gate mid-sitting).
        lineup = who's on the desktop: "together" (with her friend) or "alone". A step with a day only begins on
        such a day ("away" steps never do here: her friend tells them, see tell)."""
        today = today or datetime.date.today()
        progress = self._progress(save)
        if progress is None:
            return None
        if progress["begun"] or (progress["step"] > 0 and not greeting) or away(save, today):
            return None
        day = _quest(self.character, progress["quest"])["steps"][progress["step"]].get("day")
        if day and day != lineup:
            return None
        progress.update(begun=True, back_on=None, begun_on=today.isoformat())
        save.pop("lingering", None)  # (a new step: the last one's lingering mood is over, even on the same day)
        write_save(save)
        self.opening_now = True
        return self.character.fill(_quest(self.character, progress["quest"])["steps"][progress["step"]]["opens"])

    def note(self, save, lineup=None):
        """The step's hidden note for each of her replies while it lasts (pet.ask's note), or the note of a mood
        lingering after one (like Vesper still hurt after her confession), or None. (lineup: not used yet.)"""
        step = current_step(save, self.character)
        if step and step.get("note"):
            return self.character.fill(step["note"])
        left = lingering(save, character=self.character)
        return self.character.fill(left["note"]) if left and left.get("note") else None

    def mood(self, save, lineup=None):
        """The mood she's stuck in while the step lasts, or while it lingers after (whatever her own tag says).
        (lineup: not used yet.)"""
        step = current_step(save, self.character)
        if step and step.get("mood"):
            return step["mood"]
        left = lingering(save, character=self.character)
        return left["mood"] if left else None

    def unfinished(self, save):
        """True while her story's quest isn't done yet: its steps are the quest (the ✻ "something is on her mind"
        note). False in its epilogue, the steps after one that completes it (like Vesper's day 4)."""
        progress = save.get("story")
        return bool(progress) and "major-" + progress["quest"] not in save.get("quests_done", [])

    def day_over(self, save, today=None):
        """A step that lasts the whole day (ends = "day") is over once a later day comes. Returns what _end does,
        or None. (catch_up calls it at launch.)"""
        step = current_step(save, self.character)
        today = today or datetime.date.today()
        if step and step["ends"] == "day" and save["story"].get("begun_on", today.isoformat()) < today.isoformat():
            return self._end(save, today)
        return None

    def begs_on_goodbye(self, save):
        """True if Say goodbye should go to goodbye() instead of sending her home (a step that ends with goodbyes)."""
        step = current_step(save, self.character)
        return bool(step and step["ends"] == "goodbyes")

    def after_reply(self, save, today=None):
        """Call after each of her replies. A step that ends right after its first line ends here.
        Returns "leave" (she goes home now), "done" (the quest is finished), "next" (on to the next step), or None."""
        if not self.opening_now:
            return None
        self.opening_now = False
        if current_step(save, self.character)["ends"] == "after_it":
            return self._end(save, today)
        return None

    def goodbye(self, save, today=None):
        """You used Say goodbye during a step that ends with goodbyes: (what she says, whether she goes home now).
        Before the last one she begs and stays; on the last one the step ends. None if she isn't in such a step."""
        step = current_step(save, self.character)
        if not step or step["ends"] != "goodbyes":
            return None
        progress = save["story"]
        progress["goodbyes"] += 1
        write_save(save)
        if progress["goodbyes"] < step["goodbyes"]:  # (which goodbye it is, or she says the very same words again)
            times = {1: "once", 2: "twice"}.get(progress["goodbyes"], f"{progress['goodbyes']} times")
            return self.character.fill(step["begs"] + f". The user has told {{them}} to go {times} now, so {{they}} "
                                       "begs in new words, not what {they} said before"), False
        self._end(save, today)
        return self.character.fill(step["leaves_line"]), step["leaves"]

    def duet(self, save):
        """The chat this step wants with her friend ({starts, about}), while she's in a step that ends with one."""
        step = current_step(save, self.character)
        return step["duet"] if step and step["ends"] == "duet" else None

    def duet_done(self, save, today=None):
        """The step's chat with her friend has been had: the step is over (see _end), else None."""
        return self._end(save, today) if self.duet(save) else None

    def answer_note(self, save):
        """While she's in a step that ends with an answer: a hidden note for your message (pet.ask's note), asking
        her to judge in the same reply whether it settles it. Else None."""
        step = current_step(save, self.character)
        if not step or step["ends"] != "answer":
            return None
        # (not her opening again: given the whole opening on every message, she said it again, word for word, and
        #  judged loosely: "u need anything" settled Vesper's confession)
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
        """After her reply to a message she judged (answer_note): the step is over if she said [done] (and, with
        needs_nice, it felt nice to her). Never a rude message, a dodge or keyboard mashing. Returns what _end does,
        or None."""
        step = current_step(save, self.character)
        if not step or step["ends"] != "answer" or judged is not True or feeling == "rude":
            return None
        if step["needs_nice"] and feeling != "nice":
            return None
        if len(message.split()) < 2 or quests.is_dodge(message) or not quests.looks_like_words(message):
            return None
        return self._end(save, today)

    def _end(self, save, today=None):
        """The step is over: on to the next one (after away_days at home), or the quest is done."""
        today = today or datetime.date.today()
        progress = save["story"]
        quest = _quest(self.character, progress["quest"])
        step = quest["steps"][progress["step"]]
        if step.get("mood") and step.get("lingers"):  # (an injury doesn't heal the moment the step is over)
            last = today + datetime.timedelta(days=step["lingers"] - 1)
            save["lingering"] = {"mood": step["mood"], "until": last.isoformat(),  # (its notes: from the step)
                                 "quest": quest["id"], "step": progress["step"]}
        last_step = progress["step"] + 1 >= len(quest["steps"])
        completed = (last_step or step["completes"]) and "major-" + quest["id"] not in save.get("quests_done", [])
        if completed:  # (the gate opens: trust can grow again; any steps after this one are its epilogue)
            trust.quest_done(save, "major-" + quest["id"], quest["points"])
            kept = memory.remember(save, "milestone", self.character.fill(quest["memory"]))
            if quest["private"]:
                kept["private"] = True  # (left out of her prompt when her friend is there: Session._public)
        if not last_step:
            back = today + datetime.timedelta(days=step["away_days"] + 1) if step["away_days"] else None
            progress.update(step=progress["step"] + 1, begun=False, goodbyes=0, back_on=back and back.isoformat())
            write_save(save)
            return "done" if completed else "leave" if step["leaves"] else "next"
        del save["story"]
        write_save(save)
        return "done" if completed else "next"
