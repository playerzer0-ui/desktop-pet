"""Quests. Minor ones: now and then she asks about your world; answer her well and she trusts you more.
Major ones (MajorQuests): one per stage 1-4, a gate trust can't pass until it's done.
She judges your answer herself with a hidden tag, and the code also turns down dodges and keyboard mashing.
"""
import random, re, time
from progress import trust
from mind.directions import direction

POINTS = 5
FIRST_AFTER = (30, 60)  # minutes open before the first quest
GAP = (30, 60)          # minutes between quests
PER_DAY = 2
ANSWER_WITHIN = 30      # minutes

# checked by code on top of her [answered] tag (the model is easily fooled by these)
DODGES = re.compile(r"\bi\s+(?:really\s+|honestly\s+)?(?:do\s*n'?t|dont|do\s+not)\s+(?:really\s+)?know\b|\bidk\b|\bdunno\b|"
                    r"\bno\s+(?:idea|clue)\b|\b(?:i'?m\s+|im\s+)?not\s+(?:really\s+|too\s+)?sure\b|\bcan'?t\s+say\b|"
                    r"\bbeats\s+me\b|\bwho\s+knows\b|\b(?:what|how)\s+about\s+you\b|\byou\s+tell\s+me\b|\band\s+you\b|"
                    r"\bnever\s+thought\s+about\s+(?:it|that)\b", re.I)
FILLER = set("i you it that this the a an um uh hmm well so yeah yes no nah oh ok okay really honestly haha lol "
             "actually just like but and or maybe what about how do does".split())
CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxz]{4,}")  # keyboard mashing

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

    def due(self, save):
        """A stage direction for her question if it's time for one, else None."""
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
        """While she waits: a hidden note asking her to judge your next message with [answered]. Else None."""
        if not self.pending:
            return None
        topic = self.topic(self.pending[0])
        return self.character.fill(
            "(Not part of the user's message: {name} had just asked the user about ") + topic + self.character.fill(
            ". {They} replies as usual. Then, at the very end of {their} reply, {they} judges strictly whether this message "
            "tells {them} something about that, and adds one more tag: [answered] only if it gives at least part of "
            "an answer about ") + topic + self.character.fill(
            ". [not answered] if it's about something else, asks {them} the question back, says they don't know, "
            "or is nonsense. A friendly message on another subject is still [not answered].)")

    def answered(self, save, message, feeling, judged=None):
        """The quest id if this message finished it, else None. judged = her own tag: only True counts."""
        if not self.pending:
            return None
        quest_id, asked = self.pending
        self.pending = None  # one chance: she can ask again another time
        if (judged is not True or time.time() - asked > ANSWER_WITHIN * 60 or feeling == "rude"
                or len(re.findall(r"\w+", message)) < 4 or is_dodge(message) or not looks_like_words(message) or mentions_tags(message)):
            return None
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
        """While she's listening: a hidden note asking her to judge your message with [done]. Else None."""
        quest = self._moment(save)
        if not quest or self.listening <= 0:
            return None
        self.listening -= 1
        extra = self.character.fill(quest["note"]) + "\n\n" if quest.get("note") else ""
        return extra + self.character.fill(
            "(Not part of the user's message: {name} had just brought up something important to {them}: ") + \
            quest["starts"] + self.character.fill(
            ". {They} replies as usual. Then, at the very end of {their} reply, {they} judges whether it's done, and adds one "
            "more tag: [done] only if ") + quest["done_when"] + self.character.fill(
            ". [not yet] if the user changes the subject, brushes it off, or doesn't really respond to it.)")

    def finished(self, save, message, feeling, judged):
        """The quest if this message finished it, else None. Needs her [done], and a nice message for a quest
        with needs_nice (a harsh reply sometimes still got [done]). Never rude, a dodge or mashing."""
        quest = self._moment(save)
        unkind = feeling == "rude" or (quest and quest["needs_nice"] and feeling != "nice")
        if (not quest or judged is not True or unkind or len(re.findall(r"\w+", message)) < 2
                or is_dodge(message) or not looks_like_words(message) or mentions_tags(message)):
            return None
        if quest.get("answer_words") and not re.search(quest["answer_words"], message, re.I):
            return None  # (a friendly message about something else sometimes got [done])
        self.listening = 0
        trust.quest_done(save, "major-" + quest["id"], quest["points"])
        return quest
