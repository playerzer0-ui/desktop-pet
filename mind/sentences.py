"""Where sentences end, so "Mr. Halloway" or "St. Raos" isn't cut in two. Used by the speech bubble and pet.py.

    ends("Mr. Halloway is kind. He'll take me to St. Raos.")   ->  [index after "kind.", index after "Raos."]
"""
import re

PUNCTUATION = re.compile(r"[.!?…~]+[\"')*]*(?=\s|$)")  # with any closing quote or *
ABBREVIATIONS = {
    "mr", "mrs", "ms", "mx", "dr", "st", "mt", "jr", "sr", "prof", "rev", "fr", "sgt", "capt", "lt", "col", "gen",
    "gov", "pres", "sen", "rep", "hon", "vs", "approx", "dept", "est", "fig", "vol", "e.g", "i.e", "cf",
}

def ends(text, final=True):
    """Index after each sentence end. final=False while streaming: an end at the very end isn't counted yet."""
    found = []
    for m in PUNCTUATION.finditer(text):
        after = len(text) - len(text[m.end():].lstrip())  # past the spaces
        if after == len(text) and not final:
            break  # can't see the next word yet
        if not _is_end(text, m, after):
            continue
        found.append(after)
    return found

def first_end(text, final=True):
    found = ends(text, final)
    return found[0] if found else None

def _is_end(text, m, after):
    if text[after:after + 1].islower():
        return False  # "I was... thinking"
    if m.group().rstrip("\"')*") != ".":
        return True   # ! ? … always end one
    word = re.search(r"([A-Za-z]+(?:\.[A-Za-z]+)*)$", text[:m.start()])
    if not word:
        return True
    word = word.group(1)
    return not (word.lower() in ABBREVIATIONS or (len(word) == 1 and word.isupper()))  # "Mr." or "J. R."
