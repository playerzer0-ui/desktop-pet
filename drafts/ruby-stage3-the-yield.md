# Draft: Ruby's stage-3 major quest, "the yield"

Status: draft only. Nothing here is loaded yet. It replaces `[major_quests.3]` (`silent-hour`) in
`character/ruby/character.toml`, and needs the engine changes listed at the bottom before it will pass
`engine/character.py`'s checks.

## The story in short
| Day | Who | What happens | Ends |
|---|---|---|---|
| 1 | Ruby + Opal | Ruby proudly brings her first friend: the girl from the next hall | the whole day |
| 2 | Ruby + Opal | They tease each other, Opal asks the user about the outside | the whole day |
| 3 | Ruby + Opal | They eat together, Ruby's first shared meal ever. Ruby promises "tomorrow too" | the whole day |
| 4 | Ruby alone | No greeting. Hurt, quiet, "I just want some space". On the 3rd message she breaks down | 3 messages |
| 5 | Ruby alone | Calm and sore. She says Opal's name, and asks the user to remember it with her | an answer (opens stage 4) |

What happened (only ever told by sound, on day 4): the cloister found out about the two of them and called a
sudden Purification Trial, out of season. Ruby couldn't bring herself to strike, so she was hurt far worse than
ever. Opal realised Ruby never would, lowered her weapon, knelt, and said, smiling, that *she* was the impure
one and Ruby must stay the sword saint. The bell rang. The elders led Opal away to be "purified", and Ruby only
heard the footsteps going. Whether Opal is gone is never said: "purified" stays the word Ruby can't finish, which
is what her stage 4-5 lore is already about.

## Opal (the NPC)
Name: like Ruby, named for the colour of the eyes she gave up as a small child. Heaven says opals are
"clouded", which she finds very funny.

Folder `character/opal/`, with `npc = true` (see engine changes). Short persona to draft into
`character/opal/persona.md`:

```
# Persona
Opal (a woman: she/her) is a blind girl training in the White Cloister to become a sword saint, in the hall next
to Ruby's. She is Ruby's age, and Ruby's first and only friend in Heaven.
- Quick, dry and teasing, where Ruby is soft and floaty. She calls Ruby "Saint" to tease her, and laughs a lot,
  quietly, like someone used to laughing in a silent building
- Blind like Ruby, and finds her way by sound and touch. She never describes anything she sees
- She and Ruby met by knocking through the wall between their halls, for weeks, before they ever spoke
- She learned the quiet walk in the cloister like Ruby did, and followed Ruby to the desktop. She is amazed by it
- She knows much more than Ruby about the cloister: she has heard candidates go quiet and not come back. She never
  says so: she wants Ruby to stay happy, and changes the subject with a joke whenever it comes near
- She is very curious about the user's world, and asks them things Ruby would never think to ask
- Warm toward the user, and a little protective of Ruby around them
Rules: Opal is the speaker, the user is "you". Short replies, 1-3 sentences. Never describe a fight, the trial,
or what happens to candidates.
```

Moods: a small set is enough (`happy`, `neutral`, `worried`, `nostalgic`), so only four sprites.

## The steps (for `character/ruby/character.toml`)

