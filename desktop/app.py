"""Pip as a real desktop pet.

    python main.py

Click her to talk, right-click for the menu, drag her anywhere (she falls back to the floor).
While her mind loads, only a portal sits on the floor; once it's ready she pops out of it and says hello.
She can stay a few hours a day (daily_minutes, visits.py): then she says goodbye and goes home, and until midnight
only the portal shows up, with a note that she's resting.
Her mind is session.py, run by brain.py on its own thread. The screen never reads her save directly:
after every job the brain sends a snapshot (trust summary, memories), and Status / memories show that.
"""
import sys, time
import friends, story, visits
from save import load_save
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
RESTING_SECONDS = 8  # how long the "resting back home" note shows before the app closes

def duration(minutes):
    """A daily limit in words: 60 -> "1 hour", 240 -> "4 hours", 90 -> "1 hour 30 minutes", 45 -> "45 minutes"."""
    hours, mins = divmod(minutes, 60)
    parts = [f"{hours} hour{'s' if hours != 1 else ''}"] if hours else []
    if mins:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    return " ".join(parts)

def story_mood(character, lineup):
    """The mood her story has her in today (story.mood_today), from her save, or None."""
    save = load_save(character.save_path)
    save.gates = character.gates
    for key, empty in (("points", 0), ("quests_done", [])):  # (a save that's never been opened has neither)
        save.setdefault(key, empty)
    story.catch_up(save, character)  # (a story step that lasted all of an earlier day is over)
    return story.mood_today(save, character, lineup)

