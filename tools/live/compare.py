"""The same scenes on two (or more) models, side by side in one Markdown file.

    python -m tools.live.compare tools/live/scenes/judge-cases.json tools/live/scenes/pip-hello.json
    python -m tools.live.compare tools/live/scenes/*.json --models gemma qwen --runs 2 --out compare.md

Each model runs in its own process on its own port, one after the other (two 4B models at once would only measure
the machine). The raw results are kept next to the report as <out>-<model>-<scene>.json.
"""
import argparse, glob, json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.live import common

def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")

def report(scene_path, results):
    """One scene's table: a row per message, a column per model (the first run of each)."""
    lines = [f"## {os.path.basename(scene_path)}", ""]
    models = list(results)
    lines += ["| you | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    first = {m: [t for t in results[m]["runs"][0] if "you" in t] for m in models}
    for i, said in enumerate(t["you"] for t in first[models[0]]):
        row = [cell(said)]
        for m in models:
            t = first[m][i] if i < len(first[m]) else None
            if t is None:
                row.append("")
                continue
            flags = [t["felt"] or "-", t["mood"], f"{t['seconds']}s"]
            if t["quest_done"]:
                flags.append("done")
            if t.get("miss"):
                flags.append("**MISS: " + "; ".join(t["miss"]) + "**")
            row.append(cell(t["reply"]) + "<br>*" + " · ".join(flags) + "*")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    for m in models:  # every run, for the numbers
        runs = results[m]["runs"]
        user = [t for turns in runs for t in turns if t.get("kind") == "user"]
        if not user:
            continue
        missed = sum(bool(t.get("miss")) for t in user)
        nice = sum(t["felt"] == "nice" for t in user)
        seconds = sorted(t["seconds"] for t in user)
        trust = [turns[-1]["trust"][1] for turns in runs if turns and "trust" in turns[-1]]
        lines.append(f"- **{m}** over {len(runs)} run(s): judge missed {missed} of {len(user)} · {nice} nice · "
                     f"reply median {seconds[len(seconds) // 2]}s, slowest {seconds[-1]}s · trust at the end "
                     f"{', '.join(map(str, trust))}")
        diaries = [t["diary"] for turns in runs for t in turns if "diary" in t]
        for notes in diaries:
            lines.append(f"  - diary: {' | '.join(notes) if notes else '(nothing)'}")
    return "\n".join(lines) + "\n"

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenes", nargs="+")
    parser.add_argument("--models", nargs="+", default=sorted(common.MODELS), choices=sorted(common.MODELS))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--out", default="compare.md")
    args = parser.parse_args()
    scenes = [p for pattern in args.scenes for p in sorted(glob.glob(pattern))] or args.scenes
    stem = os.path.splitext(args.out)[0]
    sections = []
    for scene in scenes:
        results = {}
        for n, model in enumerate(args.models):
            raw = f"{stem}-{model}-{os.path.splitext(os.path.basename(scene))[0]}.json"
            print(f"=== {scene} on {model}", flush=True)
            subprocess.run([sys.executable, "-m", "tools.live.chat", scene, "--model", model, "--runs", str(args.runs),
                            "--port", str(common.PORT + 1 + n), "--out", raw], cwd=common.ROOT, check=True)
            with open(raw, encoding="utf-8") as f:
                results[model] = json.load(f)
        sections.append(report(scene, results))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(f"# {' vs '.join(args.models)}\n\n" + "\n".join(sections))
    print(f"Report: {os.path.abspath(args.out)}")

if __name__ == "__main__":
    main()
