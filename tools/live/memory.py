"""How much memory llama-server uses over a long sitting, with one or more characters on the desktop, and whether
it levels off. Also shows the stalls that come with too few checkpoints (she reads her whole prompt again) and,
in a long enough run, the moment her context fills and she forgets old chat lines.

    python -m tools.live.memory --model gemma --who pip --messages 40
    python -m tools.live.memory --model gemma --who pip ruby --messages 60 --out memory.csv
    python -m tools.live.memory --model qwen --checkpoints 1      (try another --ctx-checkpoints)

Messages go to each character in turn, like a player talking to both. The figure that matters is "private"
(Task Manager's Memory column on Windows).
"""
import argparse, csv, itertools, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.live import common

# ordinary chat, nothing that finishes a quest on purpose: what a sitting mostly is
SMALL_TALK = [
    "hi! how are you today?", "what have you been up to?", "I had a long day at work", "do you like music?",
    "I listened to some jazz this morning", "what's your favourite time of day?", "it's cold outside",
    "I made pasta for dinner", "do you ever get bored?", "tell me something about where you live",
    "my friend called me today", "I'm a bit tired", "what makes you happy?", "I went for a walk by the river",
    "do you dream?", "I'm reading a book about space", "what's the weather like where you are?",
    "I like talking to you", "I need to clean my room later", "have you ever seen snow?",
]
SLOW = 15        # seconds: a reply slower than this is a stall worth a look
REREAD = 1500    # tokens: re-reading more than this means the server went back to the start of her prompt

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", choices=sorted(common.MODELS), help="default: the one engine/config.py ships")
    parser.add_argument("--who", nargs="+", default=["pip"], help="character folders (each gets its own slot)")
    parser.add_argument("--messages", type=int, default=40, help="in all, shared between them")
    parser.add_argument("--checkpoints", type=int, help="override the model's --ctx-checkpoints")
    parser.add_argument("--port", type=int, default=common.PORT)
    parser.add_argument("--out", help="write every sample here as CSV")
    args = parser.parse_args()

    config = common.use(args.model, args.port)
    if args.checkpoints is not None:
        config.MODEL_CHECKPOINTS = args.checkpoints
    from engine.character import Character
    from mind.session import Session
    slots = len(args.who)
    sessions = []
    for slot, folder in enumerate(args.who):
        character = Character(folder)
        character.daily_minutes = None  # (a long run shouldn't be sent home)
        others = [Character(f).name for f in args.who if f != folder]
        sessions.append(Session(character, say=lambda *_: None, slot=slot, slots=slots, company=others))
    server = common.server_process(args.port)
    if server is None:
        raise SystemExit(f"Can't find the llama-server on port {args.port} to measure.")
    start = common.memory_mb(server)
    print(f"{config.MODEL_FILE} · checkpoints {config.MODEL_CHECKPOINTS} · {', '.join(args.who)} · "
          f"after warm-up {start[1]:.0f} MB private ({start[0]:.0f} MB working set)\n", flush=True)
    print(f"{'#':>3}  {'who':<6} {'secs':>5} {'reread':>6} {'context':>7} {'private MB':>10} {'change':>7}", flush=True)

    rows, lines = [], itertools.cycle(SMALL_TALK)
    for n in range(1, args.messages + 1):
        s = sessions[(n - 1) % slots]
        turn = s.user_says(next(lines))
        working, private = common.memory_mb(server)
        reread = turn.timings.get("prompt_n", 0)
        context = turn.context_used / config.N_CTX
        flags = (["SLOW"] if turn.seconds > SLOW else []) + (["RE-READ"] if reread > REREAD else [])
        rows.append({"message": n, "who": s.character.folder, "seconds": round(turn.seconds, 1), "reread": reread,
                     "context": round(context, 3), "working_mb": round(working), "private_mb": round(private)})
        print(f"{n:>3}  {s.character.folder:<6} {turn.seconds:>5.1f} {reread:>6} {context:>7.0%} {private:>10.0f} "
              f"{private - start[1]:>+7.0f}  {' '.join(flags)}", flush=True)

    private = [r["private_mb"] for r in rows]
    tail = private[-10:]
    print(f"\nstart {start[1]:.0f} MB · peak {max(private)} MB (+{max(private) - start[1]:.0f}) · end {private[-1]} MB"
          f" · last {len(tail)} messages moved {tail[-1] - tail[0]:+} MB")
    print(f"slow replies (> {SLOW}s): {sum(r['seconds'] > SLOW for r in rows)} · full re-reads: "
          f"{sum(r['reread'] > REREAD for r in rows)} · context reached {max(r['context'] for r in rows):.0%}"
          f" (she forgets old lines at {config.FORGET_AT:.0%})")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

if __name__ == "__main__":
    main()