class App:
    def __init__(self, character, resting=False, away=False, scene=None, slot=0, greeting_note=None):
        """resting = she's used up today's time (visits.resting): only the portal shows, with a note, then it closes.
        away = a story quest sent her home for a while (story.away): only the portal shows, no note, then it closes.
        scene = the Scene she shares the desktop with (desktop/scene.py), or None when she's on her own;
        slot = her own slot on the model server (llm.py), one per character in the scene.
        greeting_note = something for her greeting to bring up, like why her friend isn't here today."""
        self.character = character  # who's on the desktop (character.py)
        self.scene = scene
        company = [c.name for c in scene.characters if c is not character] if scene else []
        self.body, self.bubble = Body(character.sprites, character.portal), Bubble()
        mood = story_mood(character, "together" if scene else "alone")
        if mood:  # (her story has her hurt today, say: it shows from the portal on, not only after she speaks)
            self.body.set_mood(mood)
        self.input = InputBox(character.name)
        self.brain = Brain(character, slot=slot, slots=len(scene.characters) if scene else 1, company=company,
                           greeting_note=greeting_note)
        self.ready = False
        self.wants_open = False  # her mind is ready and she'll greet you as soon as nobody else is talking
        self.snap = None    # the latest snapshot from the brain: {"summary": trust.summary(...), "memories": [...]}
        self.leaving = False
        self.last_squish = 0.0
        self.acted = False  # an *action* in her current reply got its own move (else her mood picks one)
        self.restaging = False  # she's re-reading her prompt for a stage she just reached (on_restaging)
        self.time_up = False      # her latest reply came after today's time ran out: she goes home after it
        self.going_home = False   # leaving because of that (her goodbye differs a little)
        self.saying_goodbye = False  # her time-up goodbye has started: you can't talk to her any more (it'd keep her)
        self.story_leaving = False   # it's her story that sends her home (no "see you tomorrow": she won't be back)

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
        self.last_reply = 0  # Turn.number of her latest reply (whose mood the calm_down timer settles)

        self.body.show()  # (a portal until she's loaded: on_ready brings her out)
        self.follow()
        if away:  # her story sent her home: the portal shows, but she doesn't come through, and nothing says why
            self.leaving = True
            QTimer.singleShot(RESTING_SECONDS * 1000, QApplication.quit)
            return
        if resting:  # today's time is used up: the portal shows, but she doesn't come through (no model started)
            self.leaving = True
            self.bubble.say(f"{character.name} is resting back home today.", note=self._note(
                character.fill("{They} can visit for ") + duration(character.daily_minutes)
                + " a day. Come back tomorrow!", GRAY))  # (not how: some characters keep that secret at first)
            QTimer.singleShot(RESTING_SECONDS * 1000, QApplication.quit)
            return
        self.brain.start()

    # --- you ---

    @property
    def talking(self):
        """She's thinking, or her words are still on screen: you can't talk to her until she's done
        (it would cut into her reply, an idle thought, or a quest question you'd then miss)."""
        return self.bubble.active or self.brain.working

    def others_talking(self):
        """Someone else in the scene is talking, or you're typing to them: she waits her turn."""
        return bool(self.scene and self.scene.others_talking(self))

    def talk(self):
        if self.leaving or self.saying_goodbye or self.talking or self.others_talking() or not self.body.here:
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
        if self.saying_goodbye or self.leaving:
            return  # (she's on her way home)
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
        """Her right-click menu. Talking, Status and memories wait while she's talking (they'd cut her reply short)."""
        menu = QMenu()
        talking = self.talking
        menu.addAction("Talk to her", self.talk).setEnabled(
            self.body.here and not talking and not self.others_talking() and not self.saying_goodbye
            and not self.leaving)
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

    def leave(self, going_home=False, following=False):
        """Say goodbye: she writes in her diary, waves and fades away. going_home = her time today is up.
        While her story wants goodbyes (story.py), she begs to stay instead, and only the last one sends her home.
        In a scene everyone leaves together; following = she's leaving because someone else in it is."""
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
            if self.scene:  # (still in the portal: she just doesn't come out)
                self.body.hide()
                self.scene.vanished(self)
            else:
                QApplication.quit()
            return
        self.bubble.say("*writes in her little diary*", note=self._note("saying goodbye…", GRAY))
        self.brain.close()

    # --- her ---

    def goodbye_started(self):
        """Her time is up and she's saying goodbye: close the box you type in, and don't open it again."""
        self.saying_goodbye = True
        self.input.hide()

    def on_ready(self, prompt_was):
        self.ready = True
        self.body.arrive()  # out of the portal (her opening line is "…" until it's written: she's out by then)
        if not self.scene:  # (in a scene, the scene's ticker takes turns between everyone)
            self.ticker.start(TICK_MS)
        self.wants_open = True
        self.try_open()

    def try_open(self):
        """Her greeting, once it's her turn (alone, that's right away). In a scene the first one greets first,
        and the others wait until she's done, then hear what she said (Scene.heard_for)."""
        if (self.wants_open and not self.leaving and not self.others_talking()
                and (not self.scene or self.scene.may_greet(self))):
            self.wants_open = False
            self.brain.open(self.scene.heard_for(self) if self.scene else None)

    def on_speaking(self, kind):
        if self.scene:
            self.scene.activity()
        if kind == "time_up":  # her goodbye: no more talking from here on
            self.goodbye_started()
        self.body.hold(True)
        self.body.think(True)  # a "…" thought icon until her first words show up
        self.calm_down.stop()
        self.acted = False
        self.bubble.start()
        self.follow()

    def on_restaging(self, busy):
        """She's taking in a stage she just reached (Session.restage): a "…" over her once her reply has been read,
        so you can see why she doesn't answer a click yet."""
        self.restaging = busy
        if not self.bubble.active:
            self.body.think(busy)

    def on_mood(self, mood):
        """Her mood for the reply she's starting: her face changes now, as her first words appear."""
        self.body.set_mood(mood)

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
        if self.restaging:
            self.body.think(True)  # (still taking in her new stage: see on_restaging)
        if self.scene:  # (in a chat with her friend, it's the other one's turn now)
            self.scene.line_done(self)
        if self.time_up:  # she's said goodbye (or answered you after her time ran out): home she goes
            self.leave(going_home=True)
            return
        locked = self.snap and self.snap["summary"].get("mood_locked")  # (her story keeps her in this mood)
        if self.body.mood != "neutral" and not locked:
            self.calm_down.start(MOOD_SECONDS.get(self.body.mood, MOOD_DEFAULT_SECONDS) * 1000)

    def settle(self):
        """Her mood has lasted long enough: back to neutral, on screen and in her save at the same time."""
        self.body.set_mood("neutral")
        self.brain.settle(self.last_reply)

    def on_spoke(self, turn):
        self.last_reply = turn.number
        if turn.kind == "opening" and self.scene:
            self.scene.greeted(self, turn.reply)
        if turn.kind == "duet" and self.scene:
            self.scene.duet_said(self, turn.reply)
        self.time_up = turn.time_up or turn.leaving  # (either way she goes home once you've read this)
        self.story_leaving = self.story_leaving or turn.leaving
        if self.time_up:  # (also when her time ran out while answering you)
            self.goodbye_started()
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
        if turn.major_raised:
            notes.append(self._note("✻ Something is on her mind. Her trust can only grow once you answer it", GOLD))
        if turn.major_done:
            notes.append(self._note("✻ A turning point: she'll remember this, and her trust can grow again", ROSE))
        if turn.trust_after > turn.trust_before:
            notes.append(self._note(f"♥ {self.character.name} trusts you more · trust {turn.trust_after}/10", ROSE))
        if turn.stage_up:
            stage, name = turn.stage_after
            notes.append(self._note(f"✻ Stage {stage} · {name}: she'll open up more next time", ROSE))
        self.bubble.finish("<br>".join(notes))
        self.follow()

    def on_closed(self, notes):
        said = f"✎ She'll remember {len(notes)} new thing{'s' if len(notes) != 1 else ''} from today" if notes else ""
        if self.story_leaving:  # (she's said her own goodbye: no wave, no "see you tomorrow", she just fades)
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
        QTimer.singleShot(1800, self.body.vanish)  # she wakes up back home: her dream-self comes apart (then quits)

    def on_failed(self, error):
        print(error, file=sys.stderr)
        if self.scene:
            self.scene.end_duet()  # (a chat can't go on without her line)
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
        if self.wants_open:  # (in a scene: her greeting waited for someone else to finish)
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
    """Only one copy of the pet at a time: two copies would each write their whole save, and one would wipe the
    other's points and memories. Returns the held lock (saves/desktop.lock), or tells the user and exits.
    The lock names this process, so a copy that crashed or was killed doesn't keep the next one out."""
    import os
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QMessageBox
    folder = os.path.dirname(character.save_path)
    os.makedirs(folder, exist_ok=True)
    lock = QLockFile(os.path.join(folder, "desktop.lock"))
    lock.setStaleLockTime(0)  # (never stale by age alone: only once the copy holding it has gone)
    if not lock.tryLock(500):
        QMessageBox.information(None, character.name, f"{character.name} is already on your desktop.")
        raise SystemExit(0)
    return lock

