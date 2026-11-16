"""The judge: how your message felt, and whether it finished a quest, asked in a short call of its own.

A character also writes these as hidden tags in her reply ([nice], [done]...), but a small model judges badly while
it's busy being someone: Gemma tagged the character's own mood instead of your message (a kind "I'm so sorry" came
out [rude] on a day she was hurt, and 1 kind message in 12 [nice]), and dropped the [done] tag on a real answer.
Asked alone, with no persona, and with the answer held to one of a few words by a grammar, the same model got 16 of
16 kind messages and 20 of 20 real answers. So the judge's answer is used, and her own tag only if the judge can't
be reached.

The judge reads her line just before your message too: an answer like "yea I can" means nothing alone.

The judge has its own slot on the server (the one after the characters'), so her prompt stays read in. It is loose
with "yes" on a non-answer ("that sounds lonely"), so the checks in quests.py and story.py (answer_words, dodges,
mashing) still decide with it.
"""
import requests
from engine import llm

FEELINGS = ("nice", "neutral", "rude")

SAID_LETTERS = 400  # of her last line, for the judge (its slot only has JUDGE_CTX)

def _said(character, said):
    """Her last line, as the judge reads it before your message: an answer often only makes sense next to it
    ("yea I can" was judged blind). "" if she hasn't said anything yet."""
    said = " ".join((said or "").split())
    if not said:
        return ""
    if len(said) > SAID_LETTERS:
        said = "…" + said[-SAID_LETTERS:]  # (the end: what she asked is usually there)
    return character.fill("{name} had just said:\n\n") + f'"{said}"\n\n'

def feeling(character, message, slot, said=None):
    """How this message treats her: "nice", "neutral" or "rude". None if the judge couldn't be asked.
    said = her line just before your message."""
    before = _said(character, said)
    question = character.fill(
        "{name} is a character who is chatting with the user. " + before
        + ("Then the user sent {them} this message:\n\n" if before else "The user just sent {them} this message:\n\n")
        + f'"{message}"\n\n'
        "How does the message treat {name}?\n"
        "nice = warm toward {them}: kind, caring, thankful, a compliment, a promise, or comforting {them}\n"
        "rude = insulting, mean or hurtful toward {them}\n"
        "neutral = anything else, including plain questions and small talk\n"
        # ("stop reporting on her, protect Pip" was called rude, for being an order, and so was "wait, what?")
        "Advice or telling {them} what to do, a plain \"no\", disagreeing, and a surprised or worried question are "
        "not rude: they are neutral, or nice if they are meant kindly. Only what the message says to {name} about "
        "{them}self counts: something unkind about another person (\"tell them she's boring\") is not rude to {name}.\n"
        + ("Read the message as the user's answer to what {name} had just said, but judge only the user's message, "
           "not how {name} feels today." if before else "Judge only the user's message, not how {name} feels today."))
    felt = _ask("You label how a chat message feels to the one it was sent to. Answer with one word.",
                question, FEELINGS, slot)
    if felt == "rude" and not _at_her(character, message, before, slot):
        return "neutral"
    return felt

def _at_her(character, message, before, slot):
    """Whether a message judged rude is unkind to her, not to someone else. Asked apart, since the line in the
    question wasn't enough: "tell them she's boring" (about Vesper's sister) and "he sounds like a jerk" (about a
    boy who teases children) were rude every time, with or without her line before them. True if unsure."""
    other = "someone else"
    question = character.fill(
        before + 'The user sent {name} this message:\n\n' + f'"{message}"\n\n'
        "Who is the unkind part of the message about? Answer {name} if it insults, mocks or hurts {name} {them}self, "
        f'or "{other}" if it is about another person (someone {{name}} talked about, or anyone else).')
    who = _ask("You find out who a chat message is unkind to. Answer with one of the words given.", question,
               (character.name, other), slot)
    return who != other

def done(character, asked, counts, message, slot, said=None):
    """Whether this message does what she asked. asked = what she brought up ("she asked the user about..."),
    counts = what a real answer is, said = her line just before your message. True, False, or None if the judge
    couldn't be asked."""
    asked = character.fill(asked)
    question = (character.fill("{name} is a character chatting with the user. ") + asked[0].upper() + asked[1:].rstrip(".")
                + ".\n\n" + _said(character, said)
                + f'The user then sent this message:\n\n"{message}"\n\n'
                + f"Answer yes only if {character.fill(counts)}. A real try counts, even a short or silly one.\n"
                "Answer no if the message asks a question back, changes the subject, brushes it off, or is only a "
                'reaction like "hmm" or "wow", or only agrees ("yes", "yea I can", "sure") without saying the '
                "answer itself.")
    answer = _ask("You check whether a chat message does what was asked. Answer yes or no.", question, ("yes", "no"), slot)
    return None if answer is None else answer == "yes"

def _ask(system, question, words, slot):
    try:
        answer = llm.pick([{"role": "system", "content": system}, {"role": "user", "content": question}], words, slot)
    except (llm.ServerGone, requests.RequestException, KeyError, ValueError):
        return None  # her own tag will have to do (the server is restarted by her next reply, if it's gone)
    return answer if answer in words else None
