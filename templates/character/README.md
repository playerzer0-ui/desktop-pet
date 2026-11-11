# How to add a new character

This folder is a blank character to copy. It lives outside `character/` on purpose: the game treats any folder in
`character/` that has a `character.toml` as a real character (and the build packs all of `character/` into the game),
so nothing here is ever loaded until you copy it there.

Throughout the template, `NAME` is her name, `FOLDER` is her folder, and `CHANGE` marks text to rewrite.
Pip (`character/pip/`) and Vesper (`character/mira/`) are the full worked examples: open them side by side.

## 1. Copy the folder

```
templates/character/   ->   character/<folder>/
```

The folder name is her id everywhere in code and files (saves, roster, duets, story steps): lowercase, no spaces, and
never rename it later (her save file is `<folder>.json`). It doesn't have to be her name: Vesper's folder is `mira`.

Then delete this README from the copy (it isn't read, but it's clutter), and search the copy for `NAME`, `FOLDER` and
`CHANGE` until none are left.

## 2. What each file is

| File | What it is | Read by |
|---|---|---|
| `character.toml` | Everything that isn't prose: name, moods, example chats, idle topics, small quests, major quests, daily time | `character.py` |
| `persona.md` | Who she is and how she talks, in `# Stage N` blocks | her prompt (`pet.py`) |
| `lore.md` | What she knows about her world, in `# Stage N` blocks | her prompt (`pet.py`) |
| `events.md` | Her arc table, her moods, and dated world events | `events.py` |
| `sprites/<mood>.png` | One picture per mood | `desktop/body.py` |

### Stage blocks (`persona.md`, `lore.md`)

Trust runs 1-10, and two trust levels make a stage (1-2 is stage 1, ... 9-10 is stage 5). At stage N she gets every
`# Stage 1` ... `# Stage N` block, and sections with the same `##` heading are merged, so you can add to "## Bakery"
in a later stage without repeating it. Anything she must not say yet simply goes in a later block.

A line that a later stage replaces can retire there, so the top stage doesn't carry both:

```
- [until stage 4] Someone dangerous pays her to watch the chapel, and she won't say who
```

### Short lore, details on demand (`lore.md`)

Her prompt is read once and cached, so it should stay small: every token in it is one less for the chat. A lore
section can be split into a summary that's always in her prompt and details that only come in when it comes up:

```
## Bloodcult
words: bloodcult, lind, cult, brawl, resurrect
in short: the faction of chaos and violence. Boss: Lind (a man: he/him)
- details, as many lines as you like...
```

- `words:` the words or phrases that bring the details in (plurals and 's count too), checked against your
  message and anything the game has her talk about (idle topics, quests, events, duets). Pick names and the words
  people would really use: "who brings people back?" needs `resurrect`, not just `lind`. Leave out everyday words
  ("friend", "fight", "leave", "warm"): "I had a fight with my sister" would bring in the Bloodcult
- `in short:` always in her prompt. Put the facts she must never get wrong here (names, he/she, who did what): if
  no word matches, the summary is all she has
- the details stay for her next 2 replies (for follow-up questions), at most 3 sections at once
- a later stage block can add to the same `## Section`: more words, another `in short:`, more details
- a section without `words:` stays whole in her prompt (fine for small, always-needed ones, like the Overview)

`python -m desktop.check` warns about a section with `words:` but no `in short:` (her prompt would know nothing
about it).

Lines can also be dated, for something that changes on a real day (see the library in `character/pip/lore.md`):

```
- [until 2026-11-20] The library is still open
- [from 2026-11-20] The library was torn down on November 20, 2026
```

### Events (`events.md`)

Each `## Name` block with a `- Date:` is one event; the arc table and `## Moods` above them aren't events. On that
date she tells the user what happened, once she's ready (trust and mood), in the reaction for her stage.

- Date: `March 3 (yearly)`, or `January 18, 2027 (once)`
- Scale: background | personal | major
- Source: dream-letter | friend | prayer | public event | rumor
- Reaction by stage: `acts ... / says ...`. Leave out a stage she isn't told yet (she starts at Min trust)

Check `world_bible.md` so her events and lore agree with everyone else's.

### Moods: keep five lists the same

`python -m desktop.check` refuses to start the game until these match:

1. `moods = [...]` in `character.toml`
2. the `- mood: meaning` list in `persona.md` (between `[mood: X]` and "The user never sees these tags")
3. the `## Moods` line in `events.md` (and every event's "Not ready if mood is" / "Mood after")
4. one `sprites/<mood>.png` each
5. `MOOD_MOVES` in `desktop/moves.py` (shared by everyone: only a brand-new mood needs adding there)

A mood only a story step uses (like Vesper's `injured`) goes in `story_moods` instead of `moods`: it needs a sprite
and a `MOOD_MOVES` entry, but not lists 2 and 3.

### Sprites

`sprites/` here has no pictures, only `NEEDED.txt` with the list. Draw one PNG per mood, the same size as Pip's and
Vesper's (open theirs to compare), with a transparent background.

## 3. Her quests (all in `character.toml`)

- **Small quests** (`[quests.N]`): things she's curious about in your world. She asks one now and then and gives a
  little trust when you answer.
- **Major quests** (`[major_quests.1]` to `[major_quests.4]`): one gate at the top of each stage. Trust stops at the
  top of the stage until it's done. Each one is either:
  - **one moment**: she brings it up (`starts`) and judges your replies (`done_when`), like Pip's "thank-you"
  - **a story over several days** (`steps`): like Pip's "run-away" (she leaves, comes back, begs to stay) or
    Vesper's "the-summons" (days with Pip, without her, hurt, and an epilogue)

The template has one of each, with every option written out next to it.

## 4. Fit her into the cast (`character/roster.toml`)

A new character only comes once someone invites her. Copy `roster_entry.toml` from this folder into
`character/roster.toml` (an `[[unlocks]]` entry, and the lineups she can come in), and fill it in.

For a surprise arrival instead (nobody invites her, like Ruby), use an `[[arrivals]]` entry (`who`, `after`,
`at_trust`, `days`) in place of `[[unlocks]]`: once `after` reaches `at_trust`, a clock of `days` starts, and on the
day it runs out she comes on her own (her `first_visit` explains how she got here). The lineups are the same, and she
needs no `invite` or `introduce`.

## 5. Optional: chats with another character (`character/duets/`)

For days she's on the desktop with someone, copy `duet.toml` from this folder to
`character/duets/<folder>-<other folder>.toml` (only one file per pair, in either order).

## 6. Check it

```
python -m desktop.check <folder>
```

It reads her files the way the game does, and lists every mistake (a missing key, a mood that doesn't match, a story
step naming someone who isn't in the cast). "the cast's files are all good" means she's ready. Then:

```
python -m unittest discover tests
```

To meet her without waiting for an invite, start the game on her folder, with a throwaway data folder so your real
saves aren't touched (PowerShell):

```
$env:PET_DATA_DIR = "$env:TEMP\pet-try"; python main.py <folder>
```
