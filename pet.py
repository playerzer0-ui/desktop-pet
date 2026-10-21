import glob, hashlib, os, re
import llm
from config import N_CTX, MODEL, CACHE_DIR
from save import load_save, stage_of
from character import Character
from sentences import ends

def trim_to_sentence(text):
    # cut a reply that hit max_tokens back to its last full sentence (not one ending in "Mr." or "St.")
    found = ends(text)
    return text[:found[-1]].rstrip() if found else text

# How a character talks: their prompt, and asking the model. Who they are comes from their folder (character.py),
# so the desktop pet (main.py) and test_pip.py use the exact same character.

def new_conversation(character=None, stage=None):
    """The fixed start of a character's chat: system prompt + example exchanges (Pip if no character is given).
    stage 1-5 = how much they trust the user (from their save if not given).
    Lore and feelings they aren't ready to share are left out of the prompt entirely."""
    character = character or Character()
    if stage is None:
        stage = stage_of(load_save(character.save_path)["trust"])
    system_prompt = (character.staged("persona.md", stage)
        + "\n\n# Background lore\n" + character.staged("lore.md", stage))
    if stage < 5:
        system_prompt += character.fill("\n\n# Trust\n{name} happily talks about everything written above. {They} "
            "also knows more that isn't written here, but {they} isn't ready to share it yet. If asked about it, "
            "{they} gently changes the subject instead of making things up.")
    system_prompt += character.fill(f"\n\n# Note\nThe first {len(character.examples)} exchanges in this chat are "
        "only examples of {name}'s style and length. They never really happened, so never say the user already "
        "said those things.")
    messages = [{"role": "system", "content": system_prompt}]
    for user, reply in character.examples:  # (why examples, and how they're written: see character.toml)
        messages += [{"role": "user", "content": user}, {"role": "assistant", "content": reply}]
    return messages

def warm_up(messages, fixed):
    """Get the server to read the system prompt + examples (+ anything after them, like memories)
    before the first question. fixed = how many messages that fixed start is (len(new_conversation(...))).
    The system prompt + examples (the first `fixed` messages) are read once (~20 s on CPU) and saved to cache/.
    After that, they're just loaded from the file (~1 s). Editing persona or lore changes them,
    so they're read fresh once and saved under a new name. Anything after them (the character's memories,
    which change often) is read on top each time: only a few lines, so it's quick.
    Returns "loaded" or "read" (whether the cached part was loaded or had to be read)."""
    cached = prefix_of(messages[:fixed])  # the part that rarely changes
    everything = prefix_of(messages)

    name = hashlib.sha256(f"{os.path.basename(MODEL)} {N_CTX}\n{cached}".encode()).hexdigest()[:16] + ".bin"
    how = "read"
    if os.path.exists(os.path.join(CACHE_DIR, name)) and llm.restore_slot(name):
        how = "loaded"
    else:  # (also when a llama-server update made an old cache file unreadable: then just read it again)
        llm.read(cached)
        llm.save_slot(name)
        # keep only the newest few files (one per trust stage is all that's ever useful)
        for old in sorted(glob.glob(os.path.join(CACHE_DIR, "*.bin")), key=os.path.getmtime)[:-5]:
            os.remove(old)

    if everything != cached:  # read the memories on top of the cached part
        llm.read(everything)
    return how

def prefix_of(messages):
    """The exact text a request starts with when it holds these messages: everything before the next question."""
    marker = "PIP_NEXT_QUESTION"
    full = llm.template(messages + [{"role": "user", "content": marker}])
    return full[:full.rindex("<|im_start|>", 0, full.index(marker))]  # cut where the question's turn begins

FEELING_TAG = re.compile(r"\s*\[(?:feeling:\s*)?(nice|neutral|rude)\]", re.I)  # (the model sometimes adds "feeling:")
MOOD_TAG = re.compile(r"\s*\[mood:\s*([a-z]+)\]", re.I)
LEFTOVER_TAGS = re.compile(r"(\s*\[\w+(?::\s*\w+)?\])+\s*$")  # any other tag-like slip at the very end, like [happy]
def ask(messages, question, on_text=None, keep=1, moods=None):
    """Send a question, return (reply, timings, feeling, mood). Adds both to messages = memory.
    feeling = how the question felt to the character: "nice", "neutral" or "rude" (their hidden tag, see persona.md).
    mood = how they feel after replying (their second hidden tag): one of `moods` (Character.moods; any word if
    None), or None if they left it out or used a mood that isn't on the list.
    on_text(text) is called with each new piece of the reply as it streams in (without the tag).
    keep = how many messages at the start are never forgotten (system prompt + examples, + memories if any)."""
    messages.append({"role": "user", "content": question})

    chunks = llm.chat_stream(messages, max_tokens=200,
                             temperature=0.7, top_p=0.8, top_k=20, presence_penalty=1.5)  # Qwen's recommended chat settings

    reply = ""
    shown = 0  # how much of the reply on_text has been given
    timings = {}
    finish_reason = None
    for chunk in chunks:
        timings = chunk.get("timings", timings)  # the last chunk carries the server's timing stats
        if not chunk.get("choices"):
            continue
        finish_reason = chunk["choices"][0].get("finish_reason") or finish_reason
        text = chunk["choices"][0]["delta"].get("content") or ""
        if text:
            reply += text
            visible = reply.split("[")[0]  # hold back anything from "[" on: it's probably the feeling tag
            if on_text and len(visible) > shown:
                on_text(visible[shown:])
                shown = len(visible)

    # hit max_tokens mid-sentence: keep only the finished sentences in memory
    if finish_reason == "length":
        reply = trim_to_sentence(reply)

    tag = FEELING_TAG.search(reply)
    feeling = tag.group(1).lower() if tag else "neutral"
    mood_tag = MOOD_TAG.search(reply)
    mood = mood_tag.group(1).lower() if mood_tag else None
    if moods is not None and mood not in moods:
        mood = None
    reply = LEFTOVER_TAGS.sub("", MOOD_TAG.sub("", FEELING_TAG.sub("", reply))).rstrip()
    if on_text and len(reply) > shown:  # a "[" that wasn't a tag after all: show the rest now
        on_text(reply[shown:])

    # remember the model's own answer, tag included: seeing their own tags keeps them adding them
    messages.append({"role": "assistant", "content": f"{reply} [{feeling}] [mood: {mood or 'neutral'}]"})

    # forget the oldest chat lines when context gets too full (the first `keep` messages stay)
    if context_used(timings) > N_CTX * 0.75 and len(messages) > keep + 2:
        messages.pop(keep)  # oldest question
        messages.pop(keep)  # and its answer

    return reply.strip(), timings, feeling, mood

def context_used(timings):
    # how full the context is = cached tokens + newly read tokens + reply tokens
    return timings.get("cache_n", 0) + timings.get("prompt_n", 0) + timings.get("predicted_n", 0)
