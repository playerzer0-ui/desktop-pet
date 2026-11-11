"""Friends on the desktop: when other characters are there with her, her greeting and your messages say who's
who, and she wears a mask: her secrets aren't in her prompt at all.
(Told "never say these in front of Pip", Vesper still let them slip: a small model leaks its prompt.)
"""
from progress import roster, trust

class Company:
    def __init__(self, character, names=()):
        self.character = character
        self.names = list(names)  # the others on the desktop today

    @property
    def masked(self):
        """Her friend is there and she has a public self to show (with_friend_stage)."""
        return bool(self.names and self.character.with_friend_stage)

    def shown_stage(self, save):
        """Her trust stage as she shows it: no higher than with_friend_stage while masked."""
        stage = trust.stage(save)
        return min(stage, self.character.with_friend_stage) if self.masked else stage

    def public(self, save):
        """Her save as she shows it: while masked, without private memories and with trust capped."""
        if not self.masked:
            return save
        shown = self.shown_stage(save)
        private = {self.character.fill(q["memory"]) for q in self.character.major_quests.values() if q["private"]}
        # and her answers to world questions from above the stage she shows
        above = {self.character.fill(f"{{name}} asked about {about}.") for _, st, about in self.character.quests
                 if st > shown}
        memories = [m for m in save.get("memories", [])
                    if not m.get("private") and not any(m["text"].startswith(p) for p in private | above)]
        return dict(save, memories=memories, trust=min(save["trust"], shown * 2))

    def major_due(self, save, major):
        """Her major quest to bring up now, but not a private one while masked."""
        quest = major.active(save)
        if self.masked and quest and quest["private"]:
            return None
        return major.due(save)

    def greeting(self, heard=None):
        """For her greeting: who else is here today, or None. heard = (name, words) of a greeting just before
        hers. The first day, she introduces someone she invited."""
        if not self.names:
            return None
        fill = self.character.fill
        if heard:  # (told only to "greet too", she once repeated it word for word)
            name, words = heard
            return fill(f"{{Their}} friend {name} is on the desktop with {{them}} today, and has just "
                f'greeted the user, saying: "{words}" Now {{name}} greets the user too, as {{name}}, in {{their}} own '
                f"words and {{their}} own way: {{they}} never repeats or copies {name}'s greeting, and can react to it.")
        introduce = roster.introduce(self.character, self.names)
        if introduce:
            return introduce + "."
        friends = "{Their} friend " if len(self.names) == 1 else "{Their} friends "
        return fill(friends) + " and ".join(self.names) + fill(
            f" {self._are} on the desktop with {{them}} today too, but this greeting is {{their}} own, to the user.")

    def note(self):
        """A hidden note on each of your messages to keep who's who straight, or None when she's alone.
        (Without it, "who bakes better?" made Vesper talk as if you were Pip.)"""
        if not self.names:
            return None
        others, are = " and ".join(self.names), self._are
        else_ = "someone else" if len(self.names) == 1 else "other people"
        whose = f"{others}'s" if len(self.names) == 1 else f"each of {others}'s"
        return self.character.fill(
            f"(Not part of the user's message: {others} {are} on the desktop beside {{name}} and can hear everything, "
            f"but this message is from the user, the human who owns the desktop, and {{name}} answers the user. "
            f'In {{their}} reply, "you" is the user. {others} {are} {else_}: when the message is about {others}, '
            f"{{they}} talks about {others} by name. {{They}} never mixes up what is {{their}} own, what is {whose} "
            f"and what is the user's.)")

    @property
    def _are(self):
        return "is" if len(self.names) == 1 else "are"
