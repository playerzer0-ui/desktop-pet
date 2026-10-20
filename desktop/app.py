"""Pip as a real desktop pet.

    python main.py

Click her to talk, right-click for the menu, drag her anywhere (she falls back to the floor).
Her mind is session.py (the same as the terminal version), run by brain.py on its own thread.
"""
import sys, time
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QMenu
import trust
from desktop.body import Body
from desktop.brain import Brain
from desktop.bubble import Bubble, InputBox, GOLD, ROSE, GRAY

TICK_MS = 5000       # how often she checks whether she wants to speak up on her own
SQUISH_EVERY = 0.13  # seconds between talking squishes (one per bit of speech, but not faster than this)
STAGES = {1: "Guarded caretaker", 2: "Learning to receive", 3: "Admitting the silence",
          4: "Naming why she left", 5: "The free blessing"}  # from character/pip/events.md

class App:
    def __init__(self):
        self.body, self.bubble, self.input, self.brain = Body(), Bubble(), InputBox(), Brain()
        self.ready = False
        self.leaving = False
        self.last_squish = 0.0

        self.body.moved.connect(self.follow)
        self.body.clicked.connect(self.talk)
        self.body.menu_requested.connect(self.menu)
        self.input.submitted.connect(self.send)
        self.input.closed.connect(self.release)
        self.brain.ready.connect(self.on_ready)
        self.brain.speaking.connect(self.on_speaking)
        self.brain.piece.connect(self.on_piece)
        self.brain.spoke.connect(self.on_spoke)
        self.brain.closed.connect(self.on_closed)
        self.brain.failed.connect(self.on_failed)

        self.ticker = QTimer(timeout=self.tick)
        self.release_timer = QTimer(singleShot=True, timeout=self.release)

        self.body.show()
        self.follow()
        self.bubble.say("*rubs her eyes sleepily*",
                        note=self._note("waking up… (after you edit her persona or lore, this takes about 30 s once)", GRAY))
        self.brain.start()

    # --- you ---

    def talk(self):
        if self.leaving:
            return
        self.body.hold(True)
        self.input.open_at(self.body.head())
        self.follow()

    def send(self, text):
        if not self.ready:
            self.bubble.say("*still waking up…*", stay=3)
            return
        self.brain.say(text)

    def release(self):
        """Let her wander again, unless you're typing or she's still talking."""
        if not self.input.isVisible() and not self.brain.busy:
            self.body.hold(False)

    def menu(self, where):
        menu = QMenu()
        menu.addAction("Talk to her", self.talk)
        menu.addAction("Status", self.status)
        menu.addAction("What she remembers", self.memories)
        menu.addSeparator()
        menu.addAction("Say goodbye", self.leave)
        menu.exec(where)

    def status(self):
        if not self.ready:
            return
        save = self.brain.session.save
        level, stage = save["trust"], trust.stage(save)
        bar = "▰" * level + "▱" * (10 - level)
        nxt = f" · {trust.TRUST_POINTS[level] - save['points']} points to trust {level + 1}" if level < 10 else ""
        self.bubble.say(f"Trust {bar} {level}/10", stay=8, note=self._note(
            f"Stage {stage} · {STAGES[stage]}{nxt}<br>today: talk {save['today']['talk']}/{trust.TALK_CAP} · "
            f"{save['today']['minutes']:.0f} min together · {len(save['quests_done'])} quests done · mood {self.brain.session.mood}",
            GRAY))

    def memories(self):
        if not self.ready:
            return
        entries = self.brain.session.memories
        if not entries:
            self.bubble.say("*tilts her head* We've only just met!", stay=5)
            return
        recent = "<br>".join(f"✎ {m['text']}" for m in entries[-4:])
        self.bubble.say(f"*smiles* I remember {len(entries)} things about you.", stay=12,
                        note=self._note(recent, GRAY))

    def leave(self):
        if self.leaving:
            return
        self.leaving = True
        self.ticker.stop()
        self.input.hide()
        self.body.hold(True)
        if not self.ready:
            QApplication.quit()
            return
        self.bubble.say("*writes in her little diary*", note=self._note("saying goodbye…", GRAY))
        self.brain.close()

    # --- her ---

    def on_ready(self, prompt_was):
        self.ready = True
        self.ticker.start(TICK_MS)
        self.brain.open()

    def on_speaking(self, kind):
        self.body.hold(True)
        self.release_timer.stop()
        self.bubble.start()
        self.follow()

    def on_piece(self, piece):
        self.bubble.add(piece)
        self.follow()
        now = time.time()
        if now - self.last_squish > SQUISH_EVERY:  # she squishes as she talks
            self.last_squish = now
            self.body.squish(0.7)

    def on_spoke(self, turn):
        self.body.set_mood(turn.mood)
        notes = []
        if turn.kind == "quest":
            notes.append(self._note("✦ She's curious about your world. Answer her to earn her trust!", GOLD))
        if turn.quest_done:
            notes.append(self._note("✦ Quest complete: she learned something about your world", GOLD))
        if turn.trust_after > turn.trust_before:
            notes.append(self._note(f"♥ Pip trusts you more · trust {turn.trust_after}/10", ROSE))
        if turn.stage_up:
            notes.append(self._note(f"✻ Stage {trust.stage_of(turn.trust_after)}: she'll open up more next time", ROSE))
        self.bubble.finish("<br>".join(notes))
        self.body.squish(1.0)
        self.follow()
        self.release_timer.start(int((4 + len(turn.reply) / 14) * 1000))  # stand still while you read

    def on_closed(self, notes):
        said = f"✎ She'll remember {len(notes)} new thing{'s' if len(notes) != 1 else ''} from today" if notes else ""
        self.bubble.say("*waves goodbye* See you soon!", note=self._note(said, GRAY), stay=3)
        self.body.squish(1.0)
        QTimer.singleShot(2500, QApplication.quit)

    def on_failed(self, error):
        print(error, file=sys.stderr)
        self.bubble.say("*looks confused* Something went wrong…", stay=8,
                        note=self._note(error.strip().splitlines()[-1], GRAY))
        if self.leaving:
            QTimer.singleShot(2500, QApplication.quit)

    # --- every few seconds, and whenever she moves ---

    def tick(self):
        if self.ready and not self.leaving and not self.input.isVisible():
            self.brain.tick()

    def follow(self):
        """Keep the input box above her head, and the bubble above that."""
        head = self.body.head()
        if self.input.isVisible():
            self.input.follow(head)
            head = head - QPoint(0, self.input.height() + 6)
        self.bubble.follow(head)

    @staticmethod
    def _note(text, color):
        return f'<span style="color:{color}">{text}</span>' if text else ""

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pip = App()  # (kept in a variable so it isn't garbage-collected)
    sys.exit(app.exec())
