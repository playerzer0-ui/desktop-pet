"""How things look: colors, the welcome box, Pip's messages, quest and trust notices, the status bar."""
import io, re, shutil, sys
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich import box
import trust
from cli.art import PRIESTESS, ACCENTS

GOLD, LAVENDER, ROSE, SAGE, GRAY = "#E8B04B", "#B4A7D6", "#D7A1A9", "#9CC5A1", "#7a7a7a"
THEME = Theme({
    "robe": LAVENDER, "flame": f"bold {GOLD}", "lamp": GOLD, "face": ROSE,
    "accent": GOLD, "pip": "default", "action": f"italic {ROSE}", "you": GRAY,
    "dim": GRAY, "good": SAGE, "heart": f"bold {ROSE}",
})
STAGES = {  # from the arc table in character/pip/events.md
    1: "Guarded caretaker", 2: "Learning to receive", 3: "Admitting the silence",
    4: "Naming why she left", 5: "The free blessing",
}
VERBS = ["Praying", "Lighting lamps", "Kneading bread", "Polishing bowls", "Dreamwalking",
         "Brushing her hair", "Counting coins", "Humming", "Tending the flame", "Reading old notes"]
SPINNER = "·✢✳✶✻✽✻✶✳✢"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # the ✻ ▰ ⎿ symbols need it on some Windows terminals
console = Console(theme=THEME, force_terminal=True, color_system="truecolor", legacy_windows=False,
                  width=min(shutil.get_terminal_size().columns, 100), highlight=False)

def art():
    text = Text()
    for i, line in enumerate(PRIESTESS.splitlines()):
        if i:
            text.append("\n")
        for ch in line:
            text.append(ch, style=ACCENTS.get(ch, "robe"))
    return text

def trust_bar(level, width=10):
    return Text("▰" * level, style="accent") + Text("▱" * (width - level), style="dim")

def header(save, prompt_note=None):
    level, stage = save["trust"], trust.stage(save)
    goal = (f"{save['points']} / {trust.TRUST_POINTS[level]} points to trust {level + 1}"
            if level < 10 else f"{save['points']} points · full trust")
    info = Group(Text("✻ ", style="flame") + Text("Welcome back to Pip", style="bold"),
                 Text("Priestess of Everlily, visiting from the Republic", style="dim"),
                 Text(""))
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", no_wrap=True)
    rows.add_column()
    rows.add_row("trust", trust_bar(level) + Text(f"  {level}/10"))
    rows.add_row("stage", Text(f"{stage} · {STAGES[stage]}"))
    rows.add_row("points", Text(goal))
    rows.add_row("together", Text(f"{save['days_logged']} day(s) · {save['messages']} messages"))
    rows.add_row("quests", Text(f"{len(save['quests_done'])} finished"))
    rows.add_row("memories", Text(f"{len(save.get('memories', []))} · /memories to read them"))
    body = Group(info, rows)
    grid = Table.grid(padding=(0, 3))
    grid.add_row(art(), body)
    parts = [Panel.fit(grid, box=box.ROUNDED, border_style="accent", padding=(1, 2))]
    tips = Text("  Type to talk · she speaks up on her own when you're quiet · ", style="dim") + \
        Text("/help", style="accent") + Text(" for commands", style="dim")
    parts.append(tips)
    if prompt_note:
        parts.append(Text("  " + prompt_note, style="dim"))
    return Group(*parts)

def styled(reply):
    """Pip's words, with *actions* in soft italics."""
    text = Text()
    for i, part in enumerate(re.split(r"(\*[^*]+\*)", reply)):
        text.append(part, style="action" if i % 2 else "pip")
    return text

def you(message):
    line = Table.grid(padding=(0, 1))
    line.add_column(no_wrap=True)
    line.add_column()
    line.add_row(Text("›", style="you"), Text(message, style="you"))
    return line

def bubble(reply, kind):
    """Pip's words after her bullet: ● answering you, ◦ speaking on her own, ✦ asking a quest."""
    bullet = {"idle": Text("◦", style="robe"), "quest": Text("✦", style="flame")}.get(kind, Text("●", style="accent"))
    line = Table.grid(padding=(0, 1))
    line.add_column(no_wrap=True)
    line.add_column()
    line.add_row(bullet, styled(reply))
    return line

_live = Console(file=io.StringIO(), theme=THEME, force_terminal=True, color_system="truecolor",
                legacy_windows=False, width=console.width, highlight=False)

def live(reply, kind):
    """Her reply while she's still writing it, as terminal text for the area above the input line."""
    with _live.capture() as captured:
        _live.print(bubble(reply + "▌", kind))
    return captured.get()

