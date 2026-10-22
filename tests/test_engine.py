"""Quick checks of the engine and the desktop pet that need no llama-server (test_pip.py tests the model itself).
Saves go to a temporary folder, so your real saves/ are never touched.

    python -m unittest discover tests
"""
import contextlib, datetime, io, json, os, re, shutil, sys, tempfile, time, unittest

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
    c.daily_minutes = 240  # (her real limit, whatever character.toml has while you test: see test_pip_has_four_hours)
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
        d = trust.start(temp_path(), {1: "gate"})
        self.assertIsNone(trust.at_gate(d))
        trust._add(d, 1000)
        self.assertEqual((d["points"], d["trust"]), (39, 2))  # held just short of stage 2
        self.assertEqual(trust.at_gate(d), 1)
        self.assertTrue(trust.summary(d, {i: "x" for i in range(1, 6)})["gated"])
        trust.quest_done(d, "gate", 5)
        trust.quest_done(d, "gate", 5)  # a repeat pays nothing
        self.assertEqual((d["points"], d["trust"]), (44, 3))
        self.assertIsNone(trust.at_gate(d))
        self.assertFalse(trust.summary(d, {i: "x" for i in range(1, 6)})["gated"])

    def test_no_gates_means_no_cap(self):
        d = trust.start(temp_path())
        trust._add(d, 1000)
        self.assertEqual(d["trust"], 10)

    def test_old_save_past_a_gate_keeps_growing(self):
        """A save from before the gates (like trust 3, 57 points): gates behind her count as done."""
        path = temp_path()
        with open(path, "w") as f:
            json.dump({"trust": 3, "points": 57, "quests_done": ["world-outside"]}, f)
        gates = {1: "major-a", 2: "major-b", 3: "major-c", 4: "major-d"}
        d = trust.start(path, gates)
        self.assertEqual(d["quests_done"], ["world-outside", "major-a"])  # only the gate behind her
        before = d["points"]
        trust.talked(d, "this is a lovely morning", "nice")
        self.assertEqual(d["points"], before + 2, "trust stopped for good: the old gate wasn't counted as done")
        self.assertIsNone(trust.at_gate(d))
        trust._add(d, 1000)
        self.assertEqual((d["points"], trust.at_gate(d)), (109, 2))  # ...and the next gate still holds (110 = stage 3)
        with open(path) as f:
            self.assertNotIn("gates", json.load(f), "the gates come from the character, not the save file")

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

class DiaryTest(unittest.TestCase):
    """The goodbye diary only keeps what the user really said (memory.heard_it)."""
    # the user's own first test sitting: questions about her, nothing about themselves
    ASKED = ["who are you?", "what was that about returning soon when u just got here minutes ago?",
             "dream? but this is not a dream, it's my world", "what sort of magic is that?",
             "republic? republic of..... what?", "no not at all", "bye"]

    def diary(self, user_lines, reply):
        """write_diary over a sitting of these user lines, with the model's answer stood in for."""
        import llm
        messages = []
        for line in user_lines:
            messages += [{"role": "user", "content": line}, {"role": "assistant", "content": "Oh! [nice] [mood: happy]"}]
        real, self.prompt = llm.chat, None
        def chat(msgs, **settings):
            self.prompt = msgs[0]["content"]
            return reply
        llm.chat = chat
        try:
            return [n["text"] for n in memory.write_diary({}, messages, 0, pip())]
        finally:
            llm.chat = real

    def test_the_prompts_own_example_is_never_kept(self):
        self.assertEqual(self.diary(self.ASKED, "- The user's friend NR complains that everyone at their university uses AI."), [])
        self.assertIn("never write it", self.prompt)

    def test_invented_notes_are_dropped_real_ones_kept(self):
        said = ["I just adopted a cat named Mochi, she is very fluffy", "I have an exam this friday and I'm nervous",
                "I went hiking this weekend with my brother"]
        notes = self.diary(said, "- The user adopted a cat named Mochi.\n- The user has an exam on Friday 2026-10-23.\n"
                                 "- The user went hiking with Sam.\n- The user's friend Leo loves football.")
        self.assertEqual(notes, ["The user adopted a cat named Mochi.", "The user has an exam on Friday 2026-10-23."])

    def test_heard_it(self):
        heard = "User: I went hiking this weekend with my brother"
        self.assertTrue(memory.heard_it("The user went hiking with their brother.", heard))
        self.assertFalse(memory.heard_it("The user went hiking with Sam.", heard), "Sam was never mentioned")
        self.assertFalse(memory.heard_it("The user enjoys painting landscapes on weekends.", heard))