def main(folder=DEFAULT):
    """folder = which character to open (their folder in character/). After she has brought her friend over
    (friends.py), the friend comes with her: both on the desktop at once (desktop/scene.py)."""
    character = Character(folder)
    save = load_save(character.save_path)
    company = note = None
    friend = friends.visiting_today(save)
    if friend:  # the day after she invited her friend: the friend comes instead of her
        character = Character(friend)
        save = load_save(character.save_path)
    else:  # from the day after that, mostly together; now and then one of them is busy back home
        who = friends.plan(save, character)
        story_day = friends.by_story(save)  # (a story picked today's lineup: no "she's busy today" line)
        if who == "together":
            company = Character(character.friend["folder"])
        elif who == "only_her":  # (on a story's day, her friend's story is what she brings up instead)
            note = (friends.tell_for_friend(character) if story_day else None) or                    character.fill(character.friend["only_her"]) + "."
        elif who == "only_friend":
            lines, character = character.friend, Character(character.friend["folder"])
            note = None if story_day else character.fill(lines["only_friend"]) + "."
            save = load_save(character.save_path)
    for c in filter(None, (character, company)):
        problems = check.mood_problems(c)
        if problems:
            raise SystemExit(f"{c.name}'s mood lists don't match (see desktop/check.py):\n  - "
                             + "\n  - ".join(problems))
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    running = one_at_a_time(character)  # (kept until the app exits: that's what holds the lock)
    # her story sent her home for now, or she invited her friend today: she doesn't come out (and no model is started)
    away = story.away(save) or friends.gone_today(save)
    resting = not away and visits.resting(character) and not story.ignores_time_limit(save, character)
    if company and not (away or resting):  # (she decides whether they come today: her friend comes with her)
        from desktop.scene import Scene
        company.daily_minutes = None  # (they leave together, when her time is up)
        pet = Scene([character, company])
    else:
        pet = App(character, resting=resting, away=away, greeting_note=note)  # (kept so it isn't garbage-collected)
    sys.exit(app.exec())
