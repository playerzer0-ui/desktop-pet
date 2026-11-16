"""One scripted sitting on the real model: her greeting, then each message of a scene, with how the judge felt
about it, her mood, trust and how long she took.

    python -m tools.live.chat tools/live/scenes/judge-cases.json
    python -m tools.live.chat tools/live/scenes/ruby-breakdown.json --model qwen --runs 3 --out ruby.json

A message in a scene can say what the judge should make of it ({"say": "...", "felt": "nice"}, or "done": true):
a run that disagrees is marked MISS. Everything she said is also in the run's logs/<character>.log.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.live import common

def turn_record(said, t):
    return {"you": said, "reply": t.reply, "kind": t.kind, "felt": t.feeling, "mood": t.mood,
            "seconds": round(t.seconds, 1), "trust": [t.trust_before, t.trust_after],
            "points": [t.points_before, t.points_after], "quest_done": t.quest_done,
            "major_done": t.major_done, "story_done": t.story_done, "leaving": t.leaving,
            "reread_tokens": t.timings.get("prompt_n"), "context": t.context_used}

def misses(record, wanted):
    """What the judge got wrong against the scene's expectations."""
    wrong = []
    if "felt" in wanted and record["felt"] != wanted["felt"]:
        wrong.append(f"felt {record['felt']}, wanted {wanted['felt']}")
    done = record["quest_done"] or record["major_done"] or record["story_done"]  # (any quest or story step)
    if "done" in wanted and done != wanted["done"]:
        wrong.append(f"done {done}, wanted {wanted['done']}")
    return wrong

def show(record, wrong):
    flags = [f"[{record['felt'] or '-'}]", record["mood"], f"{record['seconds']}s"]
    if record["trust"][1] != record["trust"][0]:
        flags.append(f"trust {record['trust'][0]}->{record['trust'][1]}")
    for key in ("quest_done", "major_done", "story_done", "leaving"):
        if record[key]:
            flags.append(key.replace("_", " "))
    print(f"  you: {record['you']}\n  her: {record['reply']}\n       {' · '.join(flags)}"
          + (f"   MISS: {'; '.join(wrong)}" if wrong else "") + "\n", flush=True)

def run(scene, runs=1):
    """Plays the scene `runs` times, each from the scene's save. Returns a list of runs (lists of turn records)."""
    from engine.character import Character
    from mind.session import Session
    character = Character(scene["character"])
    if scene.get("no_time_limit", True):
        character.daily_minutes = None  # (a long scene shouldn't be sent home halfway)
    results = []
    for number in range(runs):
        print(f"--- run {number + 1} of {runs}: {character.name}", flush=True)
        common.seed_save(character, scene.get("save"))
        s = Session(character, say=lambda *_: None)
        turns = []
        if scene.get("greet", True):
            if s.opens_silently():
                print("  (a silent story step: no greeting)\n", flush=True)
            else:
                turns.append(turn_record("(greeting)", s.open()))
                show(turns[-1], [])
        for wanted in scene["messages"]:
            if "heard" in wanted:  # a duet line from the other character (scene["duet_with"]), not from you
                from engine.character import Character as Other
                from progress import duets
                turn = s.duet(duets.reply(character, Other(scene["duet_with"]), wanted["heard"]))
                turns.append(turn_record(f"({scene['duet_with']}: {wanted['heard']})", turn))
                show(turns[-1], [])
                continue
            record = turn_record(wanted["say"], s.user_says(wanted["say"]))
            record["miss"] = misses(record, wanted)
            turns.append(record)
            show(record, record["miss"])
        if scene.get("diary"):
            notes = [n["text"] for n in s.close()]
            print("  diary: " + (" | ".join(notes) if notes else "(nothing)") + "\n", flush=True)
            turns.append({"diary": notes})
        results.append(turns)
    return results

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scene")
    parser.add_argument("--model", choices=sorted(common.MODELS), help="default: the one engine/config.py ships")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--port", type=int, default=common.PORT)
    parser.add_argument("--out", help="write the results here as JSON")
    parser.add_argument("--sampling", help='JSON merged into her sampling settings, like \'{"temperature": 1.0}\'')
    args = parser.parse_args()
    config = common.use(args.model, args.port)
    if args.sampling:
        config.SAMPLING = {**config.SAMPLING, **json.loads(args.sampling)}
        print(f"sampling: {config.SAMPLING}", flush=True)
    scene = common.load_scene(args.scene)
    t0 = time.time()
    results = run(scene, args.runs)
    missed = sum(len(r.get("miss", [])) > 0 for turns in results for r in turns)
    judged = sum("felt" in m or "done" in m for m in scene["messages"]) * args.runs
    print(f"{config.MODEL_FILE} · {time.time() - t0:.0f}s · logs in {config.LOG_DIR}"
          + (f" · judge missed {missed} of {judged}" if judged else ""))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"model": config.MODEL_FILE, "scene": args.scene, "runs": results}, f, indent=1)

if __name__ == "__main__":
    main()
