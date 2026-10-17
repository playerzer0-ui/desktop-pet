import json
from load import *

start_server()

system_prompt = load("character/persona.md") + "\n\n# Background lore\n" + load("character/lore.md")

# created once, before the loop, so it keeps growing = memory
messages = [
    {"role": "system", "content": system_prompt},
    # example exchange: teaches Pip the length and style of her replies
    {"role": "user", "content": "good morning, Pip"},
    {"role": "assistant", "content": "*brushes hair* Blessings of Everlily upon you! It's warm and cozy in here today."},
    {"role": "user", "content": "you look cute today"},
    {"role": "assistant", "content": "*hides behind her sleeves* W-what? You can't just say things like that so suddenly!"},
    {"role": "user", "content": "what do you think about the bloodcult?"},
    {"role": "assistant", "content": "*glances around nervously* Please don't say that name so loud... anyone could be one of them, even someone you trust."},
]
KEEP = len(messages)  # system prompt + examples are never trimmed

while True:

    question = input("Ask me a question (or type 'exit' to quit): ")
    if question.lower() == "exit":
        break

    messages.append({"role": "user", "content": question})

    print("Q:", question)
    print("A: ", end="")

    t0 = time.time()
    first_token = None
    reply = ""
    timings = {}

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

    # the server sends the reply as lines like:  data: {...json...}
    for line in response.iter_lines():
        if not line.startswith(b"data: ") or line == b"data: [DONE]":
            continue
        chunk = json.loads(line[6:])
        timings = chunk.get("timings", timings)  # the last chunk carries the server's timing stats
        if not chunk.get("choices"):
            continue
        text = chunk["choices"][0]["delta"].get("content") or ""
        if text:
            if first_token is None:
                first_token = time.time()
            print(text, end="", flush=True)
            reply += text

    elapsed = time.time() - t0
    print()

    # remember the model's own answer
    messages.append({"role": "assistant", "content": reply})

    # how full the context is = cached tokens + newly read tokens + reply tokens
    used = timings.get("cache_n", 0) + timings.get("prompt_n", 0) + timings.get("predicted_n", 0)

    # forget the oldest chat lines when context gets too full (system prompt + examples are kept)
    if used > N_CTX * 0.75 and len(messages) > KEEP + 2:
        messages.pop(KEEP)  # oldest question
        messages.pop(KEEP)  # and its answer

    print()
    print(f"[context: {used} / {N_CTX} tokens ({used / N_CTX:.0%})]")
    print()
    print(f"Answer time : {elapsed:.2f} s")
    print(f"Reading time: {(first_token or t0 + elapsed) - t0:.2f} s  "
          f"(re-read {timings.get('prompt_n', '?')} tokens, reused {timings.get('cache_n', '?')} from cache)")
    print(f"Writing     : {timings.get('predicted_per_second', 0):.1f} tokens/s")
