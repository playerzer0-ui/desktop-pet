"""Where a character's sentences end, so "Mr. Halloway" or "St. Raos" isn't cut in two.
Used by the speech bubble (one sentence per page) and by pet.trim_to_sentence (a reply cut off at max_tokens).

    ends("Mr. Halloway is kind. He'll take me to St. Raos.")   ->  [the index after "kind.", the index after "Raos."]
    first_end(text, final=False)   while a reply is still streaming in: None if the end can't be told apart yet

A "." isn't an end after a title or short form (Mr. Dr. St. e.g. ...), after a single capital initial
("J. R. Tolkien"), or when the next word starts with a small letter ("I was... thinking").
"""
import re

PUNCTUATION = re.compile(r"[.!?…~]+[\"')*]*(?=\s|$)")  # the end of a sentence, with any closing quote or *
ABBREVIATIONS = {
    "mr", "mrs", "ms", "mx", "dr", "st", "mt", "jr", "sr", "prof", "rev", "fr", "sgt", "capt", "lt", "col", "gen",
    "gov", "pres", "sen", "rep", "hon", "vs", "approx", "dept", "est", "fig", "vol", "e.g", "i.e", "cf",
}

def ends(text, final=True):
    """Every place a sentence ends in text: the index just after its punctuation and the spaces after it.
    final = text is complete. While it's still streaming in (final=False), an end at the very end of the text
    isn't counted yet: the next word decides whether it really is one."""
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
    """Where the first sentence in text ends (see ends), or None."""
    found = ends(text, final)
    return found[0] if found else None

def _is_end(text, m, after):
    if text[after:after + 1].islower():
        return False  # "I was... thinking", "Mr. smith": the sentence goes on
    if m.group().rstrip("\"')*") != ".":
        return True   # ! ? … or "..." always end one
    word = re.search(r"([A-Za-z]+(?:\.[A-Za-z]+)*)$", text[:m.start()])
    if not word:
        return True
    word = word.group(1)
    return not (word.lower() in ABBREVIATIONS or (len(word) == 1 and word.isupper()))
