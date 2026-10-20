"""Pip's long-term memory of you, kept in save.json under "memories". Each one has the date and time it was made.

Two kinds:
    world  your answers to her "curious about your world" questions (saved the moment you answer)
    note   her diary: when you close her, the model writes up to 8 short notes about you from that sitting

At launch, they're shown to her as one note placed AFTER the cached part of her prompt (see pet.warm_up),
so new memories never force the slow full re-read.
"""
import datetime, json, re, requests
from load import SERVER

MAX_NOTES = 30        # diary notes kept (oldest forgotten first); world answers are few, so all are kept
NOTES_PER_SITTING = 8
MIN_MESSAGES = 3      # how many messages you need to send in a sitting before she writes in her diary
STOP_WORDS = set("the a an and or of to in on at for with is are was were be been their they them user users "
                 "who that this it its as by from has have had about when while s".split())

def remember(save, kind, text):
    entry = {"when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": kind, "text": text}
    memories = save.setdefault("memories", []) + [entry]
    notes = [m for m in memories if m["kind"] == "note"]
    if len(notes) > MAX_NOTES:  # forget the oldest diary notes
        memories.remove(notes[0])
    save["memories"] = memories
    return entry

def remember_answer(save, topic, answer):
    answer = answer.strip()[:200]
    return remember(save, "world", f'Pip asked about {topic}. The user said: "{answer}"')

def as_message(save):
    """The memories as a chat message for her prompt, or None if she has none yet."""
    memories = save.get("memories", [])
    if not memories:
        return None
    now = datetime.datetime.now()
    lines = [f"- {ago(m['when'], now)} ({m['when']}): {m['text']}" for m in memories]
    return {"role": "user", "content":
            "(Not a message from the user: these are Pip's memories from her earlier visits, oldest first, "
            f"with when each happened. Right now it is {now.strftime('%A %Y-%m-%d %H:%M')}. "
            "When two memories disagree, the newer one is what's true now. "
            "She remembers these the way a friend does: she brings one up naturally when it fits, and never "
            "mentions notes, lists or a diary. If the user asks whether or when she remembers something, or what "
            "she knows about them, she answers warmly in her own words from these memories, and can say roughly "
            "when it happened (like \"three days ago\"). If a detail isn't here, she admits she doesn't remember "
            "that part and shares what she does remember. She never claims she can't remember anything or that "
            "she has never talked with the user.)\n" + "\n".join(lines)}

def ago(when, now):
    days = (now.date() - datetime.datetime.strptime(when, "%Y-%m-%d %H:%M").date()).days
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"

DIARY = """You keep a diary for Pip, a priestess who visits the user's desktop.
Read what the user said and write up to 8 short notes about NEW things the USER said about themselves that Pip
would want to remember next time: their name, people and pets in their life (with names), events and dates,
what they like or dislike, how they were feeling and why, plans or promises. Most important first.
Rules:
- Each note is one short sentence on its own line, starting with "- ": one person or thing, and what the
  user said about it (for example "The user's friend NR complains that everyone at their university uses AI.").
- Keep names of people, pets and places exactly as the user wrote them (for example "The user's friend NR ...").
- Only write what the user actually said. Never add details, reasons or guesses of your own.
- Don't guess anyone's gender: use their name, or "the user" / "they", unless the user said "he" or "she".
- Turn relative dates into real ones using today's date (for example "this Friday" becomes "Friday 2026-10-23").
- Only facts from the user's own lines. A "(Pip had said: ...)" line is only there to explain a short reply.
- Updates matter most: if something in "Already remembered" changed (an exam happened, a plan is done, someone
  made a decision), write the new version, for example "The user finished their exam and thinks they did well."
- Otherwise skip anything already in "Already remembered".
- Don't write about Pip or her world, about Pip's memory, about the conversation itself (like what the user
  asked or tried to recall), or small talk.
If nothing new is worth remembering, write only: NONE"""

def write_diary(save, messages, start):
    """At the end of a sitting: the model writes notes about the user from messages[start:]. Returns the new notes."""
    lines = []
    # only the user's own words, so Pip's guesses and recollections can't turn into "facts".
    # A very short reply ("yes!", "his name is Leo") keeps the Pip line before it, for context.
    pip_said = ""
    for m in messages[start:]:
        if m["role"] == "assistant":
            pip_said = re.sub(r"\s*\[(nice|neutral|rude|mood:\s*\w+)\]", "", m["content"])
        elif not m["content"].startswith("(No message from the user"):  # skip idle and quest stage directions
            if len(m["content"].split()) < 6 and pip_said:
                lines.append("(Pip had said: " + pip_said + ")")
            lines.append("User: " + m["content"])
    if sum(line.startswith("User: ") for line in lines) < MIN_MESSAGES:
        return []
    known = [m["text"] for m in save.get("memories", [])]
    today = datetime.date.today().strftime("%A %Y-%m-%d")
    response = requests.post(f"{SERVER}/v1/chat/completions", json={
        "messages": [{"role": "system", "content": DIARY},
                     {"role": "user", "content": f"Today is {today}.\n\nAlready remembered:\n"
                                                 + ("\n".join("- " + k for k in known[-25:]) or "(nothing yet)")
                                                 + "\n\nWhat the user said this time:\n" + "\n".join(lines[-40:])}],
        "max_tokens": 250, "temperature": 0.3,
        "chat_template_kwargs": {"enable_thinking": False},
    }).json()
    text = response["choices"][0]["message"]["content"]
    notes = [re.sub(r"^-\s*", "", line).strip() for line in text.splitlines() if line.strip().startswith("-")]
    new = []
    for note in notes[:NOTES_PER_SITTING]:
        if note and "NONE" not in note and not any(same_fact(note, k) for k in known):
            new.append(remember(save, "note", note))
            known.append(note)
    return new

def same_fact(a, b):
    """True if new note a mostly repeats old note b (most of a's words are already in b).
    A safety net for when the model repeats something she already remembers.
    (Measured on a, so an update that adds a lot, like "NR switched his major to art", isn't
    mistaken for the short "The user's best friend is NR".)"""
    words = lambda text: set(re.findall(r"[a-z0-9]+", text.lower())) - STOP_WORDS
    wa, wb = words(a), words(b)
    return bool(wa) and len(wa & wb) / len(wa) >= 0.6
