"""Quests. Minor ones: now and then she asks about your world; answer her well and she trusts you more.
Major ones (MajorQuests): one per stage 1-4, a gate trust can't pass until it's done.
The judge (mind/judge.py) decides whether you answered, and the code also turns down dodges and keyboard mashing.
"""
import random, re, time
from progress import trust
from mind.directions import direction

POINTS = 5
FIRST_AFTER = (30, 60)  # minutes open before the first quest
GAP = (30, 60)          # minutes between quests
PER_DAY = 2
ANSWER_WITHIN = 30      # minutes
TRIES = 4               # your messages she judges after asking: "what do you mean?" doesn't lose the quest

# checked by code on top of her [answered] tag (the model is easily fooled by these)
DODGES = re.compile(r"\bi\s+(?:really\s+|honestly\s+)?(?:do\s*n'?t|dont|do\s+not)\s+(?:really\s+)?know\b|\bidk\b|\bdunno\b|"
                    r"\bno\s+(?:idea|clue)\b|\b(?:i'?m\s+|im\s+)?not\s+(?:really\s+|too\s+)?sure\b|\bcan'?t\s+say\b|"
                    r"\bbeats\s+me\b|\bwho\s+knows\b|\b(?:what|how)\s+about\s+you\b|\byou\s+tell\s+me\b|\band\s+you\b|"
                    r"\bnever\s+thought\s+about\s+(?:it|that)\b", re.I)
FILLER = set("i you it that this the a an um uh hmm well so yeah yes no nah oh ok okay really honestly haha lol "
             "actually just like but and or maybe what about how do does".split())
CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxz]{4,}")  # keyboard mashing

# plainly kind words: with them a [neutral] message is nice enough for a quest that needs a nice one (felt_nice)
KIND = re.compile(r"\b(?:of course|welcome|always|any ?time|please do|promise|friends?|glad|love|care)\b", re.I)

def felt_nice(message, feeling):
    """For a quest or step with needs_nice: her [nice] tag, or [neutral] on plainly kind words. (Told "of course you
    can keep coming here to rest, you're always welcome", Pip answered "that is so kind of you" and still tagged it
    [neutral], 2 times in 5.) Rude never counts."""
    return feeling == "nice" or (feeling == "neutral" and bool(KIND.search(message)))

TAG_TALK = re.compile(r"\[\s*[a-z_:\s]*[a-z][a-z_:\s]*\]|\bsquare\s+brackets?\b", re.I)

def mentions_tags(message):
    """True for a message with tag-like text or about square brackets: trying to make her write [answered]."""
    return bool(TAG_TALK.search(message))

def is_dodge(message):
    """'I don't know, what about you?' with hardly anything else. 'Not sure, but it rains a lot' still counts."""
    if not DODGES.search(message):
        return False
    rest = [w for w in re.findall(r"[a-z']+", DODGES.sub(" ", message.lower().replace("’", "'"))) if w not in FILLER]
    return len(rest) < 2

def looks_like_words(message):
    """False for keyboard mashing: too many words with a letter 3 times running, 4 consonants, or no vowel."""
    words = re.findall(r"[a-z]+", message.lower())
    odd = [w for w in words if re.search(r"(.)\1\1", w) or CONSONANT_RUN.search(w) or not re.search(r"[aeiouy]", w)]
    return bool(words) and len(odd) / len(words) < 0.4