def turn(t, verbose=False):
    """Everything printed for one of Pip's replies."""
    out = [bubble(t.reply, t.kind)]

    gained = t.points_after - t.points_before
    notes = []
    if t.kind == "user":
        notes.append(f"felt {t.feeling}")
    elif t.kind == "idle":
        notes.append("spoke on her own")
    elif t.kind == "quest":
        notes.append("asked about your world")
    elif t.kind == "opening":
        notes.append("woke up")
    if gained:
        notes.append(f"+{gained} trust point{'s' if gained > 1 else ''}")
    if verbose:
        notes.append(f"{t.seconds:.1f}s · re-read {t.timings.get('prompt_n', '?')}, "
                     f"reused {t.timings.get('cache_n', '?')} · {t.timings.get('predicted_per_second', 0):.1f} tok/s")
    if notes:
        out.append(Text("  ⎿  " + " · ".join(notes), style="dim"))

    if t.kind == "quest":
        out.append(notice("✦ Quest · Curious about your world",
                          "Pip has never seen your world. Answer her within 30 minutes to earn her trust.", GOLD))
    if t.quest_done:
        out.append(notice("✦ Quest complete", "Pip learned something about your world.", SAGE))
    if t.trust_after > t.trust_before:
        out.append(Text(f"  ♥ Pip trusts you more · trust {t.trust_after}/10", style="heart"))
    if t.stage_up:
        stage = trust.stage_of(t.trust_after)
        out.append(notice(f"✻ Stage {stage} · {STAGES[stage]}",
                          "She'll open up more the next time you open her.", ROSE))
    return Group(*out)

def notice(title, body, color):
    return Panel.fit(Text(body, style="dim"), title=Text(title, style=f"bold {color}"),
                     title_align="left", box=box.ROUNDED, border_style=color, padding=(0, 2))

def status(save, quests_done_today, quest_waiting):
    level = save["trust"]
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", no_wrap=True)
    rows.add_column()
    rows.add_row("trust", trust_bar(level) + Text(f"  {level}/10 · stage {trust.stage(save)} · {STAGES[trust.stage(save)]}"))
    rows.add_row("points", Text(f"{save['points']}" + (f" (trust {level + 1} at {trust.TRUST_POINTS[level]})" if level < 10 else "")))
    rows.add_row("today", Text(f"talk {save['today']['talk']}/{trust.TALK_CAP} · {save['today']['minutes']:.0f} min open · "
                               f"{quests_done_today} quest(s) done"))
    rows.add_row("together", Text(f"{save['days_logged']} day(s) · {save['messages']} messages"))
    rows.add_row("quest", Text("Pip is waiting for your answer" if quest_waiting else "none right now"))
    return Panel.fit(rows, title=Text("status", style=f"bold {GOLD}"), title_align="left",
                     box=box.ROUNDED, border_style="dim", padding=(0, 2))

def toolbar(save, n_ctx, ctx_used, busy_since, verb, now, quest_waiting):
    """The line under the input box (prompt_toolkit formatted text)."""
    if busy_since:
        frame = SPINNER[int((now - busy_since) * 8) % len(SPINNER)]
        return [(f"fg:{GOLD} bold", f" {frame} {verb}… "), (f"fg:{GRAY}", f"({now - busy_since:.0f}s)")]
    level = save["trust"]
    parts = [(f"fg:{GOLD}", " " + "▰" * level), (f"fg:{GRAY}", "▱" * (10 - level)),
             (f"fg:{GRAY}", f"  trust {level} · stage {trust.stage(save)} · "
                            f"talk {save['today']['talk']}/{trust.TALK_CAP} · {save['today']['minutes']:.0f} min · "
                            f"context {ctx_used / n_ctx:.0%}")]
    if quest_waiting:
        parts.append((f"fg:{GOLD} bold", "  ✦ quest: answer Pip"))
    return parts

HELP = [("/status", "trust, points and today's progress"),
        ("/stats", "show or hide reply timings (for testing)"),
        ("/memories", "what Pip remembers about you, and when"),
        ("/clear", "clear the screen"),
        ("/exit", "close Pip (Ctrl+D works too)")]

def memories(entries):
    """Everything Pip remembers, oldest first, with when each memory was made."""
    if not entries:
        return Text("  Pip has no memories of you yet. Answer her questions, and talk a while before you close her.", style="dim")
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", no_wrap=True)
    rows.add_column(no_wrap=True)
    rows.add_column()
    for m in entries:
        icon = Text("◇", style="flame") if m["kind"] == "world" else Text("✎", style="robe")
        rows.add_row(m["when"], icon, Text(m["text"]))
    return Panel.fit(rows, title=Text("what Pip remembers", style=f"bold {GOLD}"), title_align="left",
                     box=box.ROUNDED, border_style="dim", padding=(0, 2))

def diary(notes):
    """The notes Pip just wrote at the end of the sitting."""
    body = Group(*[Text("✎ ", style="robe") + Text(n["text"]) for n in notes])
    return Panel.fit(body, title=Text(f"Pip's diary · {notes[0]['when']}", style=f"bold {LAVENDER}"),
                     title_align="left", box=box.ROUNDED, border_style="robe", padding=(0, 2))

def help_panel():
    rows = Table.grid(padding=(0, 3))
    rows.add_column(style="accent", no_wrap=True)
    rows.add_column(style="dim")
    for cmd, what in HELP:
        rows.add_row(cmd, what)
    return Panel.fit(rows, title=Text("commands", style=f"bold {GOLD}"), title_align="left",
                     box=box.ROUNDED, border_style="dim", padding=(0, 2))
