"""Pip as a real desktop pet.

    python main.py

Click her to talk, right-click for the menu, drag her anywhere (she falls back to the floor).
While her mind loads, only a portal sits on the floor; once it's ready she pops out of it and says hello.
Her mind is session.py, run by brain.py on its own thread. The screen never reads her save directly:
after every job the brain sends a snapshot (trust summary, memories), and Status / memories show that.
"""
import sys, time
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QMenu
from character import Character, DEFAULT
from desktop import check, moves
from desktop.status import card as status_card
from desktop.body import Body
from desktop.brain import Brain
from desktop.bubble import Bubble, InputBox, GOLD, ROSE, GRAY

TICK_MS = 5000       # how often she checks whether she wants to speak up on her own
SQUISH_EVERY = 0.13  # seconds between talking squishes (one per few letters typed, but not faster than this)
MOOD_SECONDS = {"happy": 15}  # after she stops talking, a mood lasts this long before she's back to neutral
MOOD_DEFAULT_SECONDS = 35     # (any mood not listed)

class App:
    def __init__(self, character):
        self.character = character  # who's on the desktop (character.py)
        self.body, self.bubble = Body(character.sprites, character.portal), Bubble()
        self.input, self.brain = InputBox(character.name), Brain(character)
        self.ready = False
        self.snap = None    # the latest snapshot from the brain: {"summary": trust.summary(...), "memories": [...]}
        self.leaving = False
        self.last_squish = 0.0
        self.acted = False  # an *action* in her current reply got its own move (else her mood picks one)

        self.body.moved.connect(self.follow)
        self.body.clicked.connect(self.talk)
        self.body.menu_requested.connect(self.menu)
        self.body.vanished.connect(QApplication.quit)
        self.input.submitted.connect(self.send)
        self.input.closed.connect(self.release)
        self.bubble.typed.connect(self.on_typed)
        self.bubble.acted.connect(self.on_acted)
        self.bubble.done.connect(self.on_done)
        self.brain.ready.connect(self.on_ready)
        self.brain.speaking.connect(self.on_speaking)
        self.brain.piece.connect(self.on_piece)
        self.brain.spoke.connect(self.on_spoke)
        self.brain.closed.connect(self.on_closed)
        self.brain.snapshot.connect(self.on_snapshot)
        self.brain.failed.connect(self.on_failed)

        self.ticker = QTimer(timeout=self.tick)
        self.calm_down = QTimer(singleShot=True, timeout=self.settle)
        self.last_reply = 0  # Turn.number of her latest reply (whose mood the calm_down timer settles)

        self.body.show()  # (a portal until she's loaded: on_ready brings her out)
        self.follow()
        self.brain.start()

    # --- you ---

    def talk(self):
        if self.leaving or not self.body.here:
            return
        self.body.hold(True)
        self.input.open_at(self.body.head())
        self.follow()

    def send(self, text):
        self.follow()  # the input box just closed: the bubble goes back to just above her head
        if not self.ready:
            self.bubble.say("*still waking up…*", stay=3)
            self.release()
            return
        self.brain.say(text)

    def release(self):
        """Let her wander again, unless you're typing or she's still talking."""
        if not self.input.isVisible() and not self.brain.busy and not self.bubble.active:
            self.body.hold(False)

    def menu(self, where):
        self.build_menu().exec(where)

    def build_menu(self):
        """Her right-click menu. Status and memories wait while she's talking (they'd cut her reply short)."""
        menu = QMenu()
        menu.addAction("Talk to her", self.talk).setEnabled(self.body.here)
        talking = self.bubble.active or self.brain.busy
        for label, action in (("Status", self.status), ("What she remembers", self.memories)):
            menu.addAction(label, action).setEnabled(not talking)
        menu.addSeparator()
        menu.addAction("Say goodbye", self.leave)
        return menu

    def on_snapshot(self, snap):
        self.snap = snap

    def status(self):
        if not self.snap:
            return
        self.bubble.show_picture(status_card(self.snap["summary"]), stay=8)

    def memories(self):
        if not self.snap:
            return
        entries = self.snap["memories"]
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
        self.body.arrive()  # out of the portal (her opening line is "…" until it's written: she's out by then)
        self.ticker.start(TICK_MS)
        self.brain.open()

    def on_speaking(self, kind):
        self.body.hold(True)
        self.body.think(True)  # a "…" thought icon until her first words show up
        self.calm_down.stop()
        self.acted = False
        self.bubble.start()
        self.follow()

    def on_piece(self, piece):
        self.bubble.add(piece)  # (queued: the bubble shows it a sentence at a time, at reading pace)
        self.follow()

    def on_acted(self, action):
        """She does an *action* (it's not shown as text): act it out with a move and an emote."""
        self.body.think(False)
        move, emote = moves.for_action(action)
        if move:
            self.acted = True
            self.body.play(move)
        self.body.emote(emote)

    def on_typed(self):
        self.body.think(False)
        now = time.time()
        if now - self.last_squish > SQUISH_EVERY:  # she squishes as her words appear
            self.last_squish = now
            self.body.squish(0.7)
        self.follow()

    def on_done(self):
        """Her whole reply has been read: she can wander again, and her mood slowly settles back to neutral."""
        self.release()
        if self.body.mood != "neutral":
            self.calm_down.start(MOOD_SECONDS.get(self.body.mood, MOOD_DEFAULT_SECONDS) * 1000)

    def settle(self):
        """Her mood has lasted long enough: back to neutral, on screen and in her save at the same time."""
        self.body.set_mood("neutral")
        self.brain.settle(self.last_reply)

    def on_spoke(self, turn):
        self.last_reply = turn.number
        self.body.set_mood(turn.mood)
        move, emote = moves.MOOD_MOVES.get(turn.mood, (None, None))
        if not self.acted and move:  # no action of hers matched a move: show how she feels instead
            self.body.play(move)
        if turn.feeling == "nice":
            emote = "heart"  # you were kind to her
        self.body.emote(emote)
        notes = []
        if turn.kind == "quest":
            notes.append(self._note("✦ She's curious about your world. Answer her to earn her trust!", GOLD))
        if turn.quest_done:
            notes.append(self._note("✦ Quest complete: she learned something about your world", GOLD))
        if turn.trust_after > turn.trust_before:
            notes.append(self._note(f"♥ {self.character.name} trusts you more · trust {turn.trust_after}/10", ROSE))
        if turn.stage_up:
            stage, name = turn.stage_after
            notes.append(self._note(f"✻ Stage {stage} · {name}: she'll open up more next time", ROSE))
        self.bubble.finish("<br>".join(notes))
        self.follow()

    def on_closed(self, notes):
        said = f"✎ She'll remember {len(notes)} new thing{'s' if len(notes) != 1 else ''} from today" if notes else ""
        self.bubble.say("*waves goodbye* See you soon!", note=self._note(said, GRAY), stay=2.5)
        self.body.squish(1.0)
        QTimer.singleShot(1800, self.body.vanish)  # she wakes up back home: her dream-self comes apart (then quits)

    def on_failed(self, error):
        print(error, file=sys.stderr)
        self.body.think(False)  # her reply isn't coming: no more "…"
        self.bubble.say("*looks confused* Something went wrong…", stay=8,
                        note=self._note(error.strip().splitlines()[-1], GRAY))
        if self.leaving:
            QTimer.singleShot(2500, QApplication.quit)
        elif not self.input.isVisible():
            # the job is over (brain.busy may not be cleared yet on its thread, so not release()): wander again
            self.body.hold(False)

    # --- every few seconds, and whenever she moves ---

    def tick(self):
        if self.ready and not self.leaving and not self.input.isVisible() and not self.bubble.active:
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

def main(folder=DEFAULT):
    """folder = which character to open (their folder in character/)."""
    character = Character(folder)
    problems = check.mood_problems(character)
    if problems:
        raise SystemExit(f"{character.name}'s mood lists don't match (see desktop/check.py):\n  - "
                         + "\n  - ".join(problems))
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = App(character)  # (kept in a variable so it isn't garbage-collected)
    sys.exit(app.exec())
