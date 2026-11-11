"""A character's long-term memory of you, in her save under "memories". Kinds:
    world      your answers to her "curious about your world" questions
    milestone  her major quests and story moments
    note       her diary, written by the model when you say goodbye

Diary notes have three tiers, so her prompt stays the same size however long she knows you:
    lasting  facts that stay true (your name, pets, job): always in her prompt, at most LASTING
    recent   the newest RECENT notes: always in her prompt
    archive  older notes: brought back by recall() when your message mentions one
Memories go after the cached part of her prompt, so new ones never force the slow re-read.
"""
import datetime, re
from engine import llm
from engine.character import cast
from mind.directions import is_direction

MAX_NOTES = 5000      # plain diary notes kept (then the oldest is forgotten)
LASTING = 15          # lasting facts in her prompt
RECENT = 10           # newest plain notes in her prompt
RECALL = 3            # old notes one message can bring back
NOTES_PER_SITTING = 8
MIN_MESSAGES = 3      # messages you need to send before she writes in her diary
STOP_WORDS = set("the a an and or of to in on at for with is are was were be been their they them user users "
                 "who that this it its as by from has have had about when while s".split())

# too common to bring a memory back on their own
COMMON = set("you your yours i me my mine we our us he she his her him not but so can could would should will just "
             "really very much more most some any all what how why where which there here then than too also yes no "
             "today yesterday tomorrow now day days time week like good bad nice well know think want going get got "
             "said say tell told thing things lot little been being did does doing done make made one two".split())

def remember(save, kind, text, lasting=False):
    entry = {"when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": kind, "text": text}
    save["memories"] = save.get("memories", []) + [entry]
    if lasting:
        make_lasting(save, entry)
    notes = [m for m in save["memories"] if m["kind"] == "note" and not m.get("lasting")]
    if len(notes) > MAX_NOTES:
        save["memories"].remove(notes[0])
    return entry

