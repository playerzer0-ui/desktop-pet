"""Quick checks of the engine and the desktop pet that need no llama-server (test_pip.py tests the model itself).
Saves go to a temporary folder, so your real saves/ are never touched.

    python -m unittest discover tests
"""
import contextlib, datetime, io, json, os, shutil, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no windows pop up

import memory, pet, quests, trust
from character import Character, for_stage
from save import Save, stage_of

TMP = tempfile.mkdtemp(prefix="pet-tests-")

def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)

def temp_path(name="save"):
    return os.path.join(TMP, f"{name}-{time.time_ns()}.json")

def pip():
    c = Character("pip")
    c.save_path, c.log_path = temp_path("pip"), os.path.join(TMP, "pip.log")
    return c

class TrustTest(unittest.TestCase):
    def test_new_save_gets_the_day_points(self):
        d = trust.start(temp_path())
        self.assertEqual((d["trust"], d["points"], d["days_logged"]), (1, 3, 1))
        self.assertEqual(trust.start(d.path)["points"], 3)  # same day again: nothing extra

    def test_talk_rules_and_cap(self):
        d = trust.start(temp_path())
        trust.talked(d, "hi", "nice")                   # under 3 words: nothing
        trust.talked(d, "you are so rude", "rude")      # rude: nothing
        self.assertEqual(d["points"], 3)
        for _ in range(10):
            trust.talked(d, "that is very kind", "nice")
        self.assertEqual((d["today"]["talk"], d["points"]), (10, 13))

    def test_stay_cap(self):
        d = trust.start(temp_path())
        trust.stayed(d, 15)
        trust.stayed(d, 600)
        self.assertEqual(d["points"], 3 + 4)

    def test_never_goes_down(self):
        d = trust.start(temp_path())
        trust._add(d, 37)
        self.assertEqual(d["trust"], 3)
        d["points"] = 0
        trust._add(d, 0)
        self.assertEqual(d["trust"], 3)

    def test_major_quest_gate(self):
        old = dict(trust.MAJOR_QUESTS)
        try:
            trust.MAJOR_QUESTS[1] = "gate"
            d = trust.start(temp_path())
            trust._add(d, 1000)
            self.assertEqual((d["points"], d["trust"]), (39, 2))  # held just short of stage 2
            trust.quest_done(d, "gate", 5)
            trust.quest_done(d, "gate", 5)  # a repeat pays nothing
            self.assertEqual((d["points"], d["trust"]), (44, 3))
        finally:
            trust.MAJOR_QUESTS.clear()
            trust.MAJOR_QUESTS.update(old)

    def test_hand_edited_trust_out_of_range(self):
        for typed, expected in ((0, 1), (-3, 1), (11, 10), (99, 10)):
            path = temp_path()
            with open(path, "w") as f:
                json.dump({"trust": typed}, f)
            d = trust.start(path)
            self.assertEqual(d["trust"], expected, f"trust {typed} in the save")
            self.assertEqual(d["points"], trust.TRUST_POINTS[expected - 1] + trust.DAY_POINTS)

    def test_stage_of(self):
        self.assertEqual([stage_of(t) for t in range(0, 12)], [1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5])

class PromptTest(unittest.TestCase):
    def test_for_stage_merges_and_hides(self):
        text = "Intro\n# Stage 1\n## Republic\none\n# Stage 3\n## Republic\nthree\n## Secret\nhidden\n"
        self.assertNotIn("three", for_stage(text, 1))
        s3 = for_stage(text, 3)
        self.assertEqual(s3.count("## Republic"), 1)
        self.assertIn("hidden", s3)

