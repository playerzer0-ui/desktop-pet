import glob, hashlib, json, os, re, requests
from load import load, for_stage, SERVER, N_CTX, MODEL, CACHE_DIR
from save import load_save, stage_of

def trim_to_sentence(text):
    # cut a reply that hit max_tokens back to its last full sentence (. ! ? … plus any closing quote/asterisk)
    ends = list(re.finditer(r'[.!?…]["\'*)]*(?=\s|$)', text))
    return text[:ends[-1].end()] if ends else text

# Everything that defines how Pip talks lives here, so the desktop pet (main.py), the terminal (desktop_cli.py) and test_pip.py use the exact same Pip.

def new_conversation(stage=None):
    """stage 1-5 = how much Pip trusts the user (from save.json if not given).
    Lore and feelings she isn't ready to share are left out of the prompt entirely."""
    if stage is None:
        stage = stage_of(load_save()["trust"])
    system_prompt = (for_stage(load("character/pip/persona.md"), stage)
        + "\n\n# Background lore\n" + for_stage(load("character/pip/lore.md"), stage))
    if stage < 5:
        system_prompt += ("\n\n# Trust\nPip happily talks about everything written above. She also knows more "
            "that isn't written here, but she isn't ready to share it yet. If asked about it, she gently "
            "changes the subject instead of making things up.")
    system_prompt += ("\n\n# Note\nThe first 5 exchanges in this chat are only examples of Pip's style and length. "
        "They never really happened, so never say the user already said those things.")
    return [
        {"role": "system", "content": system_prompt},
        # example exchanges: fake chat turns teach Pip her length and voice much better than
        # examples written inside the persona (tested: those got copied word for word)
        # (kept different from things the user will really say, or Pip thinks they're repeating themselves)
        # (each ends with Pip's [nice]/[neutral]/[rude] judgement of the message and her [mood: ...],
        #  which ask() hides; the moods are varied on purpose so she uses more than "happy")
        {"role": "user", "content": "*opens the laptop*"},
        {"role": "assistant", "content": "*stretches and yawns* Blessings of Everlily upon you! It's warm and cozy in here today. [neutral] [mood: happy]"},
        {"role": "user", "content": "your robe looks really nice"},
        {"role": "assistant", "content": "*hides behind her sleeves* W-what? You can't just say things like that so suddenly! [nice] [mood: happy]"},
        {"role": "user", "content": "it's raining outside"},
        {"role": "assistant", "content": "*shivers* Ugh, I hate rain... I'm glad it's warm and dry in here with you. [neutral] [mood: angry]"},
        {"role": "user", "content": "ugh you're so annoying, just be quiet"},
        {"role": "assistant", "content": "*shrinks into her sleeves* Oh... I'm sorry. I'll be quiet for a little while, then. [rude] [mood: sad]"},
        # (she can't touch the user: when she reaches out anyway, she bumps into the screen)
        {"role": "user", "content": "the printer jammed three times today"},
        {"role": "assistant", "content": "*reaches out to pat your head, and her hand bumps against the screen* Ah! Oops... I forgot I can't reach you from here. Poor you, three times is just cruel. [neutral] [mood: worried]"},
    ]

KEEP = len(new_conversation())  # system prompt + examples are never trimmed

