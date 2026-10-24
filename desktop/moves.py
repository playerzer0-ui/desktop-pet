"""Pip's animations, all made from her 9 sprites by squashing, stretching, tilting and moving them.

    PRESETS     one-off moves (hop, bow, shiver...): how long they take, and her shape at each moment
    idle_shape  how she breathes/fidgets while standing, depending on her mood
    for_action  which move and emote fit an *action* she wrote, like *hides behind her sleeves*
    MOOD_MOVES  the move and emote to use when her reply had no action that matched

A shape is (stretch sideways, stretch upward, tilt in degrees, shift right, shift down), in pixels at 3x size.
Tweak freely: every number here is just "how it looks".
"""
import math, random, re

def smooth(p):
    p = max(0.0, min(1.0, p))
    return p * p * (3 - 2 * p)

def held(p, ramp=0.25):
    """0 -> 1, stays at 1, -> 0: for moves that lean into a pose, hold it, and come back."""
    return smooth(p / ramp) * smooth((1 - p) / ramp)

def hop(p):        # a big squashy jump: crouch, fly, land
    if p < 0.2:
        k = smooth(p / 0.2)
        return 1 + 0.12 * k, 1 - 0.15 * k, 0, 0, 0
    if p < 0.75:
        q = (p - 0.2) / 0.55
        return 0.9, 1.12, 0, 0, -40 * math.sin(math.pi * q)
    k = 1 - (p - 0.75) / 0.25
    return 1 + 0.18 * k, 1 - 0.2 * k, 0, 0, 0

def pop(p):        # a startled little jump
    q = math.sin(math.pi * p)
    return 1 - 0.06 * q, 1 + 0.1 * q, 0, 0, -14 * q

def giggle(p):     # three quick tiny bounces
    q = (p * 3) % 1
    c = math.cos(2 * math.pi * q)
    return 1 + 0.05 * c, 1 - 0.05 * c, 0, 0, -6 * math.sin(math.pi * q)

def bow(p):        # bends down, holds, comes back up
    k = held(p, 0.3)
    return 1 + 0.05 * k, 1 - 0.14 * k, 0, 0, 0

def nod(p):        # two little dips
    k = abs(math.sin(2 * math.pi * p))
    return 1 + 0.02 * k, 1 - 0.07 * k, 0, 0, 0

def headshake(p):  # quick left-right wobble
    return 1, 1, 6 * math.sin(4 * math.pi * p) * (1 - p), 0, 0

def tilt(p):       # leans to one side and holds (curious)
    return 1, 1, 9 * held(p), 0, 0

def shiver(p):     # fast side-to-side jitter
    return 1, 1, 0, 3 * math.sin(70 * p) * (1 - 0.4 * p), 0

def shrink(p):     # squashes down small (flustered, hiding), holds, pops back
    k = held(p, 0.2)
    return 1 + 0.08 * k, 1 - 0.22 * k, 0, 0, 0

def sigh(p):       # slow sink, slow rise
    k = math.sin(math.pi * p)
    return 1 + 0.03 * k, 1 - 0.09 * k, 0, 0, 0

def sway(p):       # gentle rocking (humming, remembering)
    return 1, 1, 5 * math.sin(4 * math.pi * p) * math.sin(math.pi * p), 0, 0

def stretch(p):    # stretches tall, then settles with a squash
    if p < 0.6:
        k = held(p / 0.6, 0.35)
        return 1 - 0.1 * k, 1 + 0.16 * k, 0, 0, 0
    k = math.sin(math.pi * (p - 0.6) / 0.4)
    return 1 + 0.1 * k, 1 - 0.1 * k, 0, 0, 0

def bonk(p):       # lunges at the screen, smacks into the glass, wobbles back
    if p < 0.3:
        k = smooth(p / 0.3)
        return 1 + 0.18 * k, 1 + 0.18 * k, 0, 0, 0
    if p < 0.4:
        return 1.32, 0.86, 0, 0, 0
    q = (p - 0.4) / 0.6
    k = 1 - smooth(q)
    return 1 + 0.12 * k, 1 - 0.08 * k, 7 * math.sin(10 * q) * k, 0, 0

def stomp(p):      # two hard squashes
    q = (p * 2) % 1
    k = max(0.0, 1 - q * 3)
    return 1 + 0.15 * k, 1 - 0.18 * k, 0, 0, 0

