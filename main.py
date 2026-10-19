import atexit, queue, threading, time
import trust
from idle import Idle
from load import start_server, N_CTX
from pet import new_conversation, ask, context_used, warm_up

start_server()

save = trust.start()  # counts today as a day logged
opened = time.time()  # for "duration of stay"

def count_stay():
    global opened
    trust.stayed(save, (time.time() - opened) / 60)
    opened = time.time()
atexit.register(count_stay)  # the last stretch counts too

# created once, before the loop, so it keeps growing = memory
messages = new_conversation(stage=trust.stage(save))

t0 = time.time()
if warm_up(messages) == "read":  # first launch since persona/lore changed: slow once, then saved
    print(f"(Pip read her persona and lore in {time.time() - t0:.0f} s, saved for next time)")

def say(text, from_user):
    """Send a message to Pip and print her reply. text is what the user typed,
    or (from_user=False) a hidden stage direction from idle.py that makes her speak on her own."""
    print("Pip: ", end="", flush=True)
    t0 = time.time()
    first_token = None

    def show(piece):
        nonlocal first_token
        if first_token is None:
            first_token = time.time()
        print(piece, end="", flush=True)

    reply, timings, feeling = ask(messages, text, on_text=show)
    elapsed = time.time() - t0
    print()

    old_trust = save["trust"]
    if from_user:  # Pip talking on her own earns nothing
        trust.talked(save, text, feeling)
    count_stay()
    print(f"  [{'felt ' + feeling if from_user else 'spoke on her own'} | trust {save['trust']}, {save['points']} points | "
          f"today: talk {save['today']['talk']}/{trust.TALK_CAP}, {save['today']['minutes']:.0f} min open]")
    if save["trust"] > old_trust:
        print(f"  *** Pip trusts you more! Trust {save['trust']} ***")
        if trust.stage_of(save["trust"]) > trust.stage_of(old_trust):
            print(f"  *** Stage {trust.stage(save)}: she'll open up more next time you open her ***")

    used = context_used(timings)
    print(f"  [context {used}/{N_CTX} ({used / N_CTX:.0%}) | {elapsed:.1f} s, "
          f"reading {(first_token or t0 + elapsed) - t0:.1f} s (re-read {timings.get('prompt_n', '?')}, "
          f"reused {timings.get('cache_n', '?')}) | {timings.get('predicted_per_second', 0):.1f} tokens/s]")

# input() blocks, so the keyboard gets its own thread and the main loop stays free to keep time
typed = queue.Queue()
def read_keyboard():
    while True:
        try:
            typed.put(input())
        except EOFError:
            typed.put("exit")
            return
threading.Thread(target=read_keyboard, daemon=True).start()

idle = Idle()
print("Type to talk to Pip (or 'exit' to quit).")
say(idle.opening(), from_user=False)

while True:
    try:
        question = typed.get(timeout=5)  # every 5 s with nothing typed: check if she wants to speak up
    except queue.Empty:
        nudge = idle.due()
        if nudge:
            say(nudge, from_user=False)
        continue

    if question.strip().lower() == "exit":
        break
    if not question.strip():
        continue
    idle.user_spoke()
    say(question, from_user=True)
