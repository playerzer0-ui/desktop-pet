"""Stage directions: hidden cues that make a character speak on her own (greeting, idle talk, quests, news).
They're sent as a user message, so they say plainly that they aren't one.
"""
START = "(No message from the user."

def direction(text):
    return f"{START} {text} Keep it to 1-2 short sentences and don't mention being told to speak.)"

def is_direction(text):
    return text.startswith(START)
