"""Friends on the desktop: when other characters are there with her, her greeting and your messages say who's
who, and she wears a mask: her secrets aren't in her prompt at all.
(Told "never say these in front of Pip", Vesper still let them slip: a small model leaks its prompt.)
"""
from engine.character import folder_of, is_npc
from progress import roster, trust

GET_ALONG = 5  # days on the desktop together before two strangers get along well (fewer: still getting to know)

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
            return fill(f"{self._who([name])} is on the desktop with {{them}} today, and has just "
                f'greeted the user, saying: "{words}" Now {{name}} greets the user too, as {{name}}, in {{their}} own '
                f"words and {{their}} own way: {{they}} never repeats or copies {name}'s greeting, and can react to it.")
        introduce = roster.introduce(self.character, self.names)
        if introduce:
            return introduce + "."
        return fill(f"{self._who(self.names)} {self._are} on the desktop with {{them}} today too, but this greeting "
                    "is {their} own, to the user.")

    def known(self, name):
        """How well she knows `name`: "friend" (from before the desktop: one invited the other, or an NPC who
        comes in her story), else how many days they've shared the desktop before today (roster.json)."""
        other = folder_of(name)
        if not other or is_npc(other) or is_npc(self.character.folder) or roster.knew_before(self.character.folder, other):
            return "friend"
        return roster.days_before(self.character.folder, other)

    def _who(self, names):
        """The others as her greeting names them, like "{Their} friend Vesper" or "Ruby, whom {they} has never met
        before today". (Each still has {their} etc. in it, for fill.)"""
        friends = [n for n in names if self.known(n) == "friend"]
        parts = []
        if friends:
            parts.append(("{Their} friend " if len(friends) == 1 else "{Their} friends ") + " and ".join(friends))
        for n in names:
            days = self.known(n)
            if days == "friend":
                continue
            if days == 0:
                parts.append(f"{n}, whom {{they}} has never met before (a stranger: they meet for the first time today),")
            elif days < GET_ALONG:
                parts.append(f"{n}, whom {{they}} has only met here a few times and is still getting to know,")
            else:
                parts.append(f"{n}, whom {{they}} has spent many days with here and gets along well with,")
        text = " and ".join(parts).rstrip(",")
        return text[0].upper() + text[1:]

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
            f"and what is the user's. "
            # (asked about Ruby, whom she only knows from the desktop, Pip said "my best friend, always ready to chat
            #  about baking", and Vesper "she helps me with the baking stuff")
            f"About {others}, {{they}} knows only what {{their}} own background says and what was said in this chat: "
            f"{{they}} never makes up how they met, a shared past, or what {others} likes. If {{their}} background "
            f"doesn't say how {{they}} knows {others}, they have only ever met here, on the user's desktop, and "
            f"{{they}} says so.{self._closeness()})")

    def _closeness(self):
        """For the note: how well she knows each one she only knows from the desktop ("" if all are old friends)."""
        said = []
        for n in self.names:
            days = self.known(n)
            if days == "friend":
                continue
            if days == 0:
                said.append(f"{{name}} and {n} have never met before today: they are strangers, polite and curious "
                            "about each other, not friends yet.")
            elif days < GET_ALONG:
                said.append(f"{{name}} has shared the desktop with {n} on a few days before, so they are still getting "
                            "to know each other: friendly, but not close yet.")
            else:
                said.append(f"{{name}} has shared the desktop with {n} on many days, so they get along well now and "
                            "are comfortable with each other.")
        return (" " + " ".join(said)) if said else ""

    @property
    def _are(self):
        return "is" if len(self.names) == 1 else "are"
