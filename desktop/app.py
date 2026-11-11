"""One character on the desktop: her body, speech bubble, input box and menu, wired to her mind (brain.py).
While her mind loads, only a portal shows. The screen never reads her save: the brain sends snapshots.
"""
import sys, time
from engine import data
from progress import launch
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QMenu
from engine.character import Character, DEFAULT
from desktop import check, download, moves
from desktop.status import card as status_card
from desktop.body import Body
from desktop.brain import Brain
from desktop.bubble import Bubble, InputBox, GOLD, ROSE, GRAY

TICK_MS = 5000       # how often she checks whether to speak up on her own
SQUISH_EVERY = 0.13  # seconds between talking squishes
MOOD_SECONDS = {"happy": 15}  # how long a mood lasts after she stops talking
MOOD_DEFAULT_SECONDS = 35
RESTING_SECONDS = 8  # how long the "resting back home" note shows before the app closes

def duration(minutes):
    """60 -> "1 hour", 90 -> "1 hour 30 minutes", 45 -> "45 minutes"."""
    hours, mins = divmod(minutes, 60)
    parts = [f"{hours} hour{'s' if hours != 1 else ''}"] if hours else []
    if mins:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    return " ".join(parts)

class App:
    def __init__(self, character, resting=False, away=False, scene=None, slot=0, greeting_note=None):
        """resting = today's time is used up; away = her story sent her home. Either way only the portal shows.
        scene = the Scene she shares the desktop with, or None. slot = her slot on the model server."""
        self.character = character
        self.scene = scene
        company = [c.name for c in scene.characters if c is not character] if scene else []
        self.body, self.bubble = Body(character.sprites, character.portal), Bubble()
        mood = launch.story_mood(character, [c.folder for c in scene.characters] if scene else [character.folder])
        if mood:  # shows from the portal on
            self.body.set_mood(mood)
        self.input = InputBox(character.name)
        self.brain = Brain(character, slot=slot, slots=len(scene.characters) if scene else 1, company=company,
                           greeting_note=greeting_note)
        self.ready = False
        self.wants_open = False  # ready, and she'll greet you once nobody else is talking
        self.snap = None    # the latest snapshot from the brain
        self.leaving = False
        self.last_squish = 0.0
        self.acted = False  # an *action* in her current reply got its own move
        self.restaging = False  # re-reading her prompt for a new stage
        self.time_up = False      # she goes home after her latest reply
        self.going_home = False   # leaving because her time is up
        self.saying_goodbye = False  # her time-up goodbye has started: no more talking
        self.story_leaving = False   # her story sends her home (no "see you tomorrow")

        self.body.moved.connect(self.follow)
        self.body.clicked.connect(self.talk)
        self.body.menu_requested.connect(self.menu)
        self.body.vanished.connect((lambda: scene.vanished(self)) if scene else QApplication.quit)
        self.input.submitted.connect(self.send)
        self.input.closed.connect(self.release)
        self.bubble.typed.connect(self.on_typed)
        self.bubble.acted.connect(self.on_acted)
        self.bubble.done.connect(self.on_done)
        self.brain.ready.connect(self.on_ready)
        self.brain.speaking.connect(self.on_speaking)
        self.brain.piece.connect(self.on_piece)
        self.brain.mood.connect(self.on_mood)
        self.brain.restaging.connect(self.on_restaging)
        self.brain.spoke.connect(self.on_spoke)
        self.brain.closed.connect(self.on_closed)
        self.brain.snapshot.connect(self.on_snapshot)
        self.brain.failed.connect(self.on_failed)

        self.ticker = QTimer(timeout=self.tick)
        self.calm_down = QTimer(singleShot=True, timeout=self.settle)
        self.last_reply = 0  # Turn.number of her latest reply

        self.body.show()
        self.follow()
        if away:  # her story sent her home: nothing says why
            self.leaving = True
            QTimer.singleShot(RESTING_SECONDS * 1000, QApplication.quit)
            return
        if resting:  # no model started
            self.leaving = True
            self.bubble.say(f"{character.name} is resting back home today.", note=self._note(
                character.fill("{They} can visit for ") + duration(character.daily_minutes)
                + " a day. Come back tomorrow!", GRAY))  # (not why: some characters keep that secret at first)
            QTimer.singleShot(RESTING_SECONDS * 1000, QApplication.quit)
            return
        self.brain.start()

    # --- you ---

    @property
    def talking(self):
        """She's thinking, or her words are still on screen."""
        return self.bubble.active or self.brain.working

    def others_talking(self):
        return bool(self.scene and self.scene.others_talking(self))

    def talk(self):
        if self.leaving or self.saying_goodbye or self.talking or self.others_talking() or not self.body.here:
            return
        self.body.hold(True)
        self.input.open_at(self.body.head())
        self.follow()

    def send(self, text):
        self.follow()
        if not self.ready:
            self.bubble.say("*still waking up…*", stay=3)
            self.release()
            return
        if self.saying_goodbye or self.leaving:
            return
        if self.scene:
            self.scene.activity()
        self.brain.say(text)

    def release(self):
        """Let her wander again, unless you're typing or she's still talking."""
        if not self.input.isVisible() and not self.brain.busy and not self.bubble.active:
            self.body.hold(False)

    def menu(self, where):
        self.build_menu().exec(where)

    def build_menu(self):
        """Talking, Status and memories wait while she's talking (they'd cut her reply short)."""
        menu = QMenu()
        talking = self.talking
        say = self.character.fill
        menu.addAction(say("Talk to {them}"), self.talk).setEnabled(
            self.body.here and not talking and not self.others_talking() and not self.saying_goodbye
            and not self.leaving)
        for label, action in (("Status", self.status), (say("What {they} remembers"), self.memories)):
            menu.addAction(label, action).setEnabled(not talking)
        menu.addSeparator()
        menu.addAction("Say goodbye", self.leave)
        return menu

    def on_snapshot(self, snap):
        self.snap = snap

    def status(self):
        # checked again: she may have started a reply while the menu was open, and the card would cut it off
        if not self.snap or self.talking:
            return
        self.bubble.show_picture(status_card(self.snap["summary"]), stay=8)

    def memories(self):
        if not self.snap or self.talking:
            return
        entries = self.snap["memories"]
        if not entries:
            self.bubble.say(self.character.fill("*tilts {their} head* We've only just met!"), stay=5)
            return
        recent = "<br>".join(f"✎ {m['text']}" for m in entries[-4:])
        self.bubble.say(f"*smiles* I remember {len(entries)} things about you.", stay=12,
                        note=self._note(recent, GRAY))

    def leave(self, going_home=False, following=False):
        """Say goodbye: she writes in her diary, waves and fades away. going_home = her time is up.
        While her story wants goodbyes, she begs to stay instead. following = someone else in the scene left."""
        if self.leaving:
            return
        if (not going_home and not following and self.ready and self.snap
                and self.snap["summary"].get("talks_on_goodbye")):
            self.brain.goodbye()
            return
        self.leaving, self.going_home = True, going_home
        self.ticker.stop()
        self.input.hide()
        self.body.hold(True)
        if self.scene and not following:
            self.scene.leave_with(self, going_home)
        if not self.ready:
            if self.scene:  # still in the portal: she just doesn't come out
                self.body.hide()
                self.scene.vanished(self)
            else:
                QApplication.quit()
            return
        self.bubble.say(self.character.fill("*writes in {their} little diary*"),
                        note=self._note("saying goodbye…", GRAY))
        self.brain.close()

    # --- her ---

    def goodbye_started(self):
        """Her time is up and she's saying goodbye: close the input box for good."""
        self.saying_goodbye = True
        self.input.hide()

    def on_ready(self, prompt_was):
        self.ready = True
        self.body.arrive()
        if not self.scene:  # in a scene, the scene's ticker takes turns
            self.ticker.start(TICK_MS)
        self.wants_open = True
        self.try_open()

    def try_open(self):
        """Her greeting, once it's her turn."""
        if (self.wants_open and not self.leaving and not self.others_talking()
                and (not self.scene or self.scene.may_greet(self))):
            self.wants_open = False
            self.brain.open(self.scene.heard_for(self) if self.scene else None)

    def on_speaking(self, kind):
        if self.scene:
            self.scene.activity()
        if kind == "time_up":
            self.goodbye_started()
        self.body.hold(True)
        self.body.think(True)  # "…" until her first words show up
        self.calm_down.stop()
        self.acted = False
        self.bubble.start()
        self.follow()

    def on_restaging(self, busy):
        """A "…" while she takes in a new stage, so you can see why she doesn't answer yet."""
        self.restaging = busy
        if not self.bubble.active:
            self.body.think(busy)

    def on_mood(self, mood):
        self.body.set_mood(mood)

    def on_piece(self, piece):
        self.bubble.add(piece)
        self.follow()

    def on_acted(self, action):
        """She does an *action*: act it out with a move and an emote."""
        self.body.think(False)
        move, emote = moves.for_action(action)
        if move:
            self.acted = True
            self.body.play(move)
        self.body.emote(emote)

    def on_typed(self):
        self.body.think(False)
        now = time.time()
        if now - self.last_squish > SQUISH_EVERY:
            self.last_squish = now
            self.body.squish(0.7)
        self.follow()

    def on_done(self):
        """Her whole reply has been read: she can wander again, and her mood slowly settles."""
        self.release()
        if self.restaging:
            self.body.think(True)
        if self.scene:
            self.scene.line_done(self)
        if self.time_up:
            self.leave(going_home=True)
            return
        locked = self.snap and self.snap["summary"].get("mood_locked")  # her story holds this mood
        if self.body.mood != "neutral" and not locked:
            self.calm_down.start(MOOD_SECONDS.get(self.body.mood, MOOD_DEFAULT_SECONDS) * 1000)

    def settle(self):
        """Back to neutral, on screen and in her save."""
        self.body.set_mood("neutral")
        self.brain.settle(self.last_reply)

    def on_spoke(self, turn):
        self.last_reply = turn.number
        if turn.kind == "opening" and self.scene:
            self.scene.greeted(self, turn.reply)
        if turn.kind == "duet" and self.scene:
            self.scene.duet_said(self, turn.reply)
        self.time_up = turn.time_up or turn.leaving
        self.story_leaving = self.story_leaving or turn.leaving
        if self.time_up:
            self.goodbye_started()
        self.body.set_mood(turn.mood)
        move, emote = moves.MOOD_MOVES.get(turn.mood, (None, None))
        if not self.acted and move:  # no action of hers had a move: show how she feels instead
            self.body.play(move)
        if turn.feeling == "nice":
            emote = "heart"
        self.body.emote(emote)
        notes, say = [], self.character.fill
        if turn.kind == "quest":
            notes.append(self._note(say("✦ {They} is curious about your world. Answer {them} to earn {their} trust!"),
                                    GOLD))
        if turn.quest_done:
            notes.append(self._note(say("✦ Quest complete: {they} learned something about your world"), GOLD))
        if turn.major_raised:
            notes.append(self._note(say("✻ Something is on {their} mind. {Their} trust can only grow once you answer it"),
                                    GOLD))
        if turn.major_done:
            notes.append(self._note(say("✻ A turning point: {they}'ll remember this, and {their} trust can grow again"),
                                    ROSE))
        if turn.trust_after > turn.trust_before:
            notes.append(self._note(f"♥ {self.character.name} trusts you more · trust {turn.trust_after}/10", ROSE))
        if turn.stage_up:
            stage, name = turn.stage_after
            notes.append(self._note(f"✻ Stage {stage} · {name}: " + say("{they}'ll open up more next time"), ROSE))
        self.bubble.finish("<br>".join(notes))
        self.follow()

    def on_closed(self, notes):
        said = (self.character.fill("✎ {They}'ll remember ") + f"{len(notes)} new thing{'s' if len(notes) != 1 else ''}"
                " from today") if notes else ""
        if self.story_leaving:  # she's said her own goodbye: no wave, she just fades
            if said:
                self.bubble.say("", note=self._note(said, GRAY), stay=2.5)
            else:
                self.bubble.hide()
            QTimer.singleShot(1800, self.body.vanish)
            return
        if self.going_home:
            said = "<br>".join(filter(None, [said, self.character.fill("{They}'s resting back home until tomorrow")]))
        self.bubble.say("*waves goodbye* See you tomorrow!" if self.going_home else "*waves goodbye* See you soon!",
                        note=self._note(said, GRAY), stay=2.5)
        self.body.squish(1.0)
        QTimer.singleShot(1800, self.body.vanish)

    def on_failed(self, error):
        print(error, file=sys.stderr)
        if not self.ready:  # she never woke up: say why, and close
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, self.character.name, f"{self.character.name} couldn't wake up.\n\n{error.strip()}")
            QApplication.quit()
            return
        if self.scene:
            self.scene.end_duet()
        self.body.think(False)
        self.bubble.say("*looks confused* Something went wrong…", stay=8,
                        note=self._note(error.strip().splitlines()[-1], GRAY))
        if self.leaving:
            QTimer.singleShot(2500, QApplication.quit)
        elif not self.input.isVisible():
            # not release(): brain.busy may not be cleared yet on its thread
            self.body.hold(False)

    # --- every few seconds, and whenever she moves ---

    def tick(self):
        if self.wants_open:
            self.try_open()
            return
        if (self.ready and not self.leaving and not self.input.isVisible() and not self.bubble.active
                and not self.others_talking()):
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

