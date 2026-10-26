"""World events: dated days when something happens in a character's world (their events.md, e.g. character/pip/).

Each '## Name' block there has WHEN (the date), READY (min trust, moods that hold her back) and
CONTENT (the fact, a reaction for each trust stage, a tone note); see template.md.
On an event's day, if she's ready, Pip tells you about it once: in her greeting, or else in her next
idle nudge. A stage with no reaction line means she keeps it to herself at that stage.
On a day she isn't ready to tell (trust too low, the wrong mood, no reaction at her stage), she only
shows the event's "Hint while waiting" (also once a day) and doesn't say why.

    news = events.due(date, save, character)   # what to tell (or hint at) today: {"id", "text", "mood_after", "hint"}
    events.stage_direction(date, save, character)  # the same, as a full stage direction (or None)
    events.told(date, save, news)   # she told it: don't repeat it today (kept in the save)
(The examples say Pip and "she"; the prompts are written with {name}/{they} and filled in per character.)
"""
import datetime, re
from save import stage_of
from directions import direction

# Her mood (save["mood"], set by session.py) can hold an event back. It starts neutral every sitting and eases
# back to neutral a little while after she speaks, exactly when her sprite does.

def parse(text):
    """Every dated '## Name' block in events.md -> a dict. Blocks without a Date (like the arc table) are skipped."""
    found = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        name, _, body = block.partition("\n")
        fields, reactions = {}, {}
        for line in body.splitlines():
            stage_line = re.match(r"\s+- Stage ([1-5]):\s*(.*)", line)
            field = re.match(r"- ([^:]+):\s*(.*)", line)
            if stage_line:
                reaction = stage_line.group(2).strip()
                if reaction and reaction.lower() != "(not ready)":
                    reactions[int(stage_line.group(1))] = reaction
            elif field:
                fields[field.group(1).strip().lower()] = field.group(2).strip()
        when = re.match(r"(\w+ \d+)(?:, (\d{4}))?", fields.get("date", ""))
        if not when:
            continue
        day = datetime.datetime.strptime(when.group(1) + " 2000", "%B %d %Y")  # 2000: a leap year, so Feb 29 parses
        found.append({
            "id": re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-"),
            "name": name.strip(),
            "month": day.month, "day": day.day,
            "year": int(when.group(2)) if when.group(2) else None,  # None = every year
            "min_trust": int(fields.get("min trust", 1)),
            "not_ready_moods": {m.strip().lower() for m in fields.get("not ready if mood is", "").split(",") if m.strip()},
            "fact": fields.get("fact", ""),
            "mood_after": fields.get("mood after", ""),
            "reactions": reactions,
            "tone": fields.get("tone note", ""),
            "hint": fields.get("hint while waiting", ""),
        })
    return found

def on(events, date):
    """The events (a character's parsed events.md) that fall on this date."""
    return [e for e in events if (e["month"], e["day"]) == (date.month, date.day) and e["year"] in (None, date.year)]

def due(date, save, character):
    """The event the character (character.py) should tell today, as text for a stage direction, or None.
    An event she isn't ready for (trust, mood, no reaction at her stage) gives its hint instead (hint=True).
    Anything already told (or hinted at) today is skipped."""
    stage = stage_of(save["trust"])
    mood = save.get("mood")
    today = date.isoformat()
    waiting = []
    for e in on(character.events, date):
        if save.get("events_told", {}).get(e["id"]) == today:
            continue
        if save["trust"] < e["min_trust"] or mood in e["not_ready_moods"] or stage not in e["reactions"]:
            if e["hint"] and save.get("events_hinted", {}).get(e["id"]) != today:
                waiting.append(e)
            continue
        acts, _, says = e["reactions"][stage].partition(" / ")
        # (its name only from stage 3, with the fact: below that the reaction is all she says, and given the name
        #  she said it anyway: "a cold inspection from Heaven" when the reaction was only "the exchange is busy")
        named = f" ({e['name']})" if stage >= 3 else ""
        text = character.fill(f"Something happened in {{name}}'s world today{named}. "
                              "{They} ") + f"{acts.strip()}, and {says.strip()}."
        if stage >= 3:  # from stage 3 she's honest about her world, so she may know and say what happened
            text += f" What happened: {e['fact']}"
        text += character.fill(" Only share as much as that. Afterwards {they} feels ") +             f"{e['mood_after']}. Tone: {e['tone']}."
        return {"id": e["id"], "text": text, "mood_after": e["mood_after"], "hint": False}
    for e in waiting:  # nothing she's ready to tell: let it show a little instead
        text = (character.fill("Today {name} is ") + e["hint"] + character.fill(
            ". Let that show in how {they} acts, but {they} doesn't say why and doesn't mention anything "
            "happening in {their} world."))
        return {"id": e["id"], "text": text, "mood_after": None, "hint": True}
    return None

