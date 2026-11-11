"""Startup checks of the character files, for mistakes that would otherwise fail quietly:
each character's moods agreeing across character.toml, persona.md, events.md, her sprites and moves.MOOD_MOVES,
plus roster.toml, story steps and duet files. main() won't start until they're all good.

    python -m desktop.check [character]
"""
import os, re, sys
from mind import lore
from progress import duets, roster
from engine.character import Character, DEFAULT, is_character
from desktop import moves

def persona_moods(text):
    """The '- mood: meaning' lines in persona.md's mood list."""
    start, end = text.find("[mood: X]"), text.find("The user never sees these tags")
    return set(re.findall(r"^- ([a-z]+):", text[start:end], re.M)) if start >= 0 and end > start else set()

def events_moods(text):
    """The comma-separated line under '## Moods' in events.md."""
    found = re.search(r"^## Moods\s*\n+(.+)", text, re.M)
    return {m.strip().lower() for m in found.group(1).split(",") if m.strip()} if found else set()

def mood_problems(character):
    """Every way her mood lists disagree (empty = all good)."""
    moods = character.moods
    folder = f"character/{character.folder}/"
    lists = {
        folder + "persona.md": persona_moods(character.text("persona.md")),
        f"the '## Moods' line in {folder}events.md": events_moods(character.text("events.md")),
    }
    sprites = {name[:-4] for name in os.listdir(character.sprites) if name.endswith(".png")}
    every = moods | character.story_moods  # story moods need a sprite and a move, but aren't on the lists
    toml = folder + "character.toml"
    problems = []
    for where, found in lists.items():
        if not found:
            problems.append(f"no moods found in {where}")
            continue
        if moods - found:
            problems.append(f"{where} is missing: {', '.join(sorted(moods - found))}")
        if found - moods:
            problems.append(f"{where} has {', '.join(sorted(found - moods))}, which {toml} doesn't")
    if every - sprites:
        problems.append(f"{folder}sprites/ is missing: {', '.join(sorted(every - sprites))}")
    if sprites - every:
        problems.append(f"{folder}sprites/ has {', '.join(sorted(sprites - every))}, which {toml} doesn't "
                        "(add it to moods, or to story_moods if only a story step uses it)")
    if every - set(moves.MOOD_MOVES):  # shared: a mood only another character has is fine
        problems.append(f"moves.MOOD_MOVES is missing: {', '.join(sorted(every - set(moves.MOOD_MOVES)))}")
    for e in character.events:
        for mood in sorted(e["not_ready_moods"] - moods):
            problems.append(f"event '{e['name']}' waits on mood '{mood}', which {toml} doesn't have")
        if e["mood_after"] and e["mood_after"].lower() not in moods:
            problems.append(f"event '{e['name']}' has Mood after: '{e['mood_after']}', which {toml} doesn't have")
    return problems

def lore_problems(character):
    """lore.md sections with "words:" but no "in short:" at some stage: her prompt wouldn't know the topic exists."""
    problems = []
    for stage in range(1, 6):
        prompt, sections = lore.split(character.staged("lore.md", stage))
        for heading in sections:
            if not re.search(rf"^## {re.escape(heading)}\n- ", prompt, re.M):
                problems.append(f"character/{character.folder}/lore.md: '## {heading}' has words: but no "
                                f"'in short:' line by stage {stage}, so her prompt has nothing about it")
    return sorted(set(problems))

def cast_problems(also=()):
    """Every mistake in the cast's files (empty = all good). also = folders opened by name, not in the roster."""
    try:
        r = roster.rules()
    except (ValueError, OSError) as e:
        return [f"character/roster.toml: {e}"]
    cast = [DEFAULT] + [u["who"] for u in r["unlocks"] + r["arrivals"]]
    problems = []
    for folder in cast + [f for f in also if f not in cast]:
        try:
            c = Character(folder)
        except (ValueError, KeyError, OSError) as e:
            problems.append(f"character/{folder}: {type(e).__name__}: {e}")
            continue
        problems += [f"{c.name}: {p}" for p in mood_problems(c)]
        problems += [f"{c.name}: {p}" for p in lore_problems(c)]
        problems += step_problems(c, cast, r["on_screen"])
    problems += duet_problems()
    return problems

def step_problems(character, cast, on_screen):
    """Story steps naming someone not in the cast, or needing more on screen than on_screen allows."""
    problems = []
    for stage, quest in sorted(character.major_quests.items()):
        for i, step in enumerate(quest.get("steps", []), 1):
            where = f"{character.name}'s [major_quests.{stage}] step {i}"
            needs = step.get("needs") or []
            named = needs + [step.get("told_by")] + [step.get("duet", {}).get(k) for k in ("starts", "with")]
            for folder in dict.fromkeys(f for f in named if f):
                if folder not in cast:
                    problems.append(f"{where} names {folder!r}, who isn't in the cast (character/roster.toml): "
                                    "the step would wait for her forever")
            if len(needs) > on_screen:
                problems.append(f"{where} needs {len(needs)} on the desktop, but on_screen in roster.toml is "
                                f"{on_screen}")
    return problems

def duet_problems():
    """Duet files with a bad name, the same pair twice, or a mistake inside."""
    problems, seen = [], {}
    for name in sorted(os.listdir(duets.DUET_DIR)) if os.path.isdir(duets.DUET_DIR) else []:
        if not name.endswith(".toml"):
            continue
        folders = name[:-5].split("-", 1)
        if len(folders) != 2 or not all(is_character(f) for f in folders):
            problems.append(f"character/duets/{name}: its name should be <folder>-<folder>.toml, two characters "
                            "in character/")
            continue
        pair = frozenset(folders)
        if pair in seen:
            problems.append(f"character/duets/{name} and {seen[pair]} are the same pair: only one of them is used")
            continue
        seen[pair] = name
        try:
            duets.Pair(os.path.join(duets.DUET_DIR, name))
        except (ValueError, KeyError, OSError) as e:
            problems.append(f"character/duets/{name}: {e}")
    return problems

if __name__ == "__main__":
    found = cast_problems(also=sys.argv[1:2])
    print("\n".join(found) or "the cast's files are all good")
