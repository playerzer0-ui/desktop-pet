import os, time, psutil
from llama_cpp import Llama

proc = psutil.Process(os.getpid())
proc.cpu_percent()

llm = Llama(model_path="models/Qwen3.5-2B-Q5_K_M.gguf", n_ctx=8192, verbose=False)

def context_used(messages):
    total = 0
    for m in messages:
        total += len(llm.tokenize(m["content"].encode("utf-8"), add_bos=False))
        total += 5  # small overhead per message (role tags like <|im_start|>user)
    return total

def load(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

# created once, before the loop, so it keeps growing = memory
system_prompt = load("character/persona.md") + "\n\n# Background lore\n" + load("character/lore.md")

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
    first_token = None  # when the first word appeared (= time spent reading the prompt)
    tokens = 0
    reply = ""
    for chunk in llm.create_chat_completion(
        messages=messages,
        max_tokens=200,
        temperature=0.7, top_p=0.8, top_k=20, presence_penalty=1.5,  # Qwen's recommended chat settings
        stream=True,
    ):
        text = chunk["choices"][0]["delta"].get("content", "")
        if text:
            if first_token is None:
                first_token = time.time()
            print(text, end="", flush=True)
            reply += text
            tokens += 1

    elapsed = time.time() - t0
    print()

    # remember the model's own answer
    messages.append({"role": "assistant", "content": reply})

    # forget the oldest chat lines when context gets too full (system prompt + examples are kept)
    while context_used(messages) > llm.n_ctx() * 0.75 and len(messages) > KEEP + 1:
        messages.pop(KEEP)

    used = context_used(messages)
    print()
    print(f"[context: {used} / {llm.n_ctx()} tokens ({used / llm.n_ctx():.0%})]")
    print()
    first_token = first_token or t0 + elapsed
    print(f"Answer time : {elapsed:.2f} s")
    print(f"Reading time: {first_token - t0:.2f} s  (before the first word)")
    print(f"Writing     : {tokens / max(t0 + elapsed - first_token, 0.01):.1f} tokens/s")
    print(f"RAM used    : {proc.memory_info().rss / 1024**2:.0f} MB")
    print(f"CPU (avg)   : {proc.cpu_percent() / psutil.cpu_count():.0f}%")
