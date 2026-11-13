"""How a character talks: her prompt (new_conversation), caching it (warm_up), and asking the model (ask)."""
import glob, hashlib, os, re
from engine import llm
from engine.config import N_CTX, MODEL, CACHE_DIR, FORGET_AT
from engine.save import load_save, stage_of
from engine.character import Character
from mind.lore import split as split_lore
from mind.sentences import ends

def trim_to_sentence(text):
    # a reply cut off at max_tokens, back to its last full sentence
    found = ends(text)
    return text[:found[-1]].rstrip() if found else text

def new_conversation(character=None, stage=None):
    """System prompt + example exchanges, for her trust stage (1-5; from her save if not given).
    What she isn't ready to share is left out entirely."""
    character = character or Character()
    if stage is None:
        stage = stage_of(load_save(character.save_path)["trust"])
    lore, details = split_lore(character.staged("lore.md", stage))
    system_prompt = character.staged("persona.md", stage) + "\n\n# Background lore\n"
    if details:
        system_prompt += character.fill("(Many topics here are in short. When one comes up, more of what {name} "
                                        "knows about it is added in a note.)\n")
    system_prompt += lore
    if stage < 5:
        system_prompt += character.fill("\n\n# Trust\n{name} happily talks about everything written above. {They} "
            "also knows more that isn't written here, but {they} isn't ready to share it yet. If asked about it, "
            "{they} gently changes the subject instead of making things up.")
    # at every stage: without it she invented cities ("Goldcrest", "Aethelgard")
    system_prompt += character.fill("\n\n# Never make things up\n{name} never invents names of people, places, gods, "
        "cities, family members or events that aren't written above, and never invents who taught {them} something. "
        "If asked something {they} doesn't know, {they} says so in {their} own words, or that {they} would rather "
        "not say, instead of guessing.\n{They} only remembers what the user has said in this chat and what's in "
        "{their} memories of earlier visits (if any are given). If the user asks whether {they} remembers "
        "something that isn't there, like a pet's name, {they} honestly says {they} doesn't remember it or that "
        "the user hasn't told {them} yet, and never pretends to remember.")
    system_prompt += character.fill(f"\n\n# Note\nThe first {len(character.examples)} exchanges in this chat are "
        "only examples of {name}'s style and length. They never really happened, so never say the user already "
        "said those things.")
    messages = [{"role": "system", "content": system_prompt}]
    for user, reply in character.examples:
        messages += [{"role": "user", "content": user}, {"role": "assistant", "content": reply}]
    return messages

def warm_up(messages, fixed, slot=0):
    """Have the server read her prompt before the first question. The first `fixed` messages (system prompt +
    examples) are read once (~20 s) and saved to cache/, then just loaded (~1 s). Anything after them (memories)
    is read on top each time. Returns ("loaded" or "read", prompt tokens)."""
    cached = prefix_of(messages[:fixed])
    everything = prefix_of(messages)

    name = hashlib.sha256(f"{os.path.basename(MODEL)} {N_CTX}\n{cached}".encode()).hexdigest()[:16] + ".bin"
    how = "read"
    if os.path.exists(os.path.join(CACHE_DIR, name)) and llm.restore_slot(name, slot):
        how = "loaded"
    else:  # (also when a llama-server update made an old cache file unreadable)
        llm.read(cached, slot)
        llm.save_slot(name, slot)
        # keep only the newest few (one per trust stage is all that's useful)
        for old in sorted(glob.glob(os.path.join(CACHE_DIR, "*.bin")), key=os.path.getmtime)[:-5]:
            os.remove(old)

    return how, llm.read(everything, slot)

def prefix_of(messages):
    """The exact text a request with these messages starts with, before the next question."""
    marker = "PIP_NEXT_QUESTION"
    full = llm.template(messages + [{"role": "user", "content": marker}])
    return full[:full.rindex("<|im_start|>", 0, full.index(marker))]

FEELING_TAG = re.compile(r"\s*\[(?:feeling:\s*)?(nice|neutral|rude)\]", re.I)  # (it sometimes adds "feeling:")
MOOD_TAG = re.compile(r"\s*\[mood:\s*([a-z]+)\]", re.I)
ANSWER_TAG = re.compile(r"\s*\[(?:\w+:\s*)?(not[ _]answered|unanswered|answered|not[ _]yet|done)\]", re.I)
    # (only asked for with a quest note: [answered] / [not answered], or [done] / [not yet] for a major quest)
