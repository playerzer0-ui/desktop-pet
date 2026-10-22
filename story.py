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
    s = story.Story(character)            one per sitting: begin_text, note, mood, after_reply, goodbye
"""
import datetime
import memory, trust
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

class Story:
    """One sitting's part in the story: which line begins a step, the step's note and mood while it lasts, and what
    happens after each of her replies (she goes home, or the quest is done)."""

    def __init__(self, character):
        self.character = character
        self.opening_now = False  # the reply being written is the one that begins a step

    def begin_text(self, save, greeting, today=None):
        """What she says to begin a step now (a stage direction's text), or None.
        greeting = it's her greeting: any step that's due begins there. Otherwise it's a nudge on her own, and only
        the first step begins that way (when trust reaches the gate mid-sitting)."""
        today = today or datetime.date.today()
        progress = save.get("story")
        if progress is None:  # the story hasn't started: does trust sit at a gate with a story quest?
            quest = self.character.major_quests.get(trust.at_gate(save))
            if not quest or "steps" not in quest:
                return None
            progress = save["story"] = {"quest": quest["id"], "step": 0, "begun": False, "back_on": None, "goodbyes": 0}
        if progress["begun"] or (progress["step"] > 0 and not greeting) or away(save, today):
            return None
        progress.update(begun=True, back_on=None)
        write_save(save)
        self.opening_now = True
        return self.character.fill(_quest(self.character, progress["quest"])["steps"][progress["step"]]["opens"])

    def note(self, save):
        """The step's hidden note for each of her replies while it lasts (pet.ask's note), or None."""
        step = current_step(save, self.character)
        return self.character.fill(step["note"]) if step and step.get("note") else None

    def mood(self, save):
        """The mood she's stuck in while the step lasts (whatever her own tag says), or None."""
        step = current_step(save, self.character)
        return step.get("mood") if step else None

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

    def _end(self, save, today=None):
        """The step is over: on to the next one (after away_days at home), or the quest is done."""
        today = today or datetime.date.today()
        progress = save["story"]
        quest = _quest(self.character, progress["quest"])
        step = quest["steps"][progress["step"]]
        if progress["step"] + 1 < len(quest["steps"]):
            back = today + datetime.timedelta(days=step["away_days"] + 1) if step["away_days"] else None
            progress.update(step=progress["step"] + 1, begun=False, goodbyes=0, back_on=back and back.isoformat())
            write_save(save)
            return "leave" if step["leaves"] else "next"
        del save["story"]
        trust.quest_done(save, "major-" + quest["id"], quest["points"])  # (the gate opens: trust can grow again)
        memory.remember(save, "milestone", self.character.fill(quest["memory"]))
        write_save(save)
        return "done"