class Quests:
    def __init__(self, character):
        self.character = character
        self.next = time.time() + random.uniform(*FIRST_AFTER) * 60
        self.pending = None  # (quest id, time asked) while she waits for an answer
        self.tries = 0       # your messages since she asked

    def due(self, save):
        """A stage direction for her question if it's time for one, else None."""
        if self.pending or time.time() < self.next or save["today"].get("quests", 0) >= PER_DAY:
            return None
        unasked = [q for q in self.character.quests if q[1] <= trust.stage(save) and "world-" + q[0] not in save["quests_done"]]
        if not unasked:
            return None
        quest_id, _, topic = random.choice(unasked)
        self.pending = ("world-" + quest_id, time.time())
        self.tries = 0
        self.next = time.time() + random.uniform(*GAP) * 60
        return direction(self.character.fill("{name} has never seen the user's world and is curious about it. "
                                             "{They} asks the user about ") + f"{topic}.")

    def answer_note(self):
        """While she waits: a hidden note reminding her what she asked (the judge decides if it's answered). Else None."""
        if not self.pending:
            return None
        topic = self.topic(self.pending[0])
        return self.character.fill(
            "(Not part of the user's message: {name} had just asked the user about ") + topic + self.character.fill(
            # (waiting, Ruby asked her question again in the same words after every message)
            ". {They} answers what the user just said, in new words: {they} doesn't repeat {their} question word for "
            "word, and doesn't apologise for asking.)")

    def asking(self):
        """For the judge (mind/judge.py), while she waits: (what she asked, what counts as an answer)."""
        topic = self.topic(self.pending[0])
        return "{they} asked the user about " + topic, "the message tells {them} at least part of an answer about " + topic

    def answered(self, save, message, feeling, judged=None):
        """The quest id if this message finished it, else None. judged = her own tag: only True counts.
        She keeps waiting for TRIES of your messages (a question back, then the answer), then lets it go: she can
        ask again another time."""
        if not self.pending:
            return None
        quest_id, asked = self.pending
        self.tries += 1
        late = time.time() - asked > ANSWER_WITHIN * 60
        if (judged is not True or late or feeling == "rude"
                or len(re.findall(r"\w+", message)) < 4 or is_dodge(message) or not looks_like_words(message) or mentions_tags(message)):
            if late or self.tries >= TRIES:
                self.pending = None
            return None
        self.pending = None
        save["today"]["quests"] = save["today"].get("quests", 0) + 1
        trust.quest_done(save, quest_id, POINTS)
        return quest_id

    def topic(self, quest_id):
        return next(t for q, _, t in self.character.quests if "world-" + q == quest_id)

# --- major quests: the gates between trust stages ---

LISTEN_FOR = 6     # your messages she judges after bringing it up
QUIET_FIRST = 60   # seconds of quiet before she brings it up on her own

class MajorQuests:
    """When points reach the top of a stage, that stage's quest is active. She brings it up once a sitting,
    then judges your next few messages with [done] / [not yet]. The save only keeps quests_done."""

    def __init__(self, character):
        self.character = character
        self.raised = False         # she brought it up this sitting
        self.listening = 0          # messages she still judges

    def _moment(self, save):
        """The active quest if it's a single moment; one in steps is story.py's."""
        quest = self.active(save)
        return quest if quest and "steps" not in quest else None

    def active(self, save):
        return self.character.major_quests.get(trust.at_gate(save))

    def due(self, save):
        """Text for bringing the active quest up, once a sitting, else None."""
        quest = self._moment(save)
        if not quest or self.raised:
            return None
        self.raised, self.listening = True, LISTEN_FOR
        return self.character.fill("{name} has something important on {their} mind, and brings it up now, gently "
                                   "and in {their} own words: ") + quest["starts"] + "."

    def answer_note(self, save):
        """While she's listening: a hidden note reminding her what she brought up (the judge decides if it's done).
        Else None."""
        quest = self._moment(save)
        if not quest or self.listening <= 0:
            return None
        self.listening -= 1
        extra = self.character.fill(quest["note"]) + "\n\n" if quest.get("note") else ""
        return extra + self.character.fill(
            "(Not part of the user's message: {name} had just brought up something important to {them}: ") + \
            quest["starts"] + self.character.fill(
            ". {They} answers what the user just said, in new words: {they} doesn't repeat what {they} already said "
            "word for word, and doesn't apologise for bringing it up.)")

    def asking(self, save):
        """For the judge (mind/judge.py): (what she brought up, what counts as done)."""
        quest = self._moment(save)
        return quest["starts"], quest["done_when"]

    def finished(self, save, message, feeling, judged):
        """The quest if this message finished it, else None. Needs her [done], and a nice message for a quest
        with needs_nice (a harsh reply sometimes still got [done]). Never rude, a dodge or mashing."""
        quest = self._moment(save)
        unkind = feeling == "rude" or (quest and quest["needs_nice"] and not felt_nice(message, feeling))
        if (not quest or judged is not True or unkind or len(re.findall(r"\w+", message)) < 2
                or is_dodge(message) or not looks_like_words(message) or mentions_tags(message)):
            return None
        if quest.get("answer_words") and not re.search(quest["answer_words"], message, re.I):
            return None  # (a friendly message about something else sometimes got [done])
        self.listening = 0
        trust.quest_done(save, "major-" + quest["id"], quest["points"])
        return quest