class QuestTest(unittest.TestCase):
    def test_flow(self):
        q = quests.Quests(pip())
        s = Save(temp_path(), {"trust": 1, "points": 3, "quests_done": [], "today": {"talk": 0, "minutes": 0}})
        self.assertIsNone(q.due(s))  # the first one waits 30-60 minutes
        q.next = 0
        self.assertTrue(q.due(s))
        self.assertIsNone(q.answered(s, "yes it does", "nice", True))  # too short, and the quest is dropped
        q.next = 0; q.due(s)
        quest_id = q.pending[0]
        self.assertEqual(q.answered(s, "it rains here all the time", "nice", True), quest_id)
        self.assertIn(quest_id, s["quests_done"])
        q.next = 0; q.due(s); q.answered(s, "we eat lots of bread here", "neutral", True)
        q.next = 0
        self.assertIsNone(q.due(s))  # two a day at most

    def test_only_a_real_answer_counts(self):
        q = quests.Quests(pip())
        s = Save(temp_path(), {"trust": 1, "points": 3, "quests_done": [], "today": {"talk": 0, "minutes": 0}})
        self.assertIsNone(q.answer_note(), "no note while she isn't waiting on a quest")
        for judged in (False, None):  # she judged it a non-answer, or forgot to judge it
            q.next = 0; q.due(s)
            self.assertIsNone(q.answered(s, "ajsdasdad oafhoiqwfhef aosidoaidaid burgersssss", "neutral", judged))
            self.assertIsNone(q.pending, "one chance: it's dropped")
        self.assertEqual((s["quests_done"], s["points"]), ([], 3))
        q.next = 0; q.due(s)
        note = q.answer_note()
        self.assertIn(q.topic(q.pending[0]), note)
        self.assertIn("[answered]", note)
        self.assertIn("[not answered]", note)
        self.assertTrue(note.startswith("(Not part of the user's message"))

class AnswerCheckTest(unittest.TestCase):
    """The code's own check on a quest answer, on top of her [answered] tag (quests.is_dodge, looks_like_words)."""
    REAL = [
        "it rains almost every day here and honestly I kind of like it",
        "yes, lots of rain here",
        "Rice, noodles, bread, soup",
        "I'm not sure, but it rains almost every day",
        "I don't know much about gods, but my grandma prays every Sunday",
        "we celebrate Christmas and Lunar New Year with my family",
        "Brrr it's freezing here at night, we use heaters",
        "I study at university, very tiring",
        "honestly no idea how money works, but banks and the government control most of it",
        "I spend most days in front of a laptop writing code",
    ]
    DODGES = ["I don't know, what about you?", "idk lol", "not sure tbh, what about you", "I dont really know, you tell me",
              "no idea honestly", "dunno, and you?", "I have no idea, how about you?", "I’m not sure"]
    JUNK = ["ajsdasdad oafhoiqwfhef aosidoaidaid burgersssss qiwdoqiwhdff", "asdfghjkl qwrtzp zxcvbnm hjkl",
            "aaaa bbbbbb cccc dddd", "hjkhjk sdfsdf lkjlkj qwqwqw"]

    def test_real_answers_pass(self):
        for answer in self.REAL:
            self.assertFalse(quests.is_dodge(answer), answer)
            self.assertTrue(quests.looks_like_words(answer), answer)

    def test_dodges_and_junk_dont(self):
        for answer in self.DODGES:
            self.assertTrue(quests.is_dodge(answer), answer)
        for answer in self.JUNK:
            self.assertFalse(quests.looks_like_words(answer), answer)

    def test_even_if_she_judged_it_answered(self):
        q = quests.Quests(pip())
        s = Save(temp_path(), {"trust": 1, "points": 3, "quests_done": [], "today": {"talk": 0, "minutes": 0}})
        for answer in ("I don't know, what about you?", "ajsdasdad oafhoiqwfhef aosidoaidaid burgersssss qiwdoqiwhdff"):
            q.next = 0; q.due(s)
            self.assertIsNone(q.answered(s, answer, "neutral", True), answer)
        q.next = 0; q.due(s)
        self.assertTrue(q.answered(s, "I'm not sure, but it rains almost every day", "neutral", True))

def gated_save(points=39, trust_level=2, done=()):
    """A save file sitting at Pip's first gate (39 points = the top of stage 1). Returns its path."""
    path = temp_path("gated")
    with open(path, "w") as f:
        json.dump({"trust": trust_level, "points": points, "quests_done": list(done), "last_day": None}, f)
    return path

