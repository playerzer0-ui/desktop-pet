"""The judge alone, on fixed lines: her line, your message, and what it should decide. Her replies change from run
to run, so a chat scene can't say what the judge should make of a message that depends on them; this can, and
the judge answers at temperature 0, so a run is repeatable.

    python -m tools.live.judge
    python -m tools.live.judge tools/live/scenes/judge-lines.json --model qwen

Each case is also asked without her line ("blind"), to see what the line changes.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.live import common

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cases", nargs="?", default=os.path.join(os.path.dirname(__file__), "scenes", "judge-lines.json"))
    parser.add_argument("--model", choices=sorted(common.MODELS), help="default: the one engine/config.py ships")
    parser.add_argument("--port", type=int, default=common.PORT)
    args = parser.parse_args()
    config = common.use(args.model, args.port)
    from engine.server import start_server
    from engine.character import Character
    from mind import judge
    start_server(lambda *_: None, slots=1)
    with open(args.cases, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    t0, missed = time.time(), 0
    for case in cases:
        c = Character(case.get("character", "pip"))
        said = case.get("said")
        if "felt" in case:
            blind, got = judge.feeling(c, case["say"], 1), judge.feeling(c, case["say"], 1, said=said)
            wanted = case["felt"]
        else:
            asked, counts = case["asked"], case["counts"]
            blind = judge.done(c, asked, counts, case["say"], 1)
            got = judge.done(c, asked, counts, case["say"], 1, said=said)
            wanted = case["done"]
        missed += got != wanted
        print(f"{case['say'][:42]!r:44} blind {str(blind):8} with her line {str(got):8} wanted {str(wanted):8}"
              + ("" if got == wanted else "MISS"), flush=True)
    print(f"\n{config.MODEL_FILE} · judge missed {missed} of {len(cases)} · {time.time() - t0:.0f}s")

if __name__ == "__main__":
    main()