class MemoryTest(unittest.TestCase):
    def test_note_cap_keeps_world_answers(self):
        s = {}
        for i in range(35):
            memory.remember(s, "note", f"note {i}")
        memory.remember(s, "world", "w")
        notes = [m for m in s["memories"] if m["kind"] == "note"]
        self.assertEqual((len(notes), notes[0]["text"]), (30, "note 5"))

    def test_same_fact(self):
        self.assertTrue(memory.same_fact("The user's best friend is NR.", "The user's best friend is called NR"))
        self.assertFalse(memory.same_fact("NR switched his major to art and now paints", "The user's best friend is NR"))

    def test_ago(self):
        now = datetime.datetime(2026, 10, 21, 12, 0)
        self.assertEqual([memory.ago(w, now) for w in ("2026-10-21 08:00", "2026-10-20 23:59", "2026-10-11 10:00")],
                         ["today", "yesterday", "10 days ago"])

class QuestTest(unittest.TestCase):
    def test_flow(self):
        q = quests.Quests(pip())
        s = Save(temp_path(), {"trust": 1, "points": 3, "quests_done": [], "today": {"talk": 0, "minutes": 0}})
        self.assertIsNone(q.due(s))  # the first one waits 30-60 minutes
        q.next = 0
        self.assertTrue(q.due(s))
        self.assertIsNone(q.answered(s, "yes it does", "nice"))  # too short, and the quest is dropped
        q.next = 0; q.due(s)
        quest_id = q.pending[0]
        self.assertEqual(q.answered(s, "it rains here all the time", "nice"), quest_id)
        self.assertIn(quest_id, s["quests_done"])
        q.next = 0; q.due(s); q.answered(s, "we eat lots of bread here", "neutral")
        q.next = 0
        self.assertIsNone(q.due(s))  # two a day at most

def fake_stream(pieces, finish):
    """Stands in for llm.chat_stream: the pieces as the server's chunks, then a last chunk with the timings."""
    chunks = [{"choices": [{"delta": {"content": p}, "finish_reason": None}]} for p in pieces]
    chunks.append({"choices": [{"delta": {}, "finish_reason": finish}], "timings": {"prompt_n": 1}})
    return lambda messages, **settings: iter(chunks)

class AskTest(unittest.TestCase):
    MOODS = {"happy", "neutral", "sad"}

    def ask(self, *pieces, finish="stop"):
        """(reply, feeling, mood, what was streamed to the screen) for a reply made of these pieces."""
        real, shown = pet.llm.chat_stream, []
        pet.llm.chat_stream = fake_stream(pieces, finish)
        try:
            reply, _, feeling, mood = pet.ask([{"role": "system", "content": "x"}], "hi",
                                              on_text=shown.append, moods=self.MOODS)
        finally:
            pet.llm.chat_stream = real
        return reply, feeling, mood, "".join(shown).rstrip()  # (the space before a tag streams too)

    def test_tags(self):
        self.assertEqual(self.ask("*smiles* Hel", "lo there!", " [nice]", " [mood: happy]"),
                         ("*smiles* Hello there!", "nice", "happy", "*smiles* Hello there!"))

    def test_unknown_mood_and_no_tags(self):
        self.assertEqual(self.ask("Okay. [rude] [mood: ecstatic]")[:3], ("Okay.", "rude", None))
        self.assertEqual(self.ask("Just words.")[:3], ("Just words.", "neutral", None))

    def test_brackets_in_her_words_stay(self):
        reply, *_, shown = self.ask("I read [a book] today. [nice] [mood: happy]")
        self.assertEqual((reply, shown), ("I read [a book] today.", "I read [a book] today."))

    def test_tag_slips_never_reach_the_screen(self):
        reply, feeling, mood, shown = self.ask("Hello! [feeling: nice] [mood: happy]")
        self.assertEqual((reply, feeling, mood, shown), ("Hello!", "nice", "happy", "Hello!"))
        reply, *_, shown = self.ask("Hello! [neutral] [happy]")
        self.assertEqual((reply, shown), ("Hello!", "Hello!"))

    def test_cut_off_reply(self):
        self.assertEqual(self.ask("I went to the market. Then I saw a very long", finish="length")[0],
                         "I went to the market.")