class MajorQuestTest(unittest.TestCase):
    """quests.MajorQuests: the gates between trust stages ([major_quests] in character.toml)."""

    def setUp(self):
        self.pip = pip()
        self.save = trust.start(gated_save(), self.pip.gates)
        self.major = quests.MajorQuests(self.pip)

    def test_pip_has_four_gates(self):
        self.assertEqual(self.pip.gates, {1: "major-thank-you", 2: "major-first-favour", 3: "major-unanswered",
                                          4: "major-can-i-rest"})

    def test_bad_toml_fails_loudly(self):
        from character import _major_quests
        quest = {"id": "x", "starts": "", "done_when": "", "memory": "", "points": 1}
        with self.assertRaises(ValueError):
            _major_quests({"5": dict(quest)})
        with self.assertRaises(ValueError):
            _major_quests({"1": {"id": "x"}})
        with self.assertRaises(ValueError):
            _major_quests({"1": dict(quest, needs_nice="yes")})
        self.assertTrue(_major_quests({"1": dict(quest)})[1]["needs_nice"], "left out = true (the safer side)")

    def test_needs_nice_per_quest(self):
        self.assertEqual({q["id"]: q["needs_nice"] for q in self.pip.major_quests.values()},
                         {"thank-you": True, "first-favour": False, "unanswered": True, "can-i-rest": True})
        # the herb-naming favour (gate 2): a plain, neutral reply is enough...
        save = trust.start(gated_save(points=109, trust_level=4, done=["major-thank-you"]), self.pip.gates)
        major = quests.MajorQuests(self.pip)
        self.assertEqual(major.active(save)["id"], "first-favour")
        major.due(save)
        self.assertIsNone(major.finished(save, "ugh, fine, call it Sprout", "rude", True), "rude still never counts")
        self.assertTrue(major.finished(save, "how about we name it Sprout?", "neutral", True))
        # ...but the thank-you (gate 1) needs it to feel nice
        self.major.due(self.save)
        self.assertIsNone(self.major.finished(self.save, "thanks I guess, that's a blessing", "neutral", True))
        self.assertTrue(self.major.finished(self.save, "thanks I guess, that's a blessing", "nice", True))

    def test_brought_up_once_a_sitting(self):
        self.assertEqual(self.major.active(self.save)["id"], "thank-you")
        said = self.major.due(self.save)
        self.assertIn(self.pip.major_quests[1]["starts"], said)
        self.assertIsNone(self.major.due(self.save), "only once a sitting")
        self.assertTrue(quests.MajorQuests(self.pip).due(self.save), "the next sitting, again")

    def test_not_active_below_the_gate(self):
        save = trust.start(gated_save(points=30), self.pip.gates)
        self.assertIsNone(self.major.active(save))
        self.assertIsNone(self.major.due(save))

    def test_she_listens_for_a_few_messages(self):
        self.assertIsNone(self.major.answer_note(self.save), "no note before she's brought it up")
        self.major.due(self.save)
        notes = [self.major.answer_note(self.save) for _ in range(quests.LISTEN_FOR + 1)]
        self.assertTrue(all(notes[:-1]) and notes[-1] is None, "she judges LISTEN_FOR messages, then stops")
        self.assertIn("[done]", notes[0])
        self.assertIn(self.pip.major_quests[1]["done_when"], notes[0])

    def test_only_her_done_finishes_it(self):
        self.major.due(self.save)
        for message, feeling, judged in [("thank you so much, that's lovely", "nice", False),   # she said not yet
                                         ("thank you so much, that's lovely", "nice", None),    # she forgot the tag
                                         ("whatever, stop with the blessings", "rude", True),   # rude never counts
                                         ("praying is pretty pointless honestly", "neutral", True),  # not kind
                                         ("I don't know, what about you?", "neutral", True),    # a dodge
                                         ("ajsdasdad oafhoiqwfhef qiwdoqiwhdff", "neutral", True)]:  # mashing
            self.assertIsNone(self.major.finished(self.save, message, feeling, judged), message)
        self.assertEqual((self.save["points"], self.save["trust"]), (39, 2))
        quest = self.major.finished(self.save, "thank you so much, that's lovely", "nice", True)
        self.assertEqual(quest["id"], "thank-you")
        self.assertIn("major-thank-you", self.save["quests_done"])
        self.assertEqual((self.save["points"], self.save["trust"]), (49, 3))  # +10: into stage 2
        self.assertIsNone(self.major.active(self.save), "the gate is open")
        self.assertIsNone(self.major.answer_note(self.save))