YES_TAGS = {"answered", "done"}
LEFTOVER_TAGS = re.compile(r"(\s*\[\w+(?::\s*[\w ]+)?\])+\s*$")  # any other tag-like slip at the end, like [happy]
LEADING_TAGS = re.compile(r"^\s*(?:\[(?:\w+(?::\s*[\w ]+)?|not answered|not yet)\]\s*)*", re.I)  # [nice] [mood: happy]
def ask(messages, question, on_text=None, keep=1, moods=None, note=None, slot=0, on_mood=None):
    """Send a question, return (reply, timings, feeling, mood, answered). Adds both to messages.
    Her hidden tags: feeling (nice/neutral/rude), mood (one of `moods`, else None), answered (True/False/None).
    note = a hidden note for this request only. on_text streams her words, on_mood gets her mood first.
    keep = messages at the start that are never forgotten."""
    messages.append({"role": "user", "content": question})
    request = messages[:-1] + [{"role": "user", "content": f"{question}\n\n{note}"}] if note else messages

    chunks = llm.chat_stream(request, slot=slot, max_tokens=200,
                             temperature=0.7, top_p=0.8, top_k=20, min_p=0.05,
                             presence_penalty=0.3)  # Qwen's chat settings, but a light penalty: 1.5 pushed her to odd words

    reply = ""
    shown = 0  # how much of her words on_text has been given
    mood_told = False
    timings = {}
    finish_reason = None
    for chunk in chunks:
        timings = chunk.get("timings", timings)  # the last chunk has the server's stats
        if not chunk.get("choices"):
            continue
        finish_reason = chunk["choices"][0].get("finish_reason") or finish_reason
        text = chunk["choices"][0]["delta"].get("content") or ""
        if text:
            reply += text
            lead = LEADING_TAGS.match(reply).end()
            if on_mood and not mood_told:
                told = MOOD_TAG.search(reply[:lead])
                if told and (moods is None or told.group(1).lower() in moods):
                    mood_told = True
                    on_mood(told.group(1).lower())
            body = reply[lead:]
            if body.startswith("[") and "]" not in body:
                continue  # another tag still being written
            visible = body.split("[")[0]  # hold back a possible tag at the end
            if on_text and len(visible) > shown:
                on_text(visible[shown:])
                shown = len(visible)

    if finish_reason == "length":
        reply = trim_to_sentence(reply)

    tag = FEELING_TAG.search(reply)
    feeling = tag.group(1).lower() if tag else "neutral"
    mood_tag = MOOD_TAG.search(reply)
    mood = mood_tag.group(1).lower() if mood_tag else None
    if moods is not None and mood not in moods:
        mood = None
    answer_tag = ANSWER_TAG.search(reply)
    answered = (answer_tag.group(1).lower() in YES_TAGS) if answer_tag else None
    reply = LEFTOVER_TAGS.sub("", MOOD_TAG.sub("", FEELING_TAG.sub("", ANSWER_TAG.sub("", reply)))).rstrip()
    reply = LEADING_TAGS.sub("", reply)
    if on_text and len(reply) > shown:  # a "[" that wasn't a tag after all
        on_text(reply[shown:])

    # kept with her tags: seeing her own tags keeps her writing them
    messages.append({"role": "assistant", "content": f"[{feeling}] [mood: {mood or 'neutral'}] {reply}"})

    forget_oldest(messages, keep, context_used(timings))
    return reply.strip(), timings, feeling, mood, answered

def forget_oldest(messages, keep, used, full=FORGET_AT, down_to=0.5):
    """Over `full` of N_CTX: forget the oldest question+answer pairs (never the first `keep`) down to about
    `down_to`, in one cut, so only one reply pays for the re-read. Tokens are guessed from letter counts."""
    if used <= N_CTX * full:
        return 0
    letters = [len(m["content"]) for m in messages]
    target = sum(letters) * (N_CTX * down_to / used)
    total, dropped = sum(letters), 0
    while total > target and len(messages) > keep + 2:
        total -= len(messages.pop(keep)["content"]) + len(messages.pop(keep)["content"])
        dropped += 2
    return dropped

def context_used(timings):
    # cached + newly read + reply tokens
    return timings.get("cache_n", 0) + timings.get("prompt_n", 0) + timings.get("predicted_n", 0)