PRESETS = {  # name: (seconds, shape at progress 0..1)
    "hop": (0.9, hop), "pop": (0.4, pop), "giggle": (0.9, giggle), "bow": (1.3, bow), "nod": (0.7, nod),
    "headshake": (0.8, headshake), "tilt": (1.6, tilt), "shiver": (1.2, shiver), "shrink": (1.8, shrink),
    "sigh": (1.8, sigh), "sway": (2.4, sway), "stretch": (1.6, stretch), "bonk": (1.4, bonk),
    "stomp": (0.8, stomp),
}

KEYWORDS = [  # (words in her *action*, move, emote): the first that matches wins, so the order matters
    (r"\b(bump|bonk|smack|hit|thud)", "bonk", "dizzy"),
    (r"\breach.*\b(screen|glass)", "bonk", "dizzy"),  # reaching out for you always ends at the glass
    (r"\b(gasp|startl|surpris|widen|flinch)", "pop", "exclaim"),
    (r"\byawn", "stretch", "zzz"),
    (r"\bstretch", "stretch", None),
    (r"\b(bow|curts|kneel|pray|clasp)", "bow", "sparkle"),
    (r"\b(hide|hiding|sleeve|blush|fluster|shrink|cover|squeak)", "shrink", "heart"),
    (r"\b(shiver|trembl|shudder|shak(e|es|ing) (with|from)|cower)", "shiver", "sweat"),
    (r"\b(stomp|huff|pout|cross(es)? her arms|glare|scowl)", "stomp", "anger"),
    (r"\bshak(e|es|ing) her head", "headshake", None),
    (r"\bnod(?!(s|ding)? off)", "nod", None),  # (nodding off is falling asleep: the sleep line below)
    (r"\b(giggl|laugh|chuckl|snicker|wave)", "giggle", "note"),
    (r"\b(jump|bounc|hop|twirl|spin|clap|cheer|beam)", "hop", "sparkle"),
    (r"\b(tilt|puzzl|ponder|frown|blink|confus|wide eyes|stare|wonder)", "tilt", "question"),
    (r"\b(hum|sing|sway|rock)", "sway", "note"),
    (r"\b(sigh|droop|slump|lower|sniff|wipe)", "sigh", None),
    (r"\b(sleep|doze|nod(s|ding)? off|drows)", "sigh", "zzz"),
]

MOOD_MOVES = {  # mood: (move, emote) when her reply had no action that matched
    "happy": ("hop", "note"), "sad": ("sigh", None), "worried": ("tilt", "sweat"), "scared": ("shiver", "exclaim"),
    "angry": ("stomp", "anger"), "regretful": ("sigh", "sweat"), "nostalgic": ("sway", "sparkle"),
    "bored": ("sigh", "zzz"), "neutral": (None, None),
    "injured": ("shiver", "sweat"),  # (a story mood: Vesper's day 3)
}

def for_action(action):
    """(move, emote) for an action like 'tilts her head curiously', or (None, None) if nothing fits."""
    action = action.lower()
    for words, move, emote in KEYWORDS:
        if re.search(words, action):
            return move, emote
    return None, None

def idle_shape(mood, t):
    """How she stands around (breathing, fidgeting) in this mood, at time t in seconds."""
    def breathe(period, amount):
        b = math.sin(2 * math.pi * t / period)
        return 1 - amount * b, 1 + amount * b
    if mood == "happy":       # bouncy
        sx, sy = breathe(1.6, 0.03)
        return sx, sy, 0, 0, -2 * abs(math.sin(math.pi * t / 1.6))
    if mood in ("sad", "regretful", "injured"):  # droopy, slow
        sx, sy = breathe(4.0, 0.012)
        sag = 0.03 if mood == "sad" else 0.02
        return sx * (1 + sag / 2), sy * (1 - sag), 0, 0, 0
    if mood == "scared":      # tiny fast jitters
        sx, sy = breathe(0.9, 0.02)
        return sx, sy, 0, random.uniform(-1.2, 1.2), 0
    if mood == "worried":     # fidgety little sway
        sx, sy = breathe(2.0, 0.015)
        return sx, sy, 1.5 * math.sin(2 * math.pi * t / 1.3), 0, 0
    if mood == "angry":       # tense, quick breaths
        sx, sy = breathe(1.0, 0.025)
        return sx, sy, 0, 0, 0
    if mood == "bored":       # slow sway, slow breath
        sx, sy = breathe(3.5, 0.02)
        return sx, sy, 3 * math.sin(2 * math.pi * t / 5), 0, 0
    if mood == "nostalgic":   # gentle sway
        sx, sy = breathe(3.0, 0.015)
        return sx, sy, 2 * math.sin(2 * math.pi * t / 3.5), 0, 0
    sx, sy = breathe(2.6, 0.015)  # neutral
    return sx, sy, 0, 0, 0