class SessionMajorQuestTest(unittest.TestCase):
    """A whole sitting at the first gate, with the model stood in for."""

    def setUp(self):
        import session
        self.session = session
        self.real = session.start_server, session.warm_up, session.ask
        self.notes, self.judged = [], []

        def ask(messages, question, on_text=None, keep=1, moods=None, note=None):
            self.notes.append(note)
            messages += [{"role": "user", "content": question}, {"role": "assistant", "content": "ok [nice]"}]
            return "ok", {}, "nice", "happy", (self.judged.pop(0) if self.judged else None)
        session.start_server = lambda say: None
        session.warm_up = lambda messages, fixed: "loaded"
        session.ask = ask

    def tearDown(self):
        self.session.start_server, self.session.warm_up, self.session.ask = self.real

    def sitting(self, path):
        c = pip()
        c.save_path = path
        return self.session.Session(c, say=lambda *_: None)

    def test_greeting_brings_it_up_and_a_reply_finishes_it(self):
        s = self.sitting(gated_save())
        turn = s.open()
        self.assertTrue(turn.major_raised)
        self.assertIn(s.character.major_quests[1]["starts"], s.messages[-2]["content"])  # (the greeting's cue)
        s.quests.next = 0
        self.assertIsNone(s.wants_to_speak(), "world quests wait while a major quest is active")
        self.judged = [False]
        turn = s.user_says("oh, that's a nice gesture I guess")
        self.assertFalse(turn.major_done)
        self.assertIn("[done]", self.notes[-1])
        self.judged = [True]
        turn = s.user_says("thank you Pip, that really means a lot to me")
        self.assertTrue(turn.major_done and turn.stage_up)
        self.assertEqual(turn.trust_after, 3)
        milestone = [m for m in s.memories if m["kind"] == "milestone"]
        self.assertEqual(len(milestone), 1)
        self.assertIn("thank you Pip, that really means a lot to me", milestone[0]["text"])
        self.assertFalse(s.user_says("so how was your morning?").major_done)
        self.assertIsNone(self.notes[-1], "no more judging once it's done")
        with open(s.character.save_path) as f:
            self.assertIn("major-thank-you", json.load(f)["quests_done"])

    def test_brought_up_after_a_quiet_minute_when_the_gate_is_reached_mid_sitting(self):
        s = self.sitting(gated_save(points=35))  # +3 for the new day: one point short of the gate (39)
        s.open()
        self.assertIsNone(s.major.active(s.save))
        s.user_says("good morning, how are you doing today")  # +2 points: up to the cap (39), not past it
        self.assertEqual((s.save["points"], s.major.active(s.save)["id"]), (39, "thank-you"))
        self.assertIsNone(s.wants_to_speak(), "not right after you spoke")
        s.idle.last -= 61
        cue, kind = s.wants_to_speak()
        self.assertEqual(kind, "major")
        self.assertTrue(s.speak(cue, kind).major_raised)

    def test_old_save_opens_normally(self):
        s = self.sitting(gated_save(points=57, trust_level=3, done=["world-outside"]))
        self.assertFalse(s.open().major_raised)
        self.assertIn("major-thank-you", s.save["quests_done"])

def save_with_minutes(minutes, day=None, trust_level=3):
    """A save file that has already spent `minutes` with her on `day` (today if not given), at this trust level.
    Returns its path."""
    path = temp_path("minutes")
    day = day or datetime.date.today().isoformat()
    with open(path, "w") as f:
        json.dump({"trust": trust_level, "points": trust.TRUST_POINTS[trust_level - 1], "last_day": day,
                   "today": {"talk": 0, "minutes": minutes}}, f)
    return path

class VisitsTest(unittest.TestCase):
    """visits.py: Pip can stay 240 minutes a day (daily_minutes in her character.toml)."""

    def test_her_lines_by_stage(self):
        c = pip()
        self.assertEqual((sorted(c.time_warning), sorted(c.time_up)), ([1, 3], [1, 3]))
        self.assertEqual([c.at_stage({1: "a", 3: "b"}, st) for st in range(1, 6)], ["a", "a", "b", "b", "b"])
        from character import _by_stage
        with self.assertRaises(ValueError):
            _by_stage({"time_up": {"3": "x"}}, "time_up", required=True)  # nothing for stages 1-2
        with self.assertRaises(ValueError):
            _by_stage({"time_up": {"6": "x"}}, "time_up", required=False)
        self.assertEqual(_by_stage({}, "time_up", required=False), {}, "no limit: no lines needed")

    def test_pip_has_four_hours(self):
        minutes = Character("pip").daily_minutes  # (her character.toml as it is, not the test's pip())
        self.assertEqual(minutes, 240, f"Pip's daily_minutes is {minutes} in character.toml: set it back to 240 "
                                       "after testing")

    def test_minutes_used_and_left(self):
        import visits
        today = trust.start(save_with_minutes(100))
        self.assertEqual(visits.minutes_used(today, 5), 105)
        self.assertEqual(visits.minutes_left(today, pip(), 5), 135)
        yesterday = {"last_day": "2000-01-01", "today": {"minutes": 300}}
        self.assertEqual(visits.minutes_used(yesterday, 5), 5, "a new day starts from zero")
        no_limit = pip()
        no_limit.daily_minutes = None
        self.assertIsNone(visits.minutes_left(today, no_limit))

    def test_resting_once_todays_time_is_used(self):
        import visits
        for minutes, day, expected in [(240, None, True), (300, None, True), (239, None, False),
                                       (300, "2000-01-01", False)]:  # used up yesterday: she's back today
            c = pip()
            c.save_path = save_with_minutes(minutes, day)
            self.assertEqual(visits.resting(c), expected, (minutes, day))
        self.assertFalse(visits.resting(pip()), "a first visit (no save yet)")

