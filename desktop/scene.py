"""Two characters on the desktop at once: Pip and the friend she brought over (friends.py), from the day after the
friend's first visit. Each one is a whole App (desktop/app.py) with her own body, bubble, menu, mind and save, on
her own slot of the model server (llm.py). The scene only makes them get along:

    taking turns   one talks at a time: nobody speaks up (greeting, idle talk, quest, news) while the other is
                   talking or you're typing to her, and you can't open a chat with one while the other is talking
    arriving       side by side, each out of her own portal. Pip greets first (the first day, she introduces her
                   friend: friends.introduce), and once she's done, her friend greets you too, hearing what she said
    leaving        together: Say goodbye to either one, or Pip's time running out, and both go home
                   (the friend has no daily limit of her own here: she stays as long as Pip does)
    closing        the app quits once both have faded away

    scene = Scene([pip, vesper])    # the first one leads: she decides whether they come today, and her time counts
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from desktop.app import App
from desktop.body import SIZE

TICK_MS = 2000   # how often someone may speak up on her own (each tick gives one of them the chance, in turn)
SPACING = SIZE * 1.4  # how far apart they come out of their portals

class Scene:
    def __init__(self, characters):
        self.characters = list(characters)
        self.pets = [App(c, scene=self, slot=i) for i, c in enumerate(self.characters)]
        self.gone = set()   # pets that have faded away
        lead = self.pets[0].body
        for i, pet in enumerate(self.pets[1:], 1):  # (side by side, not out of the same portal)
            pet.body.foot_x = pet.body.target = lead.foot_x - i * SPACING
            pet.body._place()
            pet.follow()
        self.greetings = {}  # what each one said in her greeting (id(pet) -> words), for the ones after her
        self.turn = 0  # whose chance it is first on the next tick
        self.ticker = QTimer(timeout=self.tick)
        self.ticker.start(TICK_MS)

    def others_talking(self, pet):
        """Anyone but `pet` is talking, about to, or being typed to."""
        return any(p.talking or p.input.isVisible() for p in self.pets if p is not pet)

    def may_greet(self, pet):
        """The first one greets first; the others once she has (or once her greeting failed, or she's leaving)."""
        lead = self.pets[0]
        return pet is lead or lead.leaving or (lead.ready and not lead.wants_open and not lead.talking)

    def heard_for(self, pet):
        """(name, words) of the first one's greeting, for the others' greetings to answer, or None."""
        lead = self.pets[0]
        words = self.greetings.get(id(lead))
        return (lead.character.name, words) if pet is not lead and words else None

    def greeted(self, pet, words):
        self.greetings[id(pet)] = words

    def tick(self):
        """Give each one, in turn, the chance to speak up; once one does (or greets you), the rest wait."""
        for i in range(len(self.pets)):
            pet = self.pets[(self.turn + i) % len(self.pets)]
            pet.tick()
            if pet.talking:
                break
        self.turn = (self.turn + 1) % len(self.pets)

    def leave_with(self, pet, going_home):
        """`pet` is going home: so is everyone else (her goodbye, or her time running out)."""
        self.ticker.stop()
        for other in self.pets:
            if other is not pet:
                other.leave(going_home=going_home, following=True)

    def vanished(self, pet):
        self.gone.add(id(pet))
        if len(self.gone) == len(self.pets):
            QApplication.quit()
