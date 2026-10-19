import time
from load import start_server, N_CTX
from pet import new_conversation, ask, context_used, warm_up

start_server()

# created once, before the loop, so it keeps growing = memory
messages = new_conversation()

t0 = time.time()
if warm_up(messages) == "read":  # first launch since persona/lore changed: slow once, then saved
    print(f"(Pip read her persona and lore in {time.time() - t0:.0f} s, saved for next time)")

while True:

    question = input("Ask me a question (or type 'exit' to quit): ")
    if question.lower() == "exit":
        break

    print("Q:", question)
    print("A: ", end="")

    t0 = time.time()
    first_token = None

    def show(text):
        global first_token
        if first_token is None:
            first_token = time.time()
        print(text, end="", flush=True)

    reply, timings = ask(messages, question, on_text=show)

    elapsed = time.time() - t0
    print()

    used = context_used(timings)
    print()
    print(f"[context: {used} / {N_CTX} tokens ({used / N_CTX:.0%})]")
    print()
    print(f"Answer time : {elapsed:.2f} s")
    print(f"Reading time: {(first_token or t0 + elapsed) - t0:.2f} s  "
          f"(re-read {timings.get('prompt_n', '?')} tokens, reused {timings.get('cache_n', '?')} from cache)")
    print(f"Writing     : {timings.get('predicted_per_second', 0):.1f} tokens/s")