class SessionTimeLimitTest(unittest.TestCase):
    """A sitting that runs into her daily limit, with the model stood in for."""

    def setUp(self):
        import session
        self.session = session
        self.real = session.start_server, session.warm_up, session.ask

        def ask(messages, question, on_text=None, keep=1, moods=None, note=None):
            messages += [{"role": "user", "content": question}, {"role": "assistant", "content": "ok [nice]"}]
            return "ok", {}, "nice", "happy", None
        session.start_server = lambda say: None
        session.warm_up = lambda messages, fixed: "loaded"
        session.ask = ask

    def tearDown(self):
        self.session.start_server, self.session.warm_up, self.session.ask = self.real

    def sitting(self, minutes, trust_level=3):
        c = pip()
        c.save_path = save_with_minutes(minutes, trust_level=trust_level)
        s = self.session.Session(c, say=lambda *_: None)
        s.open()
        s.quests.next = time.time() + 3600  # (no world quest getting in the way)
        return s

    def spend(self, s, minutes):
        s.opened -= minutes * 60  # as if she'd been open that much longer

    def test_what_she_says_depends_on_her_stage(self):
        """Her body going without food or water is stage 3 lore: before that she just has to go home."""
        body = re.compile(r"body|eaten|drunk|food|water|dreamwalk", re.I)
        for level in (1, 3, 5, 7, 9):  # stages 1-5
            with self.subTest(stage=trust.stage_of(level)):
                s = self.sitting(232, trust_level=level)
                warning, _ = s.wants_to_speak()
                self.spend(s, 10)
                goodbye, _ = s.wants_to_speak()
                shares = trust.stage_of(level) >= 3
                for cue in (warning, goodbye):
                    self.assertEqual(bool(body.search(cue)), shares, cue)
                self.assertIn("about 8 minutes longer", warning)
                self.assertIn("tomorrow", goodbye)
                self.assertNotIn("{", warning + goodbye, "a placeholder wasn't filled in")

    def test_warning_then_goodbye(self):
        s = self.sitting(225)
        self.assertIsNone(s.wants_to_speak(), "15 minutes left: nothing yet")
        self.spend(s, 6)  # 9 minutes left
        cue, kind = s.wants_to_speak()
        self.assertEqual(kind, "time_warning")
        self.assertIn("about 9 minutes longer", cue)
        self.assertFalse(s.speak(cue, kind).time_up)
        self.assertIsNone(s.wants_to_speak(), "the warning comes once")
        self.spend(s, 10)  # past the limit
        cue, kind = s.wants_to_speak()
        self.assertEqual(kind, "time_up")
        self.assertIn("tomorrow", cue)
        self.assertTrue(s.speak(cue, kind).time_up)
        self.assertIsNone(s.wants_to_speak(), "nothing else once she's said goodbye")
        self.assertTrue(s.user_says("wait, one more thing before you go").time_up, "she still answers, then goes")

    def test_one_minute_left_reads_right(self):
        s = self.sitting(239.2)
        cue, kind = s.wants_to_speak()
        self.assertEqual(kind, "time_warning")
        self.assertIn("about 1 minute longer", cue)

    def test_time_is_saved_once_a_minute(self):
        s = self.sitting(10)
        self.spend(s, 3)
        s.wants_to_speak()
        with open(s.character.save_path) as f:
            self.assertAlmostEqual(json.load(f)["today"]["minutes"], 13, delta=0.1)

    def test_snapshot_shows_todays_time(self):
        s = self.sitting(100)
        self.spend(s, 20)
        summary = s.snapshot()["summary"]
        self.assertAlmostEqual(summary["minutes_today"], 120, delta=0.1)
        self.assertEqual(summary["daily_minutes"], 240)