class SentencesTest(unittest.TestCase):
    def split(self, text):
        from sentences import ends
        cuts = [0] + ends(text)
        return [text[a:b].strip() for a, b in zip(cuts, cuts[1:] + [len(text)]) if text[a:b].strip()]

    def test_titles_and_places_dont_end_a_sentence(self):
        self.assertEqual(self.split("Mr. Haloway is a nice person. He will ride me all the way to St. Raos"),
                         ["Mr. Haloway is a nice person.", "He will ride me all the way to St. Raos"])
        self.assertEqual(self.split("Dr. Who? Yes. J. R. Tolkien wrote it, e.g. the Hobbit."),
                         ["Dr. Who?", "Yes.", "J. R. Tolkien wrote it, e.g. the Hobbit."])

    def test_real_ends(self):
        self.assertEqual(self.split('No. That is wrong! Are you sure? I was... thinking. I said "hi." *waves* Bye~ ok'),
                         ["No.", "That is wrong!", "Are you sure?", "I was... thinking.", 'I said "hi."',
                          "*waves* Bye~ ok"])

    def test_streaming_waits_for_the_next_word(self):
        from sentences import first_end
        self.assertIsNone(first_end("Hello there. ", final=False))  # "Mr." or "St." might come next
        self.assertEqual(first_end("Hello there. Mr. ", final=False), len("Hello there. "))
        self.assertIsNone(first_end("I went to St. ", final=False))
        self.assertEqual(first_end("Hello there.", final=True), len("Hello there."))

    def test_trim_cut_off_reply(self):
        self.assertEqual(pet.trim_to_sentence("I met Mr. Haloway. He took me to St."), "I met Mr. Haloway.")
        self.assertEqual(pet.trim_to_sentence("no end here"), "no end here")

class MovesTest(unittest.TestCase):
    def test_actions(self):
        from desktop.moves import for_action
        cases = {
            "reaches out to pat your head, and her hand bumps against the screen": ("bonk", "dizzy"),
            "hides behind her sleeves": ("shrink", "heart"),
            "shakes her head": ("headshake", None),
            "nods happily": ("nod", None),
            "starts to nod off": ("sigh", "zzz"),
            "nods off": ("sigh", "zzz"),
            "keeps nodding off": ("sigh", "zzz"),
            "stirs her tea": (None, None),
        }
        for action, expected in cases.items():
            self.assertEqual(for_action(action), expected, action)

class DesktopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.qapp = QApplication.instance() or QApplication([])

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.qapp.processEvents()
            time.sleep(0.005)

    def test_bubble_pages_a_reply(self):
        from desktop.bubble import Bubble
        b, acted, done = Bubble(), [], []
        b.acted.connect(acted.append)
        b.done.connect(lambda: done.append(1))
        b.start()
        for piece in ("*waves* Hello there! ", "How are ", "you today? I baked bread."):
            b.add(piece)
        b.finish()
        self.assertEqual((acted, b.page), (["waves"], "Hello there!"))
        for _ in range(20):  # click through it all
            b.mousePressEvent(None)
            self.pump(0.005)
        self.assertEqual(done, [1])

    def test_bubble_keeps_titles_on_one_page(self):
        from desktop.bubble import Bubble
        b = Bubble()
        b.start()
        for piece in ("Mr", ". Hal", "oway is a nice person. He will", " ride me all the way to St", ". Raos"):
            b.add(piece)
        b.finish()
        self.assertEqual([b.page] + b.pages, ["Mr. Haloway is a nice person.", "He will ride me all the way to St. Raos"])

    def test_bubble_and_input_box_stay_on_screen(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication
        from desktop.bubble import Bubble, InputBox, TAIL_INSET
        area = QGuiApplication.primaryScreen().availableGeometry()
        b, box = Bubble(), InputBox("Pip")
        b.say("A reply long enough to fill the bubble from one side to the other.")
        y = area.bottom() - 200
        for x in (area.left() + 5, area.left() + 60, area.center().x(), area.right() - 60, area.right() - 5):
            head = QPoint(x, y)
            for widget in (b, box):
                widget.follow(head)
                self.assertGreaterEqual(widget.x(), area.left(), f"{type(widget).__name__} off the left at x={x}")
                self.assertLessEqual(widget.x() + widget.width(), area.right() + 1,
                                     f"{type(widget).__name__} off the right at x={x}")
            if TAIL_INSET <= x - b.x() <= b.width() - TAIL_INSET:
                self.assertEqual(b.x() + b.tail_x, x, "the tail should point at her head")
        b.follow(QPoint(area.center().x(), y))
        self.assertEqual(b.tail_x, b.width() // 2)  # away from the edges: centred, as before
        b.follow(QPoint(area.center().x(), area.top() + 10))  # dragged up to the top of the screen
        self.assertGreaterEqual(b.y(), area.top())

    def test_message_mid_reply_isnt_typed_over(self):
        from desktop.bubble import Bubble
        b = Bubble()
        b.start()
        b.add("Hello there! How are you? ")
        b.mousePressEvent(None)  # her first sentence is fully typed: the next one would come up on its own
        b.say("Something went wrong…")  # e.g. an error, or saying goodbye, while she talks
        b.add("I baked bread today. ")
        b.finish("note")
        self.pump(0.3)
        self.assertIn("Something went wrong", b.label.text())
        self.assertFalse(b.active)
        b.start()  # her next reply plays normally again
        b.add("Fresh start. ")
        b.finish()
        self.assertEqual(b.page, "Fresh start.")

    def app(self, loaded=True):
        from desktop import app as A
        class Signal:
            def connect(self, *_): pass
        class StubBrain:  # the real Brain would start llama-server
            busy = False
            def __getattr__(self, name):
                return Signal() if name in ("ready", "speaking", "piece", "spoke", "closed", "snapshot", "failed") \
                    else (lambda *a, **k: None)
        real = A.Brain
        A.Brain = lambda character: StubBrain()
        try:
            a = A.App(pip())
        finally:
            A.Brain = real
        if loaded:
            a.ready = True
            a.body.state, a.body.landed = "here", True  # (out of the portal already)
        return a

    def test_she_arrives_through_the_portal(self):
        import time
        from desktop import body as B
        a = self.app(loaded=False)
        self.assertEqual(a.body.state, "portal")
        self.assertIsNone(a.body._arrival(time.time()), "she's drawn before she's loaded")
        a.talk()
        self.assertFalse(a.input.isVisible(), "you can talk to the portal")
        a.on_ready("loaded")
        self.assertEqual(a.body.state, "arriving")
        a.body.portal_at -= B.ARRIVE_SECONDS  # (skip the animation)
        a.body._tick()
        self.assertTrue(a.body.here and a.body.landed)
        a.talk()
        self.assertTrue(a.input.isVisible())
        a.input.hide()

    def test_goodbye_she_dissolves_then_quits(self):
        from desktop import body as B
        a = self.app()
        gone = []
        a.body.vanished.connect(lambda: gone.append(True))
        a.body.vanish()
        self.assertEqual(a.body.state, "vanishing")
        self.assertTrue(a.body.motes, "nothing to dissolve")
        self.assertFalse(a.body.here, "she can still be dragged or talked to while dissolving")
        a.body.vanish_at -= B.VANISH_SWEEP + 0.25 + B.MOTE_LIFE  # (skip the animation)
        a.body._tick()
        self.assertEqual((a.body.state, gone), ("gone", [True]))

    def test_status_waits_while_she_talks(self):
        a = self.app()
        def enabled():
            menu = a.build_menu()  # (kept in a variable: its actions are deleted along with it)
            return {act.text(): act.isEnabled() for act in menu.actions() if act.text()}
        a.bubble.active = False
        self.assertTrue(enabled()["Status"] and enabled()["What she remembers"])
        a.on_speaking("user")
        self.assertFalse(enabled()["Status"] or enabled()["What she remembers"])
        self.assertTrue(enabled()["Talk to her"] and enabled()["Say goodbye"])

    def test_error_mid_reply_lets_her_wander(self):
        a = self.app()
        a.on_speaking("user")
        self.assertTrue(a.body.thinking and a.body.held)
        with contextlib.redirect_stderr(io.StringIO()):  # (on_failed prints the error)
            a.on_failed("Traceback...\nrequests.exceptions.ReadTimeout: boom\n")
        self.assertFalse(a.body.thinking, "still showing the '…' icon")
        self.assertFalse(a.body.held, "still held in place: she'd never wander again")

class DirectionsTest(unittest.TestCase):
    def test_a_cue_is_told_apart_from_the_user(self):
        from directions import direction, is_direction
        self.assertTrue(is_direction(direction("Pip says something on her own.")))
        self.assertFalse(is_direction("(she smiles) hi"))

class ServerGoneTest(unittest.TestCase):
    """No llama-server at all (a port nothing listens on): every call says so the same way."""
    def setUp(self):
        import llm, socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]  # (closed again: nothing listens there)
        self.llm, self.real = llm, (llm.SERVER, llm.CONNECT_SECONDS)
        llm.SERVER = f"http://127.0.0.1:{port}"
        llm.CONNECT_SECONDS = 0.3  # (Windows keeps retrying a refused connection for ~2 s: give up sooner)

    def tearDown(self):
        self.llm.SERVER, self.llm.CONNECT_SECONDS = self.real

    def test_every_call_raises_server_gone(self):
        self.assertFalse(self.llm.is_up())
        self.assertEqual(self.llm.model_path(), "")
        for call in (lambda: self.llm.chat([]), lambda: list(self.llm.chat_stream([])),
                     lambda: self.llm.template([]), lambda: self.llm.read("x")):
            with self.assertRaises(self.llm.ServerGone):
                call()

class ReconnectTest(unittest.TestCase):
    """The server goes away once: her reply and the goodbye diary both start it again and retry."""
    def setUp(self):
        import llm, session
        self.llm, self.session = llm, session
        self.real = session.start_server, session.warm_up, session.ask, llm.chat
        self.calls = {"start": 0, "read": 0, "ask": 0, "diary": 0}

        def start(say): self.calls["start"] += 1
        def warm(messages, fixed): self.calls["read"] += 1; return "loaded"
        def ask(messages, question, on_text=None, keep=1, moods=None):
            self.calls["ask"] += 1
            messages.append({"role": "user", "content": question})
            if self.calls["ask"] == 2:  # her first reply to you: the server is gone
                raise llm.ServerGone("test")
            messages.append({"role": "assistant", "content": "ok [nice] [mood: happy]"})
            return "ok", {}, "nice", "happy"
        def chat(messages, **settings):
            self.calls["diary"] += 1
            if self.calls["diary"] == 1:
                raise llm.ServerGone("test")
            return "- The user has a cat called Leo."
        session.start_server, session.warm_up, session.ask, llm.chat = start, warm, ask, chat

    def tearDown(self):
        self.session.start_server, self.session.warm_up, self.session.ask, self.llm.chat = self.real

    def test_reply_and_diary_survive(self):
        s = self.session.Session(pip(), say=lambda *_: None)
        s.open()
        shown = []
        self.assertEqual(s.user_says("my cat Leo knocked over a plant", on_text=shown.append).reply, "ok")
        self.assertEqual((self.calls["start"], self.calls["read"]), (2, 2))  # restarted, her prompt read back in
        self.assertIn(None, shown)  # the screen was told to start her reply over
        self.assertEqual([m["content"] for m in s.messages].count("my cat Leo knocked over a plant"), 1)
        s.user_says("we are going hiking on Friday")
        s.user_says("I had a really nice day today")
        notes = s.close()
        self.assertEqual([n["text"] for n in notes], ["The user has a cat called Leo."])
        self.assertEqual((self.calls["start"], self.calls["read"]), (3, 2))  # restarted again, no prompt re-read

if __name__ == "__main__":
    unittest.main()
