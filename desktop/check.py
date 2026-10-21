"""A startup check that every list of a character's moods agrees. For Pip they live in five places:

    character/pip/character.toml   moods = [...]: the ones pet.ask() accepts from her tag (anything else is dropped)
    character/pip/persona.md       the list the model is told to choose from
    character/pip/events.md        the "## Moods" line, and each event's "Not ready if mood is" / "Mood after"
    character/pip/sprites/         one <mood>.png each
    moves.MOOD_MOVES               the move and emote for each mood (shared by every character)

A mood missing from one of them fails quietly (a dropped tag, an event that never waits, a sprite that never
shows), so main() refuses to start until they match.

    python -m desktop.check [character]    run it on its own (Pip if no character is named)
"""
import os, re, sys
from character import Character, DEFAULT
from desktop import moves

def persona_moods(text):
    """The '- mood: meaning' lines between '[mood: X]' and 'The user never sees these tags' in persona.md."""
    start, end = text.find("[mood: X]"), text.find("The user never sees these tags")
    return set(re.findall(r"^- ([a-z]+):", text[start:end], re.M)) if start >= 0 and end > start else set()

def events_moods(text):
    """The comma-separated line under '## Moods' in events.md."""
    found = re.search(r"^## Moods\s*\n+(.+)", text, re.M)
    return {m.strip().lower() for m in found.group(1).split(",") if m.strip()} if found else set()

def mood_problems(character):
    """Every way the character's mood lists disagree, as readable lines (an empty list = all good)."""
    moods = character.moods
    folder = f"character/{character.folder}/"
    lists = {
        folder + "persona.md": persona_moods(character.text("persona.md")),
        f"the '## Moods' line in {folder}events.md": events_moods(character.text("events.md")),
        folder + "sprites/": {name[:-4] for name in os.listdir(character.sprites) if name.endswith(".png")},
        "moves.MOOD_MOVES": set(moves.MOOD_MOVES),
    }
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
    for e in character.events:
        for mood in sorted(e["not_ready_moods"] - moods):
            problems.append(f"event '{e['name']}' waits on mood '{mood}', which {toml} doesn't have")
        if e["mood_after"] and e["mood_after"].lower() not in moods:
            problems.append(f"event '{e['name']}' has Mood after: '{e['mood_after']}', which {toml} doesn't have")
    return problems

if __name__ == "__main__":
    found = mood_problems(Character(sys.argv[1] if len(sys.argv) > 1 else DEFAULT))
    print("\n".join(found) or "all mood lists match")