def one_at_a_time(character):
    """Only one copy of the pet at a time (two would overwrite each other's saves). Returns the held lock,
    or tells the user and exits. A copy that crashed doesn't keep the next one out."""
    import os
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QMessageBox
    folder = os.path.dirname(character.save_path)
    os.makedirs(folder, exist_ok=True)
    lock = QLockFile(os.path.join(folder, "desktop.lock"))
    lock.setStaleLockTime(0)  # stale only once the copy holding it has gone
    if not lock.tryLock(500):
        QMessageBox.information(None, character.name, f"{character.name} is already on your desktop.")
        raise SystemExit(0)
    return lock

def main(folder=DEFAULT):
    """Open a character. Who comes today is picked from character/roster.toml: more than one means a Scene."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    data.prepare()
    problems = check.cast_problems(also=[folder])
    if problems:
        raise SystemExit("Some character files have mistakes (python -m desktop.check lists them again):\n  - "
                         + "\n  - ".join(problems))
    character = Character(folder)
    running = one_at_a_time(character)  # kept until exit: it holds the lock (taken before the model download)
    if not download.ensure_model(character):
        return
    day = launch.today(folder)
    if day.together:
        from desktop.scene import Scene
        pet = Scene(day.cast)
    else:  # (kept in a variable so it isn't garbage-collected)
        pet = App(day.cast[0], resting=day.resting, away=day.away, greeting_note=day.note)
    sys.exit(app.exec())