def make_lasting(save, entry):
    """Mark a note lasting. Past LASTING, the one marked longest ago becomes a plain note again."""
    entry["lasting"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    marked = [m for m in save["memories"] if m.get("lasting")]
    if len(marked) > LASTING:
        del min(marked, key=lambda m: str(m["lasting"]))["lasting"]

def archive(save):
    """Plain notes older than the newest RECENT: not in her prompt."""
    plain = [m for m in save.get("memories", []) if m["kind"] == "note" and not m.get("lasting")]
    return plain[:-RECENT] if len(plain) > RECENT else []

def in_prompt(save):
    old = {id(m) for m in archive(save)}
    return [m for m in save.get("memories", []) if id(m) not in old]

def _keywords(text):
    """Word starts (5 letters, so "adopted" ~ "adopt"), without common words."""
    words = re.findall(r"[a-z0-9]+", re.sub(r"'s\b", "", text.lower()))
    return {w[:5] for w in words if len(w) >= 3 and w not in STOP_WORDS and w not in COMMON}

def recall(save, text, limit=RECALL):
    """Archived notes that text mentions, best first (most shared words, then newest). No model call."""
    said = _keywords(text)
    if not said:
        return []
    scored = []
    for i, m in enumerate(archive(save)):
        shared = len(said & _keywords(m["text"]))
        if shared:
            scored.append((shared, i, m))
    return [m for _, _, m in sorted(scored, key=lambda x: (x[0], x[1]), reverse=True)[:limit]]

RECALLED = ("(Not part of the user's message: what the user just said reminds {name} of these older memories from "
            "earlier visits. Right now it is {now}. {They} can bring them up if they fit, the way a friend suddenly "
            "remembers, and never mentions notes or a diary.)\n")

def recall_note(found, character):
    now = datetime.datetime.now()
    return (character.fill(RECALLED).replace("{now}", now.strftime("%A %Y-%m-%d %H:%M"))
            + "\n".join(f"- {ago(m['when'], now)} ({m['when']}): {m['text']}" for m in found))

def remember_answer(save, topic, answer, character):
    answer = answer.strip()[:200]
    return remember(save, "world", f'{character.name} asked about {topic}. The user said: "{answer}"')

MEMORIES = ("(Not a message from the user: these are {name}'s memories from {their} earlier visits, oldest first, "
            "with when each happened. Right now it is {now}. "
            "When two memories disagree, the newer one is what's true now. "
            "{They} remembers these the way a friend does: {they} brings one up naturally when it fits, and never "
            "mentions notes, lists or a diary. If the user asks whether or when {they} remembers something, or what "
            "{they} knows about them, {they} answers warmly in {their} own words from these memories, and can say "
            "roughly when it happened (like \"three days ago\"). If a detail isn't here, {they} admits {they} doesn't "
            "remember that part and shares what {they} does remember. {They} never claims {they} can't remember "
            "anything or that {they} has never talked with the user. Older memories can come back to {them} during the "
            "chat, when something the user says reminds {them}.)\n")

TODAY = ("(Not a message from the user: right now it is {now}. Days in {name}'s world fall on the same calendar "
         "dates as the user's, so {they} knows what day it is back home too.)")

def as_message(save, character):
    """Her memories as one message for her prompt. With none yet, just today's date (dated lore needs it)."""
    memories = in_prompt(save)
    now = datetime.datetime.now()
    if not memories:
        return {"role": "user", "content": character.fill(TODAY).replace("{now}", now.strftime("%A %Y-%m-%d %H:%M"))}
    lines = [f"- {ago(m['when'], now)} ({m['when']}): {m['text']}" for m in memories]
    intro = character.fill(MEMORIES).replace("{now}", now.strftime("%A %Y-%m-%d %H:%M"))
    return {"role": "user", "content": intro + "\n".join(lines)}

def ago(when, now):
    days = (now.date() - datetime.datetime.strptime(when, "%Y-%m-%d %H:%M").date()).days
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"

DIARY = """You keep a diary for {name}, {about}.
The user is the human on the other side of the screen. The user is never {name}, and never {others}: they are
characters from {name}'s world, not people in the user's life, so never write a note about them.
Read what the user said and write up to 8 short notes about NEW things the USER said about themselves that {name}
would want to remember next time: their name, people and pets in their life (with names), events and dates,
what they like or dislike, how they were feeling and why, plans or promises. Most important first.
Rules:
- Each note is one short sentence on its own line, starting with "- ": one person or thing, and what the
  user said about it (a made-up example of the style, never write it: "{example1}").
- Put "(lasting)" right after "- " on a note that will stay true for months: the user's name, their family,
  partner, friends and pets (with names), where they live, their job or school, lasting likes and dislikes, their
  health (a made-up example, never write it: "- (lasting) {example3}"). Plans, events, feelings and news are never
  lasting, and most notes aren't.
- Keep names of people, pets and places exactly as the user wrote them.
- Only write what the user actually said. Never add details, reasons or guesses of your own.
- Don't guess anyone's gender: use their name, or "the user" / "they", unless the user said "he" or "she".
- Turn relative dates into real ones using today's date (for example "this Friday" becomes "Friday 2026-10-23").
- Only facts from the user's own lines. A "({name} had said: ...)" line is only there to explain a short reply.
- Updates matter most: if something in "Already remembered" changed (an exam happened, a plan is done, someone
  made a decision), write the new version (a made-up example, never write it: "{example2}").
- Otherwise skip anything already in "Already remembered".
- Never write anything the user didn't say this time. Most sittings have nothing new: then write NONE.
- Don't write about {name} or {their} world, about {name}'s memory, about the conversation itself (like what the user
  asked or tried to recall), or small talk.
If nothing new is worth remembering, write only: NONE"""

EXAMPLES = ["The user's friend NR complains that everyone at their university uses AI.",  # (never kept: heard_it)
            "The user finished their exam and thinks they did well.",
            "The user's older sister Mei lives in Busan."]
LASTING_MARK = re.compile(r"^(?:[(\[]\s*lasting\s*[)\]]|lasting\s*:)\s*", re.I)
CALENDAR = set("monday tuesday wednesday thursday friday saturday sunday january february march april may june july "
               "august september october november december".split())

def heard_it(note, heard):
    """True if a note comes from what the user said. The model sometimes invents one, even copying DIARY's
    examples, so a note must not be an example, must share a third of its words with what was said, and every
    name in it must have been said."""
    if any(same_fact(note, example) for example in EXAMPLES):
        return False
    stem = lambda w: w[:5]
    said = {stem(w) for w in re.findall(r"[a-z0-9]+", heard.lower())}
    words = [w for w in re.findall(r"[a-z0-9]+", note.lower()) if w not in STOP_WORDS]
    if words and sum(stem(w) in said for w in words) / len(words) < 1 / 3:
        return False
    names = [w for w in re.findall(r"[A-Za-z][\w'-]*", note)[1:] if w[0].isupper() and w.lower() not in CALENDAR]
    return all(re.sub(r"'s$", "", n).lower() in heard.lower() for n in names)

def write_diary(save, messages, start, character, slot=0):
    """At goodbye: the model writes notes about the user from messages[start:]. Returns the new ones."""
    lines = []
    # only the user's words, so her guesses can't become facts. A short reply ("yes!") keeps the question
    # she had just asked, for context: only the question, or her own news became notes about the user.
    they_said = ""
    for m in messages[start:]:
        if m["role"] == "assistant":
            words = re.sub(r"\*[^*]*\*", "", re.sub(r"\s*\[(nice|neutral|rude|mood:\s*\w+)\]", "", m["content"]))
            they_said = " ".join(q.strip() for q in re.findall(r"[^.!?…]*\?", words))
        elif not is_direction(m["content"]):
            if len(m["content"].split()) < 6 and they_said:
                lines.append(f"({character.name} had said: {they_said})")
            lines.append("User: " + m["content"])
    if sum(line.startswith("User: ") for line in lines) < MIN_MESSAGES:
        return []
    heard = "\n".join(lines)
    # what she already knows, plus old notes this sitting mentions (so a change to one is written as an update)
    shown = [m["text"] for m in in_prompt(save) + recall(save, heard, limit=10)]
    day = datetime.date.today()
    today = day.strftime("%A %Y-%m-%d") + ". The next 7 days are " + ", ".join(
        (day + datetime.timedelta(days=n)).strftime("%A %Y-%m-%d") for n in range(1, 8))  # (it got "Friday" wrong)
    everyone = cast()
    world = world_names(character)
    user_lines = "\n".join(line for line in lines if line.startswith("User: "))
    own = {character.name, character.folder.capitalize()}
    others = sorted(everyone - own) or ["anyone else from " + character.fill("{their}") + " world"]
    prompt = character.fill(DIARY).replace("{about}", character.about).replace("{others}", " or ".join(others))
    prompt = prompt.replace("{example1}", EXAMPLES[0]).replace("{example2}", EXAMPLES[1]).replace("{example3}", EXAMPLES[2])
    text = llm.chat([{"role": "system", "content": prompt},
                     {"role": "user", "content": f"Today is {today}.\n\nAlready remembered:\n"
                                                 + ("\n".join("- " + k for k in shown) or "(nothing yet)")
                                                 + "\n\nWhat the user said this time:\n" + "\n".join(lines[-80:])}],
                    slot=slot, max_tokens=250, temperature=0.3)
    notes = [re.sub(r"^(?:-\s*)+", "", line.strip()).strip() for line in text.splitlines() if line.strip().startswith("-")]
    new = []
    for note in notes[:NOTES_PER_SITTING]:
        lasting = bool(LASTING_MARK.match(note))
        note = LASTING_MARK.sub("", note)
        if (not note or "NONE" in note or not heard_it(note, heard) or names_a_character(note, everyone)
                or from_her_world(note, user_lines, world)):
            continue
        lasting = lasting and not PASSING.search(note)  # ("The user is resting" was marked lasting)
        repeats = [m for m in save.get("memories", []) if same_fact(note, m["text"])]
        if not repeats:
            new.append(remember(save, "note", note, lasting))
        elif lasting and repeats[-1]["kind"] == "note" and not repeats[-1].get("lasting"):
            make_lasting(save, repeats[-1])  # something she knew turns out to last
    return new

# something passing is never a lasting fact, whatever the diary marked
PASSING = re.compile(r"\b(?:today|tonight|yesterday|tomorrow|this (?:morning|afternoon|evening|week|weekend)|next \w+|"
                     r"right now|currently|is (?:resting|tired|nervous|sad|happy|busy|sick|bored|excited)|"
                     r"feel(?:s|ing)?|felt|\d{4}-\d\d-\d\d)\b", re.I)

def world_names(character):
    """Capitalised names from her own files (places, factions, people), lowercase."""
    text = " ".join(character.text(f) for f in ("lore.md", "persona.md", "events.md"))
    return {w.lower() for w in re.findall(r"\b[A-Z][a-z]+\b", text)} - CALENDAR

def from_her_world(note, user_lines, world):
    """True if a note names something from her world (like "the Republic") that the user didn't say."""
    names = [w.lower() for w in re.findall(r"[A-Za-z][\w'-]*", note)[1:] if w[0].isupper()]
    said = user_lines.lower()
    return any(re.sub(r"'s$", "", n) in world and not re.search(rf"\b{re.escape(re.sub(chr(39) + 's$', '', n))}", said)
               for n in names)

def names_a_character(note, everyone):
    """True if a note names a character: the model sometimes takes the user for one ("The user's friend Pip")."""
    return any(re.search(rf"\b{re.escape(name)}\b", note) for name in everyone)

def same_fact(a, b):
    """True if most of a's words are already in b (measured on a, so a bigger update isn't taken for a repeat)."""
    words = lambda text: set(re.findall(r"[a-z0-9]+", text.lower())) - STOP_WORDS
    wa, wb = words(a), words(b)
    return bool(wa) and len(wa & wb) / len(wa) >= 0.6
