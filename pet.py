import json, re, requests
from load import load, for_stage, SERVER, N_CTX
from save import load_save, stage_of

def trim_to_sentence(text):
    # cut a reply that hit max_tokens back to its last full sentence (. ! ? … plus any closing quote/asterisk)
    ends = list(re.finditer(r'[.!?…]["\'*)]*(?=\s|$)', text))
    return text[:ends[-1].end()] if ends else text

# Everything that defines how Pip talks lives here, so main.py and test_pip.py use the exact same Pip.

def new_conversation(stage=None):
    """stage 1-5 = how much Pip trusts the user (from save.json if not given).
    Lore and feelings she isn't ready to share are left out of the prompt entirely."""
    if stage is None:
        stage = stage_of(load_save()["trust"])
    system_prompt = (for_stage(load("character/persona.md"), stage)
        + "\n\n# Background lore\n" + for_stage(load("character/lore.md"), stage))
    if stage < 5:
        system_prompt += ("\n\n# Trust\nPip knows much more about her world and herself than written here, "
            "but she doesn't trust the user enough to share it yet. If asked about it, she gently "
            "changes the subject instead of making things up.")
    system_prompt += ("\n\n# Note\nThe first 3 exchanges in this chat are only examples of Pip's style and length. "
        "They never really happened, so never say the user already said those things.")
    return [
        {"role": "system", "content": system_prompt},
        # example exchanges: fake chat turns teach Pip her length and voice much better than
        # examples written inside the persona (tested: those got copied word for word)
        # (kept different from things the user will really say, or Pip thinks they're repeating themselves)
        {"role": "user", "content": "*opens the laptop*"},
        {"role": "assistant", "content": "*stretches and yawns* Blessings of Everlily upon you! It's warm and cozy in here today."},
        {"role": "user", "content": "your robe looks really nice"},
        {"role": "assistant", "content": "*hides behind her sleeves* W-what? You can't just say things like that so suddenly!"},
        {"role": "user", "content": "it's raining outside"},
        {"role": "assistant", "content": "*shivers* Ugh, I hate rain... I'm glad it's warm and dry in here with you."},
    ]

KEEP = len(new_conversation())  # system prompt + examples are never trimmed

def ask(messages, question, on_text=None):
    """Send a question, return (reply, timings). Adds both to messages = memory.
    on_text(text) is called with each new piece of the reply as it streams in."""
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
            if on_text:
                on_text(text)

    # hit max_tokens mid-sentence: keep only the finished sentences in memory
    if finish_reason == "length":
        reply = trim_to_sentence(reply)

    # remember the model's own answer
    messages.append({"role": "assistant", "content": reply})

    # forget the oldest chat lines when context gets too full (system prompt + examples are kept)
    if context_used(timings) > N_CTX * 0.75 and len(messages) > KEEP + 2:
        messages.pop(KEEP)  # oldest question
        messages.pop(KEEP)  # and its answer

    return reply, timings

def context_used(timings):
    # how full the context is = cached tokens + newly read tokens + reply tokens
    return timings.get("cache_n", 0) + timings.get("prompt_n", 0) + timings.get("predicted_n", 0)
