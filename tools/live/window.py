"""The pet's real window on the real model: she wakes, greets you, and the messages are typed into her input box
the way you would. For every reply it times her first words, her last letter, and how long after that last
letter you still can't type to her (the judge, or a new stage, still running), and saves a picture of her bubble.

    python -m tools.live.window
    python -m tools.live.window --who ruby --say "hi" "what are you doing?"
    python -m tools.live.window --offscreen          no windows on screen (the pictures still work)

It ends by itself; Ctrl+C or --timeout stops it early. Her ticker is stopped, so she never speaks up on her own
in the middle of a measurement.
"""
import argparse, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.live import common

MESSAGES = ["hi! how are you today?", "I had a long day, but talking to you helps", "what are you up to?"]
POLL_MS = 50

class Probe:
    """Watches one App and sends the next message once she has finished, and you could type again."""
    def __init__(self, pet, messages, shots, quit, goodbye=False):
        self.pet, self.messages, self.shots, self.quit = pet, list(messages), shots, quit
        self.goodbye, self.left = goodbye, None  # left = when you said goodbye
        self.t0 = time.time()
        self.awake = None
        self.replies, self.reply = [], None
        self.failed = None
        self.waiting_since = None  # her reply is done: trying to open the input box since then
        pet.brain.ready.connect(self.on_ready)
        pet.brain.speaking.connect(self.on_speaking)
        pet.bubble.typed.connect(self.on_typed)
        pet.brain.piece.connect(self.on_piece)
        pet.brain.spoke.connect(self.on_spoke)
        pet.bubble.done.connect(self.on_done)
        pet.brain.failed.connect(self.on_failed)

    def now(self):
        return time.time() - self.t0

    def on_ready(self, how):
        self.awake = (self.now(), how)
        self.pet.ticker.stop()  # (no idle lines while measuring)
        print(f"awake after {self.awake[0]:.1f}s (prompt {how})", flush=True)

    def on_speaking(self, kind):
        if self.reply and self.reply.get("speaking") is not None:
            return  # (the server restarted mid-reply: same reply)
        self.reply = self.reply or {"you": None, "sent": self.now()}
        self.reply.update(kind=kind, speaking=self.now(), first=None, last=None, written=None, spoke=None, free=None)

    def on_piece(self, _):
        if self.reply:
            self.reply["written"] = self.now()  # her last word so far has arrived from the model

    def on_typed(self):
        if self.reply:
            self.reply["first"] = self.reply["first"] or self.now()
            self.reply["last"] = self.now()

    def on_spoke(self, turn):
        if self.reply:
            self.reply.update(spoke=self.now(), text=turn.reply, felt=turn.feeling, mood=turn.mood)

    def on_done(self):
        if self.reply and self.reply.get("spoke") is not None:
            self.reply["done"] = self.now()
            self.replies.append(self.reply)
            self.show(self.reply)
            self.reply = None
            if not self.left:  # (after her goodbye, poll waits for her to fade)
                self.waiting_since = self.now()

    def on_failed(self, error):
        self.failed = error
        print("FAILED: " + error, flush=True)
        self.quit()

    def poll(self):
        r = self.reply
        if self.left and self.pet.body.state in ("vanishing", "gone"):
            print(f"she faded out {self.now() - self.left:.1f}s after you said goodbye · bubble: "
                  f"{self.pet.bubble.label.text().strip()!r} · note: {self.pet.bubble.note.text()!r}", flush=True)
            self.quit()
            return
        if r and r.get("spoke") is not None and r["free"] is None and not self.pet.brain.working:
            r["free"] = self.now()
            self.picture(len(self.replies) + 1)
        if (self.awake and not self.replies and not self.reply and self.waiting_since is None
                and not self.pet.brain.working and self.now() - self.awake[0] > 5):
            print("(no greeting: a silent story step)", flush=True)
            self.waiting_since = self.now()
        if self.waiting_since is None:
            return
        if not self.messages:
            if self.goodbye and not self.left:  # "Say goodbye" from her menu: her goodbye, her diary, then she fades
                self.left = self.now()
                self.waiting_since = None
                print("\n(you say goodbye)", flush=True)
                self.pet.leave()
                return
            self.quit()
            return
        self.pet.talk()
        if self.pet.input.isVisible():
            from PySide6.QtCore import Qt
            from PySide6.QtTest import QTest
            text = self.messages.pop(0)
            self.reply = {"you": text, "sent": None, "input_after": self.now() - self.waiting_since}
            self.waiting_since = None
            QTest.keyClicks(self.pet.input.line, text)
            self.reply["sent"] = self.now()
            QTest.keyClick(self.pet.input.line, Qt.Key_Return)
        elif self.now() - self.waiting_since > 15:
            print("FAILED: the input box didn't open within 15 s of her reply ending", flush=True)
            self.failed = "input box never opened"
            self.quit()

    def picture(self, number):
        if self.shots and self.pet.bubble.isVisible():
            self.pet.bubble.grab().save(os.path.join(self.shots, f"{number:02}-bubble.png"))
            self.pet.body.grab().save(os.path.join(self.shots, f"{number:02}-body.png"))

    def show(self, r):
        start = r["sent"] if r.get("sent") is not None else r["speaking"]
        typed, skipped = locks(r)
        print(f"\n{r['kind']}" + (f" · you: {r['you']}" if r["you"] else "") + f"\n  her: {r.get('text', '')}\n  "
              + (f"input box opened {r['input_after']:.1f}s after her last reply ended · " if "input_after" in r else "")
              + (f"first words {r['first'] - start:.1f}s · last letter {r['last'] - start:.1f}s · " if r["first"] else "")
              + (f"can't type for {typed:.1f}s after her last letter ({skipped:.1f}s if you click to skip) · "
                 if typed is not None else "")
              + f"bubble gone {r['done'] - start:.1f}s · [{r.get('felt') or '-'}] {r.get('mood')}", flush=True)

