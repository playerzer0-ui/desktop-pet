# live checks

Checks that run the real model, for what `tests/` can't see: how she writes, what the judge decides, how much
memory the server takes, and how the window feels. Each takes minutes, not seconds, so none of them is part of
`python -m unittest`.

Every run gets a fresh data folder and its own port (8091 and up), so your saves are never touched and the pet
can stay on the desktop meanwhile. Run them from the repo folder with the project's Python (`.venv`). The model
files go in `models/`; `--model gemma` or `--model qwen` picks one (default: the one `engine/config.py` ships),
with the checkpoint count measured for it.

| tool | what it answers |
|---|---|
| `python -m tools.live.chat <scene>` | one scene on one model: her replies, the judge's verdicts, mood, trust, timings |
| `python -m tools.live.compare <scenes...>` | the same scenes on every model, side by side in a Markdown report |
| `python -m tools.live.memory --who pip ruby` | the server's memory over a long sitting, stalls, and when she starts forgetting |
| `python -m tools.live.window` | the real window: wake-up, first words, and how long you can't type after she's done |

`memory` needs `psutil` (`pip install psutil`), which the game itself doesn't.

## scenes

A scene (`scenes/*.json`) is who, an optional save to start from, and what you say:

```json
{"character": "pip", "diary": true, "save": {"trust": 6},
 "messages": ["hello", {"say": "tell them she's boring", "felt": "neutral"}, {"say": "my cat", "done": true}]}
```

`felt` and `done` are what the judge should decide; a run that disagrees is marked MISS. `diary: true` has her
write her diary at the end (it's printed). `greet: false` skips her greeting.

- `judge-cases.json`: messages the judge has got wrong, or must keep getting right
- `pip-hello.json`: a first sitting, ending with her diary
- `ruby-breakdown.json`: day 4 of Ruby's story, the-yield

## reading the numbers

- `window`: "can't type after her last letter" is the wait if you let the bubble type; "if you click to skip" is
  the wait after the model's last word, which is how long the judge holds you up.
  `--offscreen` runs without windows, but its pictures have no text (no fonts offscreen).
- `memory`: watch "private" (Task Manager's Memory column). It should level off; "RE-READ" means the server read
  her whole prompt again (too few checkpoints), and context near 75% is where she starts forgetting old lines.
  `--checkpoints N` tries another count.
