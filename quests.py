"""Minor quests: small things a character asks of you at random times. Finishing one gives trust points.
(The examples say Pip and "she".)

"Curious about your world": Pip has never seen the user's world, so now and then she asks about it.
Answer her (4+ words, not rudely, within 30 minutes) and she trusts you a bit more.
Each question is only asked until it's answered. Deeper questions unlock at higher trust stages.
"""
import random, re, time
import trust
from idle import direction

# (the questions are the character's own: [quests] in their character.toml)
POINTS = 5
FIRST_AFTER = (30, 60)  # minutes open before the first quest (random in this range)
GAP = (30, 60)          # minutes between quests
PER_DAY = 2             # most quests that can be finished in a day
ANSWER_WITHIN = 30      # minutes the user has to answer

class Quests:
    def __init__(self, character):
        self.character = character  # (character.py) whose questions, name and pronouns
        self.next = time.time() + random.uniform(*FIRST_AFTER) * 60
        self.pending = None  # (quest id, time asked) while the character waits for an answer

    def due(self, save):
        """A stage direction that makes the character ask their question, if it's time for one, else None."""
        if self.pending or time.time() < self.next or save["today"].get("quests", 0) >= PER_DAY:
            return None
        unasked = [q for q in self.character.quests if q[1] <= trust.stage(save) and "world-" + q[0] not in save["quests_done"]]
        if not unasked:
            return None
        quest_id, _, topic = random.choice(unasked)
        self.pending = ("world-" + quest_id, time.time())
        self.next = time.time() + random.uniform(*GAP) * 60
        return direction(self.character.fill("{name} has never seen the user's world and is curious about it. "
                                             "{They} asks the user about ") + f"{topic}.")

    def answered(self, save, message, feeling):
        """Call with each user message. Returns the quest id if it finished the quest the character was waiting on, else None."""
        if not self.pending:
            return None
        quest_id, asked = self.pending
        self.pending = None  # one chance: a non-answer drops it (she can ask again another time)
        if (time.time() - asked > ANSWER_WITHIN * 60 or feeling == "rude"
                or len(re.findall(r"\w+", message)) < 4):
            return None
        save["today"]["quests"] = save["today"].get("quests", 0) + 1
        trust.quest_done(save, quest_id, POINTS)
        return quest_id

    def topic(self, quest_id):
        """What a world quest asked about, like "whether it rains a lot in the user's world, ..."."""
        return next(t for q, _, t in self.character.quests if "world-" + q == quest_id)