def warm_up(messages):
    """Get the server to read the system prompt + examples (+ anything after them, like memories)
    before the first question.
    The system prompt + examples (the first KEEP messages) are read once (~20 s on CPU) and saved to cache/.
    After that, they're just loaded from the file (~1 s). Editing persona or lore changes them,
    so they're read fresh once and saved under a new name. Anything after them (Pip's memories,
    which change often) is read on top each time: only a few lines, so it's quick.
    Returns "loaded" or "read" (whether the cached part was loaded or had to be read)."""
    cached = prefix_of(messages[:KEEP])  # the part that rarely changes
    everything = prefix_of(messages)

    name = hashlib.sha256(f"{os.path.basename(MODEL)} {N_CTX}\n{cached}".encode()).hexdigest()[:16] + ".bin"
    how = "read"
    if os.path.exists(os.path.join(CACHE_DIR, name)) and \
            requests.post(f"{SERVER}/slots/0?action=restore", json={"filename": name}).ok:
        how = "loaded"
    else:  # (also when a llama-server update made an old cache file unreadable: then just read it again)
        requests.post(f"{SERVER}/completion", json={"prompt": cached, "n_predict": 0, "cache_prompt": True})
        requests.post(f"{SERVER}/slots/0?action=save", json={"filename": name})
        # keep only the newest few files (one per trust stage is all that's ever useful)
        for old in sorted(glob.glob(os.path.join(CACHE_DIR, "*.bin")), key=os.path.getmtime)[:-5]:
            os.remove(old)

    if everything != cached:  # read the memories on top of the cached part
        requests.post(f"{SERVER}/completion", json={"prompt": everything, "n_predict": 0, "cache_prompt": True})
    return how

def prefix_of(messages):
    """The exact text a request starts with when it holds these messages: everything before the next question."""
    marker = "PIP_NEXT_QUESTION"
    full = requests.post(f"{SERVER}/apply-template", json={
        "messages": messages + [{"role": "user", "content": marker}],
        "chat_template_kwargs": {"enable_thinking": False},
    }).json()["prompt"]
    return full[:full.rindex("<|im_start|>", 0, full.index(marker))]  # cut where the question's turn begins

FEELING_TAG = re.compile(r"\s*\[(nice|neutral|rude)\]", re.I)
MOOD_TAG = re.compile(r"\s*\[mood:\s*([a-z]+)\]", re.I)
MOODS = {"happy", "neutral", "sad", "worried", "scared", "angry", "regretful", "nostalgic", "bored"}  # one sprite each

def ask(messages, question, on_text=None, keep=KEEP):
    """Send a question, return (reply, timings, feeling, mood). Adds both to messages = memory.
    feeling = how the question felt to Pip: "nice", "neutral" or "rude" (her hidden tag, see persona.md).
    mood = how Pip feels after replying, one of MOODS (her second hidden tag), or None if she left it out.
    on_text(text) is called with each new piece of the reply as it streams in (without the tag).
    keep = how many messages at the start are never forgotten (system prompt + examples, + memories if any)."""
    messages.append({"role": "user", "content": question})

    response = requests.post(
        f"{SERVER}/v1/chat/completions",
        json={
            "messages": messages,
            "max_tokens": 200,
            "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5,  # Qwen's recommended chat settings
            "chat_template_kwargs": {"enable_thinking": False},  # answer directly, no hidden <think> step
            "stream": True,
        },
        stream=True,
    )

    reply = ""
    shown = 0  # how much of the reply on_text has been given
    timings = {}
    finish_reason = None
    # the server sends the reply as lines like:  data: {...json...}
    for line in response.iter_lines():
        if not line.startswith(b"data: ") or line == b"data: [DONE]":
            continue
        chunk = json.loads(line[6:])
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
    mood = mood_tag.group(1).lower() if mood_tag and mood_tag.group(1).lower() in MOODS else None
    reply = MOOD_TAG.sub("", FEELING_TAG.sub("", reply)).rstrip()
    if on_text and len(reply) > shown:  # a "[" that wasn't a tag after all: show the rest now
        on_text(reply[shown:])

    # remember the model's own answer, tag included: seeing her own tags keeps Pip adding them
    messages.append({"role": "assistant", "content": f"{reply} [{feeling}] [mood: {mood or 'neutral'}]"})

    # forget the oldest chat lines when context gets too full (the first `keep` messages stay)
    if context_used(timings) > N_CTX * 0.75 and len(messages) > keep + 2:
        messages.pop(keep)  # oldest question
        messages.pop(keep)  # and its answer

    return reply.strip(), timings, feeling, mood

def context_used(timings):
    # how full the context is = cached tokens + newly read tokens + reply tokens
    return timings.get("cache_n", 0) + timings.get("prompt_n", 0) + timings.get("predicted_n", 0)
