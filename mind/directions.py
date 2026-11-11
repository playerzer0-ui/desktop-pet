"""Stage directions: hidden cues that make a character speak without the user saying anything
(their greeting, idle small talk, a quest question, today's news). They're sent as if the user said them,
so they're wrapped in parentheses and say plainly that they aren't a message from the user.

    direction("Pip says something on her own: it's morning, ...")   the cue to send
    is_direction(message["content"])                                 True for a cue (the diary skips them)
"""
START = "(No message from the user."

def direction(text):
    # in parentheses, so it reads as a stage direction, not as something the user said
    return f"{START} {text} Keep it to 1-2 short sentences and don't mention being told to speak.)"

def is_direction(text):
    return text.startswith(START)