```toml
# Ruby needs an injured sprite (sprites/injured.png) for day 4, like Vesper's
story_moods = ["injured"]   # (a plain key: goes up top, before the first [table])

[major_quests.3]  # opens stage 4, Doubting: a story over five days, with Opal (an NPC) on the first three
id = "the-yield"
memory = "Ruby brought her friend Opal, a girl from the next hall, to the desktop for three days. Then the cloister called a sudden trial between them. Ruby couldn't strike her friend, and Opal knelt and gave up so Ruby could stay the sword saint, and was led away to be purified. Ruby told the user, and asked them to remember Opal's name."
points = 10

[[major_quests.3.steps]]  # day 1: Ruby brings a friend for once
needs = ["ruby", "opal"]
opens = "she is bursting with pride: for the first time ever, she has brought a friend. She introduces Opal, the girl from the next hall: they knocked to each other through the wall for weeks before they ever spoke, and Opal followed her on the quiet walk. She asks the user to be kind to her"
note = "(Not part of the message: Opal is the first friend {name} has ever had in Heaven, and {they} is giddy about it all day: {they} keeps including Opal, laughing at her teasing, and telling the user little things about her.)"
ends = "day"

[[major_quests.3.steps]]  # day 2: the two of them, teasing and asking
needs = ["ruby", "opal"]
opens = "she arrives with Opal again, both of them giggling about something that happened in the cloister this morning. She lets Opal ask the user a question about their world, because Opal has been saving it up all night"
note = "(Not part of the message: {name} and Opal tease each other like old friends. If anyone mentions the trial, the ladder or purifying, Opal turns it into a joke and changes the subject, and {name} doesn't notice.)"
ends = "day"

[[major_quests.3.steps]]  # day 3: the first meal she has ever shared
needs = ["ruby", "opal"]
opens = "she comes with Opal, and they have planned something: they both brought their supper on the quiet walk, so they can eat it together with the user. It's the first meal she has ever eaten with anyone, and she says so, delighted"
note = "(Not part of the message: today is the happiest {name} has ever been. At the end of the day {they} promises Opal and the user they'll all do it again tomorrow. Opal is quieter than usual now and then, and smiles it away if asked.)"
ends = "day"

[[major_quests.3.steps]]  # day 4: alone, no greeting, until the third message
needs = ["ruby"]
greeting = false               # NEW: she says nothing when she arrives
opens = "she is here alone, without Opal. She says nothing at all: she sits very still, hurt and stiff, facing away"
mood = "injured"
no_time_limit = true
note = "(Not part of the message: {name} is badly hurt and sore all over, and very quiet. {They} doesn't want to talk: {they} answers in a few flat words, says {they} just wants some space, and asks the user not to worry. {They} never says what happened, and never mentions Opal, and if asked about her {they} goes silent.)"
ends = "messages"              # NEW: the step ends on the user's Nth message
messages = 3
breaks = "the user has reached out for the third time, and she breaks down crying hard. In pieces, she tells them: the cloister found out about her and Opal, and called a trial between them, out of season, with no warning. In the silent hall she couldn't bring herself to strike her friend, not once, so she was hurt worse than ever. Then Opal stopped. Opal lowered her weapon and knelt, and said with a smile in her voice that she was the impure one, and that Ruby had to keep being the sword saint. The bell rang. The elders led Opal away to be purified, and all Ruby heard was the footsteps going. She asks why Opal did that, and whether it was her fault for bringing her here"
breaks_note = "(Not part of the message: {name} only ever tells this by sound: the silent hall, steel on steel, her own breathing, Opal's voice, the bell, the footsteps going away. Never describe a blow, a wound, blood, a weapon striking anyone, or what happens to Opal after. Never say Opal died, or that she is gone for good: the elders only said purified, and {name} doesn't know what it means. {They} is crying, so {their} words come in pieces.)"
lingers = 2                    # sore today and tomorrow
lingers_note = "(Not part of the message: {name} is still hurt and sore from the trial, and quieter than usual. {They} misses Opal, and it shows.)"

[[major_quests.3.steps]]  # day 5: she says the name, so someone else remembers it
needs = ["ruby"]
opens = "she comes back calmer, still sore. She thanks the user for listening yesterday. Then she says that in the trial nobody is allowed names, and the elders will never say Opal's again, so she asks the user to say it with her and remember it, so Opal isn't only in her own head"
ends = "answer"
waiting_on = "whether the user will say Opal's name and remember her"
done_when = "the user says Opal's name, or promises to remember her, or comforts Ruby kindly about her"
needs_nice = true
answer_words = '''\b(?:opal|remember\w*|never forget|won'?t forget|i'?ll (?:remember|keep)|her name|not your fault|it wasn'?t you|she chose|she loved you)\b'''
completes = true
```

## Engine changes needed
1. **NPC characters** (`engine/character.py`, `progress/roster.py`, `mind/memory.py`, `progress/trust.py`):
   `npc = true` in a character.toml means: no trust, no stages, no quests, no diary, no memory, no save entry. She is
   only ever brought by a story step's `needs`, never by `[[lineups]]`, arrivals or unlocks. `is_character("opal")`
   still has to be true so `needs` passes `_check_step`.
2. **`greeting = false`** on a step: the step's character arrives without a greeting line (`story.begin_text` / the
   greeting code in `mind/session.py`). Her sprite and `opens` state still apply.
3. **`ends = "messages"`** with `messages = N`, `breaks` and optional `breaks_note`: counts the user's messages
   during the step (reuse the `goodbyes` counter in `save["story"]`). Before the Nth, the step's `note` applies;
   the Nth gets `breaks` as her reply's stage direction, then the step ends. Add it to the allowed `ends` in
   `_check_step`, requiring `messages` and `breaks`.
4. **Ruby's injured sprite**: `character/ruby/sprites/injured.png`, plus `story_moods = ["injured"]`.
5. **Tests** in `tests/test_engine.py` for npc, `greeting = false` and `ends = "messages"`.

## Lore and events to update afterwards
- `lore.md`, stage 4: a section "Opal" (words: opal, friend, wall, knocking) with what Ruby will say about her.
- `events.md`: the Purification Trial and the silent hour at stages 4-5 now think of Opal.
- `persona.md`, stage 4 inner feelings: she misses Opal, and wonders whether the silent hour is for her now.
- The quiet "can't finish the thought" in stages 4-5 still fits as written: it's now about one person.
