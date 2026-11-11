"""World events: dated days in a character's world (her events.md). On the day, if she's ready (trust, mood, a
reaction at her stage), she tells it once, in her greeting or next idle nudge. If not, she only shows its hint.

    news = events.due(date, save, character)   # {"id", "text", "mood_after", "hint"} or None
    events.told(date, save, news)              # don't repeat it today
"""
import datetime, re
from engine.save import stage_of
from mind.directions import direction

def parse(text):
    """Every dated '## Name' block in events.md -> a dict (blocks without a Date are skipped)."""
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
    return [e for e in events if (e["month"], e["day"]) == (date.month, date.day) and e["year"] in (None, date.year)]

def due(date, save, character):
    """The event to tell today, or its hint if she isn't ready, or None. Skips what was told today."""
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
        # the name only from stage 3: given it earlier, she said it anyway
        named = f" ({e['name']})" if stage >= 3 else ""
        text = character.fill(f"Something happened in {{name}}'s world today{named}. "
                              "{They} ") + f"{acts.strip()}, and {says.strip()}."
        if stage >= 3:
            text += f" What happened: {e['fact']}"
        text += character.fill(" Only share as much as that. Afterwards {they} feels ") +             f"{e['mood_after']}. Tone: {e['tone']}."
        return {"id": e["id"], "text": text, "mood_after": e["mood_after"], "hint": False}
    for e in waiting:
        text = (character.fill("Today {name} is ") + e["hint"] + character.fill(
            ". Let that show in how {they} acts, but {they} doesn't say why and doesn't mention anything "
            "happening in {their} world."))
        return {"id": e["id"], "text": text, "mood_after": None, "hint": True}
    return None

def stage_direction(date, save, character):
    """Today's event as a stage direction, or None (doesn't mark it told)."""
    news = due(date, save, character)
    return news and direction(character.fill("{name} says something on {their} own. ") + news["text"])

def told(date, save, news):
    """Remember she told (or hinted at) it today. Hints are kept apart: she can still tell it if trust goes up."""
    save.setdefault("events_hinted" if news["hint"] else "events_told", {})[news["id"]] = date.isoformat()


if __name__ == "__main__":  # self-check with Pip's events: python -m mind.events
    from engine.character import Character
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