def stage_direction(date, save, character):
    """The stage direction that makes the character tell today's event on their own, or None. Doesn't mark it told."""
    news = due(date, save, character)
    return news and direction(character.fill("{name} says something on {their} own. ") + news["text"])

def told(date, save, news):
    """The character told (or hinted at) this event: remember the day, so she doesn't repeat it today.
    Hints are kept apart, so she can still tell it later that day if trust goes up."""
    save.setdefault("events_hinted" if news["hint"] else "events_told", {})[news["id"]] = date.isoformat()


if __name__ == "__main__":  # quick self-check, with Pip's events: python events.py
    from character import Character
    pip = Character("pip")
    EVENTS = pip.events
    D = datetime.date
    def check(date, trust, expect, mood=None):
        save = {"trust": trust, "mood": mood}
        news = due(date, save, pip)
        got = news and (news["id"] + (" (hint)" if news["hint"] else ""))
        assert got == expect, f"{date} trust {trust}: expected {expect}, got {got}"
        print(f"ok  {date} trust {trust:>2} mood {mood}: {got}")
        return save, news

    assert len(EVENTS) == 10, [e["id"] for e in EVENTS]
    _, s1 = check(D(2026, 10, 15), 2, "sally-s-death-anniversary")   # stage 1
    _, s5 = check(D(2026, 10, 15), 10, "sally-s-death-anniversary")  # stage 5
    assert "reveals nothing" in s1["text"] and "What happened" not in s1["text"], s1["text"]
    assert "Sally was kind" in s5["text"] and "What happened" in s5["text"], s5["text"]
    _, h = check(D(2026, 10, 15), 1, "sally-s-death-anniversary (hint)")  # below min trust 2: hint only
    assert "more quiet than normal" in h["text"] and "Sally" not in h["text"], h["text"]
    check(D(2026, 10, 15), 6, "sally-s-death-anniversary (hint)", mood="angry")  # a mood that blocks it
    check(D(2027, 10, 15), 6, "sally-s-death-anniversary")  # yearly: next year too
    save, h = check(D(2026, 10, 31), 2, "long-night (hint)")  # long night: min trust 3, not ready
    told(D(2026, 10, 31), save, h)
    assert due(D(2026, 10, 31), save, pip) is None          # hinted once, not repeated that day
    save["trust"] = 3
    assert due(D(2026, 10, 31), save, pip)["hint"] is False # ... but trust went up: now she tells it
    check(D(2026, 10, 31), 3, "long-night")            # stage 2 has a reaction
    check(D(2026, 8, 14), 3, "the-day-the-gods-left")
    check(D(2026, 4, 9), 4, "her-vows (hint)")         # her vows: min trust 5
    check(D(2026, 4, 9), 5, "her-vows")
    check(D(2026, 3, 3), 1, "day-of-plenty")
    check(D(2026, 10, 19), 10, None)                   # an ordinary day
    save, lib = check(D(2026, 11, 20), 4, "the-library-closes")  # once-event, on its day
    check(D(2027, 11, 20), 4, None)                    # ... not the year after
    check(D(2026, 11, 20), 2, "the-library-closes (hint)")  # ... min trust 3
    told(D(2026, 11, 20), save, lib)
    assert due(D(2026, 11, 20), save, pip) is None          # told once, not repeated that day
    save["events_told"]["sally-s-death-anniversary"] = "2025-10-15"
    assert due(D(2026, 10, 15), {**save, "trust": 6}, pip)  # told last year doesn't count
    # a stage written "(not ready)" counts as no reaction
    fake = parse("## Test\nWHEN\n- Date: May 1 (yearly)\nCONTENT\n- Reaction by stage:\n  - Stage 1: (not ready)\n  - Stage 2: acts x / says y\n")
    assert fake[0]["reactions"] == {2: "acts x / says y"}, fake
    print("\nall good. Stage 5 direction for Oct 15:\n" + s5["text"])
