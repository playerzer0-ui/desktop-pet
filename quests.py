"""Minor quests: small things a character asks of you at random times. Finishing one gives trust points.
(The examples say Pip and "she".)

"Curious about your world": Pip has never seen the user's world, so now and then she asks about it.
Answer her (4+ words, not rudely, within 30 minutes) and she trusts you a bit more. She judges whether your
message really answers her (a hidden [answered] tag, see answer_note): nonsense or a change of subject doesn't count.
On top of that, the code itself turns down "I don't know"-style dodges and keyboard mashing (is_dodge, looks_like_words).
Each question is only asked until it's answered. Deeper questions unlock at higher trust stages.
"""
import random, re, time
import trust
from directions import direction

# (the questions are the character's own: [quests] in their character.toml)
POINTS = 5
FIRST_AFTER = (30, 60)  # minutes open before the first quest (random in this range)
GAP = (30, 60)          # minutes between quests
PER_DAY = 2             # most quests that can be finished in a day
ANSWER_WITHIN = 30      # minutes the user has to answer

# A code check on top of her [answered] tag (the model is easily fooled by these two):
DODGES = re.compile(r"\bi\s+(?:really\s+|honestly\s+)?(?:do\s*n'?t|dont|do\s+not)\s+(?:really\s+)?know\b|\bidk\b|\bdunno\b|"
                    r"\bno\s+(?:idea|clue)\b|\b(?:i'?m\s+|im\s+)?not\s+(?:really\s+|too\s+)?sure\b|\bcan'?t\s+say\b|"
                    r"\bbeats\s+me\b|\bwho\s+knows\b|\b(?:what|how)\s+about\s+you\b|\byou\s+tell\s+me\b|\band\s+you\b|"
                    r"\bnever\s+thought\s+about\s+(?:it|that)\b", re.I)
FILLER = set("i you it that this the a an um uh hmm well so yeah yes no nah oh ok okay really honestly haha lol "
             "actually just like but and or maybe what about how do does".split())
CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxz]{4,}")  # "qwfh", "hdff": keyboard mashing (y counts as a vowel)

def is_dodge(message):
    """'I don't know, what about you?': a dodge phrase, and hardly anything else (fewer than 2 words that say something).
    'Not sure, but it rains almost every day' still counts as an answer."""
    if not DODGES.search(message):
        return False
    rest = [w for w in re.findall(r"[a-z']+", DODGES.sub(" ", message.lower().replace("’", "'"))) if w not in FILLER]
    return len(rest) < 2

def looks_like_words(message):
    """False for keyboard mashing like 'ajsdasdad oafhoiqwfhef burgersssss': too many words that can't be real
    (a letter 3 times in a row, 4 consonants in a row, or no vowel at all)."""
    words = re.findall(r"[a-z]+", message.lower())
    odd = [w for w in words if re.search(r"(.)\1\1", w) or CONSONANT_RUN.search(w) or not re.search(r"[aeiouy]", w)]
    return bool(words) and len(odd) / len(words) < 0.4

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

    def answer_note(self):
        """While the character waits on a quest: a hidden note for the user's next message (pet.ask's note), asking
        them to judge, in the same reply, whether it really answers their question. Else None."""
        if not self.pending:
            return None
        topic = self.topic(self.pending[0])
        return self.character.fill(
            "(Not part of the user's message: {name} had just asked the user about ") + topic + self.character.fill(
            ". {They} replies as usual. Then, after {their} other tags, {they} judges strictly whether this message "
            "tells {them} something about that, and adds one more tag: [answered] only if it gives at least part of "
            "an answer about ") + topic + self.character.fill(
            ". [not answered] if it's about something else, asks {them} the question back, says they don't know, "
            "or is nonsense. A friendly message on another subject is still [not answered].)")

    def answered(self, save, message, feeling, judged=None):
        """Call with each user message. Returns the quest id if it finished the quest the character was waiting on,
        else None. judged = the character's own [answered] tag for this message (pet.ask): only True counts,
        so a reply she judged a non-answer (or forgot to judge) never finishes a quest."""
        if not self.pending:
            return None
        quest_id, asked = self.pending
        self.pending = None  # one chance: a non-answer drops it (she can ask again another time)
        if (judged is not True or time.time() - asked > ANSWER_WITHIN * 60 or feeling == "rude"
                or len(re.findall(r"\w+", message)) < 4 or is_dodge(message) or not looks_like_words(message)):
            return None
        save["today"]["quests"] = save["today"].get("quests", 0) + 1
        trust.quest_done(save, quest_id, POINTS)
        return quest_id

    def topic(self, quest_id):
        """What a world quest asked about, like "whether it rains a lot in the user's world, ..."."""
        return next(t for q, _, t in self.character.quests if "world-" + q == quest_id)