def locks(r):
    """How long you still can't type to her once her words are all there: after the bubble typed the last letter,
    and after the model wrote the last word (what you wait if you click to skip the typing). (None, None) if
    unknown."""
    if r.get("free") is None or r.get("last") is None or r.get("written") is None:
        return None, None
    return max(0.0, r["free"] - r["last"]), max(0.0, r["free"] - r["written"])

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--who", default="pip")
    parser.add_argument("--say", nargs="+", default=MESSAGES)
    parser.add_argument("--model", choices=sorted(common.MODELS), help="default: the one engine/config.py ships")
    parser.add_argument("--port", type=int, default=common.PORT)
    parser.add_argument("--offscreen", action="store_true")
    parser.add_argument("--goodbye", action="store_true", help='end with "Say goodbye" from her menu')
    parser.add_argument("--shots", default="window-shots", help="folder for the pictures ('' for none)")
    parser.add_argument("--timeout", type=int, default=900, help="seconds before it gives up")
    args = parser.parse_args()
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    config = common.use(args.model, args.port)
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from engine.character import Character
    from desktop.app import App
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)
    character = Character(args.who)
    character.daily_minutes = None
    common.seed_save(character, None)  # (a fresh data folder: her very first visit)
    pet = App(character)
    probe = Probe(pet, args.say, args.shots, qt.quit, goodbye=args.goodbye)
    poller = QTimer(timeout=probe.poll)
    poller.start(POLL_MS)
    QTimer.singleShot(args.timeout * 1000, lambda: (print(f"FAILED: still going after {args.timeout}s"), qt.quit()))
    qt.exec()

    user = [r for r in probe.replies if r["you"]]
    waits = [locks(r) for r in user if locks(r)[0] is not None]
    print(f"\n{config.MODEL_FILE} · {len(probe.replies)} replies ({len(user)} to you) · "
          + (f"can't type after her last letter: {', '.join(f'{t:.1f}s' for t, _ in waits)} · if you click to skip: "
             f"{', '.join(f'{s:.1f}s' for _, s in waits)}" if waits else "")
          + (f" · pictures in {os.path.abspath(args.shots)}" if args.shots else ""))
    ok = probe.failed is None and len(user) == len(args.say)
    print("OK" if ok else "FAILED" + (f": {probe.failed}" if probe.failed else f": {len(user)} of {len(args.say)} replies"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
