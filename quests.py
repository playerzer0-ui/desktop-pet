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

# --- major quests: the gates between trust stages ---

LISTEN_FOR = 6     # your messages she keeps judging after she brings it up; then it waits for the next sitting
QUIET_FIRST = 60   # seconds of quiet before she brings it up on her own (so it never cuts into a chat)

class MajorQuests:
    """A character's major quests ([major_quests] in their character.toml): one per stage 1-4, each a gate.
    When your points reach the top of a stage they stop (trust.at_gate) and that stage's quest is the active one.
    She brings it up once a sitting (in her greeting, or on her own after a quiet minute), then judges your next
    few messages with a hidden [done] / [not yet] tag. Once it's done, its points open the next stage.
    Nothing about it is kept in the save but quests_done: whether one is active comes from the points."""

    def __init__(self, character):
        self.character = character  # (character.py) whose quests, name and pronouns
        self.raised = False         # she brought it up this sitting
        self.listening = 0          # how many more of your messages she judges it on

    def _moment(self, save):
        """The active quest if it's a single moment (starts / done_when); a story in steps is story.py's to play."""
        quest = self.active(save)
        return quest if quest and "steps" not in quest else None

    def active(self, save):
        """The major quest holding trust back right now ({id, starts, done_when, memory, points}), or None."""
        return self.character.major_quests.get(trust.at_gate(save))

    def due(self, save):
        """What she says to bring the active quest up, if she hasn't yet this sitting (text for a stage direction,
        to go in her greeting or a nudge), else None. Marks it raised."""
        quest = self._moment(save)
        if not quest or self.raised:
            return None
        self.raised, self.listening = True, LISTEN_FOR
        return self.character.fill("{name} has something important on {their} mind, and brings it up now, gently "
                                   "and in {their} own words: ") + quest["starts"] + "."

    def answer_note(self, save):
        """While she's waiting on it: a hidden note for your next message (pet.ask's note), asking her to judge,
        in the same reply, whether it's done. Else None. Each note uses up one of her LISTEN_FOR messages."""
        quest = self._moment(save)
        if not quest or self.listening <= 0:
            return None
        self.listening -= 1
        return self.character.fill(
            "(Not part of the user's message: {name} had just brought up something important to {them}: ") + \
            quest["starts"] + self.character.fill(
            ". {They} replies as usual. Then, after {their} other tags, {they} judges whether it's done, and adds one "
            "more tag: [done] only if ") + quest["done_when"] + self.character.fill(
            ". [not yet] if the user changes the subject, brushes it off, or doesn't really respond to it.)")

    def finished(self, save, message, feeling, judged):
        """Call after her reply to a message she judged (answer_note). Returns the quest if that finished it, else
        None. It takes her own [done], and for a quest about being kind to her (needs_nice in character.toml) a
        message that felt nice to her too: a harsh "praying is pointless" sometimes still got [done]. Never a rude
        message, a dodge or keyboard mashing."""
        quest = self._moment(save)
        unkind = feeling == "rude" or (quest and quest["needs_nice"] and feeling != "nice")
        if (not quest or judged is not True or unkind or len(re.findall(r"\w+", message)) < 2
                or is_dodge(message) or not looks_like_words(message)):
            return None
        self.listening = 0
        trust.quest_done(save, "major-" + quest["id"], quest["points"])  # (done first, so the gate opens for them)
        return quest
