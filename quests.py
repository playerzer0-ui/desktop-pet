"""Minor quests: small things Pip asks of you at random times. Finishing one gives trust points.

"Curious about your world": Pip has never seen the user's world, so now and then she asks about it.
Answer her (4+ words, not rudely, within 30 minutes) and she trusts you a bit more.
Each question is only asked until it's answered. Deeper questions unlock at higher trust stages.
"""
import random, re, time
import trust
from idle import direction

WORLD = [  # (id, stage it unlocks at, what Pip asks about)
    # stage 1: surface things - warmth, rain, food
    ("rain", 1, "whether it rains a lot in the user's world, and whether they like rain"),
    ("warm", 1, "what people in the user's world do to keep warm on cold nights"),
    ("food", 1, "what people eat in the user's world, and whether they have bread"),
    ("outside", 1, "what the user's world looks like outside this desktop"),
    ("comfort", 1, "what the user likes to drink or do when they need comfort"),
    # stage 2: daily life
    ("work", 2, "what the user does all day for work or study, and whether it's tiring"),
    ("money", 2, "how money works in the user's world, and whether one person controls it all"),
    ("poor", 2, "whether people in the user's world help the poor and hungry"),
    ("festival", 2, "what festivals or holidays people celebrate in the user's world"),
    # stage 3: faith
    ("gods", 3, "whether people in the user's world believe in gods"),
    ("prayer", 3, "whether people in the user's world pray, and what they pray for"),
    ("magic", 3, "whether the user's world has magic, or only technology"),
    # stage 4: her fears
    ("rulers", 4, "whether the people who rule the user's world are kind or frightening"),
    ("refuge", 4, "whether there's anywhere in the user's world where anyone can be safe"),
    ("rest", 4, "how people in the user's world rest when they're too tired to go on"),
    # stage 5: staying or going
    ("visits", 5, "whether the user wants her to keep visiting, or if she's a bother"),
    ("listening", 5, "whether the user thinks gods would hear her if she prayed from their world"),
]
POINTS = 5
FIRST_AFTER = (30, 60)  # minutes open before the first quest (random in this range)
GAP = (30, 60)          # minutes between quests
PER_DAY = 2             # most quests that can be finished in a day
ANSWER_WITHIN = 30      # minutes the user has to answer

class Quests:
    def __init__(self):
        self.next = time.time() + random.uniform(*FIRST_AFTER) * 60
        self.pending = None  # (quest id, time asked) while Pip waits for an answer

    def due(self, save):
        """A stage direction that makes Pip ask her question, if it's time for one, else None."""
        if self.pending or time.time() < self.next or save["today"].get("quests", 0) >= PER_DAY:
            return None
        unasked = [q for q in WORLD if q[1] <= trust.stage(save) and "world-" + q[0] not in save["quests_done"]]
        if not unasked:
            return None
        quest_id, _, topic = random.choice(unasked)
        self.pending = ("world-" + quest_id, time.time())
        self.next = time.time() + random.uniform(*GAP) * 60
        return direction(f"Pip has never seen the user's world and is curious about it. "
                         f"She asks the user about {topic}.")

    def answered(self, save, message, feeling):
        """Call with each user message. Returns the quest id if it finished the quest Pip was waiting on, else None."""
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

def topic(quest_id):
    """What a world quest asked about, like "whether it rains a lot in the user's world, ..."."""
    return next(t for q, _, t in WORLD if "world-" + q == quest_id)