class ClockNudgeTest(unittest.TestCase):
    """idle.CLOCK: she speaks up at 7:00, 12:00, 18:00 and 23:00, once a day each, within 30 minutes after."""

    @staticmethod
    def clock(when):
        """While this is on (a with block), idle.py thinks it's `when` (a datetime)."""
        from unittest import mock
        import idle
        class Clock(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return when
        return mock.patch.object(idle, "datetime", mock.Mock(datetime=Clock, timedelta=datetime.timedelta))

    def at(self, idle_, when):
        """idle_.due() as if the clock said `when`. The quiet nudge can't fire: someone just spoke."""
        idle_.last = idle_.user_last = time.time()
        with self.clock(when):
            return idle_.due()

    def test_greeting_covers_the_moment_she_opens_in(self):
        import idle
        for hour, minute, about in idle.CLOCK:
            with self.subTest(f"{hour:02}:{minute:02}"):
                i = idle.Idle(pip())
                opened = datetime.datetime(2026, 10, 21, hour, minute + 10)
                with self.clock(opened):
                    greeting = i.opening()
                said = pip().fill(about)
                self.assertIn(said[0].upper() + said[1:] + ".", greeting)
                self.assertIsNone(self.at(i, opened + datetime.timedelta(seconds=5)), "she'd greet twice")
                self.assertTrue(self.at(i, opened + datetime.timedelta(days=1)), "tomorrow it comes again")

    def test_greeting_outside_a_moment_knows_the_time_of_day(self):
        import idle
        i = idle.Idle(pip())
        with self.clock(datetime.datetime(2026, 10, 21, 15, 0)):
            greeting = i.opening("Some news.")
        self.assertIn("greets them first. It's afternoon for the user right now (15:00), so she greets them for "
                      "that time of day. Some news.", greeting)
        self.assertEqual(i.fired, set())
        self.assertTrue(self.at(i, datetime.datetime(2026, 10, 21, 18, 5)), "later moments still come")

    def test_greeting_inside_a_moment_says_the_time_once(self):
        import idle
        with self.clock(datetime.datetime(2026, 10, 21, 12, 10)):
            greeting = idle.Idle(pip()).opening()
        self.assertIn("lunchtime", greeting)
        self.assertNotIn("afternoon for the user", greeting)

    def test_part_of_day(self):
        import idle
        at = lambda h, m=0: idle.part_of_day(datetime.datetime(2026, 10, 21, h, m))
        self.assertEqual([at(0), at(4, 59), at(5), at(11, 59), at(12), at(16, 59), at(17), at(20, 59), at(21), at(23, 59)],
                         ["night", "night", "morning", "morning", "afternoon", "afternoon", "evening", "evening",
                          "night", "night"])

    def test_each_fires_once_in_its_window(self):
        import idle
        for hour, minute, about in idle.CLOCK:
            with self.subTest(f"{hour:02}:{minute:02}"):
                i = idle.Idle(pip())
                day = datetime.datetime(2026, 10, 21, hour, minute)
                minutes = lambda m: day + datetime.timedelta(minutes=m)
                self.assertIsNone(self.at(i, minutes(-1)), "too early")
                cue = self.at(i, minutes(0))
                self.assertIn(pip().fill(about), cue)
                self.assertTrue(cue.startswith("(No message from the user."))
                self.assertIsNone(self.at(i, minutes(10)), "only once a day")
                self.assertIsNone(self.at(i, minutes(29)), "only once a day")
                self.assertTrue(self.at(i, minutes(24 * 60 + 5)), "the next day, again")

    def test_window_is_30_minutes(self):
        import idle
        for hour, minute, _ in idle.CLOCK:
            with self.subTest(f"{hour:02}:{minute:02}"):
                start = datetime.datetime(2026, 10, 21, hour, minute)
                self.assertTrue(self.at(idle.Idle(pip()), start + datetime.timedelta(minutes=29, seconds=59)))
                self.assertIsNone(self.at(idle.Idle(pip()), start + datetime.timedelta(minutes=30)))

    def test_quiet_afternoon_has_none(self):
        import idle
        i = idle.Idle(pip())
        for h in range(13, 18):
            self.assertIsNone(self.at(i, datetime.datetime(2026, 10, 21, h, 10)))

def fake_stream(pieces, finish):
    """Stands in for llm.chat_stream: the pieces as the server's chunks, then a last chunk with the timings."""
    chunks = [{"choices": [{"delta": {"content": p}, "finish_reason": None}]} for p in pieces]
    chunks.append({"choices": [{"delta": {}, "finish_reason": finish}], "timings": {"prompt_n": 1}})
    def stream(messages, **settings):
        fake_stream.sent = messages  # what the server was asked (for the note tests)
        return iter(chunks)
    return stream

class AskTest(unittest.TestCase):
    MOODS = {"happy", "neutral", "sad"}

    def ask(self, *pieces, finish="stop", note=None):
        """(reply, feeling, mood, what was streamed to the screen) for a reply made of these pieces.
        Also keeps self.answered (her [answered] tag) and self.messages (the chat afterwards)."""
        real, shown = pet.llm.chat_stream, []
        pet.llm.chat_stream = fake_stream(pieces, finish)
        self.messages = [{"role": "system", "content": "x"}]
        try:
            reply, _, feeling, mood, self.answered = pet.ask(self.messages, "hi", on_text=shown.append,
                                                             moods=self.MOODS, note=note)
        finally:
            pet.llm.chat_stream = real
        return reply, feeling, mood, "".join(shown).rstrip()  # (the space before a tag streams too)

    def test_answered_tag(self):
        for tag, expected in (("[answered]", True), ("[not answered]", False), ("[Not_Answered]", False), ("", None),
                              ("[answered: not answered]", False), ("[quest: answered]", True)):  # (real slips seen)
            with self.subTest(tag):
                reply, feeling, mood, shown = self.ask(f"Oh, rain all day? [nice] [mood: happy] {tag}", note="(note)")
                self.assertEqual((reply, shown, feeling, mood, self.answered),
                                 ("Oh, rain all day?", "Oh, rain all day?", "nice", "happy", expected))
                self.assertNotIn("answered", self.messages[-1]["content"], "her stored reply shouldn't teach the tag")

    def test_note_is_sent_but_not_kept(self):
        self.ask("Okay. [neutral] [mood: neutral] [answered]", note="(Not part of the user's message: judge it.)")
        self.assertEqual(fake_stream.sent[-1]["content"], "hi\n\n(Not part of the user's message: judge it.)")
        self.assertEqual(self.messages[1], {"role": "user", "content": "hi"})
        self.ask("Okay. [neutral] [mood: neutral]")
        self.assertEqual(fake_stream.sent[1]["content"], "hi")  # no note: the question as it is

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

    def app(self, loaded=True, resting=False):
        """The App with a stand-in brain; a.brain.calls lists what it was asked to do (start, close, ...)."""
        from desktop import app as A
        class Signal:
            def connect(self, *_): pass
        class StubBrain:  # the real Brain would start llama-server
            busy = working = False
            def __init__(self):
                self.calls = []
            def __getattr__(self, name):
                if name in ("ready", "speaking", "piece", "spoke", "closed", "snapshot", "failed"):
                    return Signal()
                return lambda *a, **k: self.calls.append(name)
        real = A.Brain
        A.Brain = lambda character: StubBrain()
        try:
            a = A.App(pip(), resting=resting)
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

    def test_status_shows_the_card(self):
        import trust
        data = {"trust": 3, "points": 51, "today": {"talk": 5, "minutes": 139}, "quests_done": [],
                "days_logged": 1, "messages": 0}
        s = trust.summary(data, {i: "x" for i in range(1, 6)})
        self.assertAlmostEqual(s["progress"], (51 - 40) / (70 - 40))
        self.assertEqual(trust.summary(dict(data, trust=10, points=999), {i: "x" for i in range(1, 6)})["progress"], 1.0)
        a = self.app()
        a.snap = {"summary": s, "memories": []}
        a.status()
        from desktop import status
        self.assertTrue(a.bubble.isVisible())
        self.assertTrue(a.bubble.picture.isVisible() and not a.bubble.picture.pixmap().isNull(), "no card shown")
        self.assertEqual(a.bubble.picture.height(), status.HEIGHT, "the card is squashed (an empty bubble)")
        self.assertGreater(a.bubble.height(), status.HEIGHT)
        a.bubble.say("hi")
        self.assertFalse(a.bubble.picture.isVisible(), "the card stays behind her next words")
        self.assertTrue(a.bubble.label.isVisible())
        a.status()  # and again: it still fits after a message in between
        self.assertEqual(a.bubble.picture.height(), status.HEIGHT)

    def test_a_long_message_still_sits_above_her_head(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        from desktop.bubble import Bubble
        b = Bubble()
        b.follow(QPoint(800, 700))
        b.say("hi")  # (a short message first: the long one used to grow the window down from here)
        long = "<br>".join(["✎ The user's friend Mrs. Gable told Pip a story about a ship that never made it back."] * 4)
        b.say("I remember 11 things about you.", note=long)
        QApplication.processEvents()
        self.assertEqual(b.height(), b.layout().totalHeightForWidth(b.width()), "the text doesn't fit")
        self.assertEqual(b.geometry().bottom(), 699, "the bubble covers her head")
        b.hide()

    def test_resting_she_doesnt_come_out(self):
        a = self.app(loaded=False, resting=True)
        self.assertNotIn("start", a.brain.calls, "the model was started for nothing")
        self.assertEqual(a.body.state, "portal")
        self.assertIn("resting back home", a.bubble.label.text())
        self.assertIn("4 hours a day", a.bubble.note.text())
        a.talk()
        self.assertFalse(a.input.isVisible(), "you can't talk to an empty portal")

    def test_no_talking_while_she_speaks(self):
        """Her idle chat and her quest questions can't be cut into: you talk once she's done."""
        for kind in ("idle", "quest", "opening", "user"):
            with self.subTest(kind):
                a = self.app()
                a.on_speaking(kind)  # she starts (the "…" while she thinks)
                a.talk()
                self.assertFalse(a.input.isVisible(), "the box opened while she was talking")
                menu = a.build_menu()  # (kept in a variable: its actions are deleted along with it)
                self.assertFalse(next(x for x in menu.actions() if x.text() == "Talk to her").isEnabled())
                a.on_piece("Do you have bread where you live? ")
                a.talk()
                self.assertFalse(a.input.isVisible(), "the box opened while her words were showing")
                a.bubble.finish("")
                for _ in range(30):  # read to the end (clicking through her bubble)
                    if not a.bubble.active:
                        break
                    a.bubble.mousePressEvent(None)
                    self.pump(0.01)
                self.assertFalse(a.bubble.active)
                a.talk()
                self.assertTrue(a.input.isVisible(), "once she's done, you can talk again")

    def test_no_talking_while_your_message_waits(self):
        a = self.app()
        a.brain.working = True  # (your message is queued, or she's thinking)
        a.talk()
        self.assertFalse(a.input.isVisible())
        a.brain.working = False
        a.talk()
        self.assertTrue(a.input.isVisible())

    def test_no_talking_once_her_goodbye_starts(self):
        """You could keep her from leaving by talking to her during her goodbye: not any more."""
        from session import Turn
        a = self.app()
        a.talk()
        self.assertTrue(a.input.isVisible())
        a.on_speaking("time_up")  # her goodbye starts while the box is open
        self.assertFalse(a.input.isVisible(), "the box you type in should close")
        a.talk()
        self.assertFalse(a.input.isVisible(), "clicking her opened it again")
        menu = a.build_menu()  # (kept in a variable: its actions are deleted along with it)
        talk = next(act for act in menu.actions() if act.text() == "Talk to her")
        self.assertFalse(talk.isEnabled())
        a.send("wait, don't go yet")
        self.assertNotIn("say", a.brain.calls, "your message still reached her")

    def test_no_talking_when_time_runs_out_mid_chat(self):
        from session import Turn
        a = self.app()
        a.bubble.start()
        a.on_spoke(Turn("Oh, that's lovely!", "user", "nice", "happy", 1.0, {}, 3, 3, 50, 51, time_up=True))
        a.talk()
        self.assertFalse(a.input.isVisible())

    def test_time_up_she_goes_home(self):
        from session import Turn
        a = self.app()
        self.assertIn("start", a.brain.calls)
        a.bubble.start()
        a.on_spoke(Turn("I have to wake up now...", "time_up", None, "sad", 1.0, {}, 3, 3, 50, 50, time_up=True))
        self.assertNotIn("close", a.brain.calls, "not before you've read her goodbye")
        a.on_done()
        self.assertTrue(a.leaving and a.going_home)
        self.assertIn("close", a.brain.calls)  # her diary, then she fades away
        a.on_closed([])
        self.assertIn("See you tomorrow", a.bubble.label.text())
        self.assertIn("resting back home until tomorrow", a.bubble.note.text())

    def test_time_up_she_fades_away_and_the_app_closes(self):
        """The whole way out, on real timers: her goodbye, the diary, the wave, the fade, and the app quitting."""
        from session import Turn
        from desktop import app as A, body as B
        quits = []
        class FakeQApplication:  # (stands in for the real quit, which the app hooks up when it's made)
            quit = staticmethod(lambda: quits.append(True))
        real = A.QApplication
        A.QApplication = FakeQApplication
        try:
            a = self.app()
        finally:
            A.QApplication = real
        a.bubble.start()
        a.on_spoke(Turn("I have to go home now...", "time_up", None, "sad", 1.0, {}, 3, 3, 50, 50, time_up=True))
        a.on_done()
        self.assertIn("close", a.brain.calls)
        a.on_closed([])  # (the brain wrote her diary)
        end = time.time() + 1.8 + B.VANISH_SWEEP + 0.25 + B.MOTE_LIFE + 2  # (the wave, then the fade, plus slack)
        while not quits and time.time() < end:
            self.pump(0.02)
        self.assertEqual(a.body.state, "gone", "she never finished fading away")
        self.assertEqual(quits, [True], "she faded away, but the app didn't quit")

    def test_status_shows_her_daily_time(self):
        from desktop import status
        # (the text itself, as the offscreen test platform has no fonts to draw it with)
        s = trust.summary(trust.start(temp_path()), {i: "x" for i in range(1, 6)})
        self.assertEqual(status.clock_text(dict(s, minutes_today=139.4, daily_minutes=240)), "139/240 min")
        self.assertEqual(status.clock_text(dict(s, minutes_today=139.4, daily_minutes=None)), "139 min")
        self.assertEqual(status.clock_text(dict(s, minutes_today=139.4)), "139 min")

    def test_major_quest_notes_under_her_reply(self):
        from session import Turn
        a = self.app()
        a.bubble.start()
        a.on_spoke(Turn("Bless your day!", "opening", None, "happy", 1.0, {}, 2, 2, 39, 39, major_raised=True))
        self.assertIn("Something is on her mind", a.bubble.final_note)
        a.bubble.start()
        a.on_spoke(Turn("Thank you...", "user", "nice", "happy", 1.0, {}, 2, 3, 39, 49, major_done=True))
        self.assertIn("A turning point", a.bubble.final_note)
        self.assertIn("Stage 2", a.bubble.final_note)

    def test_status_card_marks_the_gate(self):
        from desktop import status
        s = trust.summary(trust.start(gated_save(), pip().gates), {i: "x" for i in range(1, 6)})
        self.assertTrue(s["gated"])
        gated, free = status.card(s).toImage(), status.card(dict(s, gated=False)).toImage()
        self.assertNotEqual(gated, free, "the ✻ isn't drawn")

    def test_status_waits_while_she_talks(self):
        a = self.app()
        def enabled():
            menu = a.build_menu()  # (kept in a variable: its actions are deleted along with it)
            return {act.text(): act.isEnabled() for act in menu.actions() if act.text()}
        a.bubble.active = False
        self.assertTrue(enabled()["Status"] and enabled()["What she remembers"])
        a.on_speaking("user")
        self.assertFalse(enabled()["Status"] or enabled()["What she remembers"])
        self.assertFalse(enabled()["Talk to her"], "talking waits too, so you can't cut into her reply")
        self.assertTrue(enabled()["Say goodbye"])

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
        def ask(messages, question, on_text=None, keep=1, moods=None, note=None):
            self.calls["ask"] += 1
            messages.append({"role": "user", "content": question})
            if self.calls["ask"] == 2:  # her first reply to you: the server is gone
                raise llm.ServerGone("test")
            messages.append({"role": "assistant", "content": "ok [nice] [mood: happy]"})
            return "ok", {}, "nice", "happy", None
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
