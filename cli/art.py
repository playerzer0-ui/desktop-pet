"""Pip's ASCII art for the CLI.

The art is plain text so it's easy to redraw. Colors are added per character:
anything listed in ACCENTS gets that style (styles live in cli/ui.py's THEME), the rest is "robe".
"""

# a hooded priestess, eyes closed, holding Everlily's warm lamp
PRIESTESS = r"""
     .-'''-.
    / .---. \
   / / ^ ^ \ \
  | |       | |
   \ \ `-' / /
    '-.___.-'
  .-'   ,   '-.
 /     (*)     \
/   .--|=|--.   \
\__/   '-'   \__/
  |           |
  |___________|
""".strip("\n")

ACCENTS = {
    "*": "flame", ",": "flame",  # the flame that never goes out
    "=": "lamp",
    "^": "face", "`": "face",    # closed eyes, small smile
}
