"""The terminal app: welcome box, an input line, and Pip speaking up on her own while you type.

    python desktop_cli.py
"""
import asyncio, functools, random, time
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from cli import ui
from cli.ui import console
from session import Session

TICK_SECONDS = 5  # how often to check whether Pip wants to speak up
STYLE = Style.from_dict({"bottom-toolbar": "noreverse bg:default"})

class App:
    def __init__(self, session):
        self.s = session
        self.lock = asyncio.Lock()  # Pip says one thing at a time, in order
        self.busy_since = None      # when she started writing her current reply (for the spinner)
        self.verb = ""
        self.writing = ""           # her reply so far, shown above the input line while it streams in
        self.writing_kind = ""
        self.ctx_used = 0
        self.verbose = False

    async def pip(self, kind, call, *args):
        """Run one of the session's calls (it talks to the model, so it runs off the UI thread).
        Her words stream into the area above the input line, then the finished reply is printed."""
        async with self.lock:
            self.busy_since, self.verb = time.time(), random.choice(ui.VERBS)
            self.writing, self.writing_kind = "", kind
            try:
                t = await asyncio.to_thread(functools.partial(call, *args, on_text=self.add_words))
            finally:
                self.busy_since = None
                self.writing = ""
            self.ctx_used = t.context_used
            console.print(ui.turn(t, self.verbose))
            console.print()

    def add_words(self, piece):
        self.writing += piece  # (called from the model thread; the screen redraws on its own every 0.15 s)

    async def ticker(self):
        while True:
            await asyncio.sleep(TICK_SECONDS)
            if not self.lock.locked():
                what = self.s.wants_to_speak()
                if what:
                    await self.pip(what[1], self.s.speak, *what)

    def prompt(self):
        line = FormattedText([(f"fg:{ui.GRAY}", "─" * console.width + "\n"), (f"fg:{ui.GOLD} bold", "❯ ")])
        if not self.writing:
            return line
        return FormattedText(to_formatted_text(ANSI(ui.live(self.writing, self.writing_kind))) + line)

    def toolbar(self):
        return FormattedText(ui.toolbar(self.s.save, self.s.n_ctx, self.ctx_used, self.busy_since,
                                        self.verb, time.time(), self.s.quest_waiting))

    def command(self, text):
        """Handle a /command. Returns False to quit."""
        cmd = text.split()[0].lower()
        if cmd in ("/exit", "/quit"):
            return False
        if cmd == "/help":
            console.print(ui.help_panel())
        elif cmd == "/status":
            console.print(ui.status(self.s.save, self.s.save["today"].get("quests", 0), self.s.quest_waiting))
        elif cmd == "/stats":
            self.verbose = not self.verbose
            console.print(f"[dim]  reply timings {'on' if self.verbose else 'off'}[/]")
        elif cmd == "/memories":
            console.print(ui.memories(self.s.memories))
        elif cmd == "/clear":
            console.clear()
            console.print(ui.header(self.s.save))
        else:
            console.print(f"[dim]  unknown command {cmd}, try [/][accent]/help[/]")
        console.print()
        return True

    async def run(self):
        session = PromptSession(style=STYLE, erase_when_done=True)  # your line is reprinted in its own style
        with patch_stdout(raw=True):  # anything printed (like Pip speaking up) goes above the input line
            asyncio.create_task(self.pip("opening", self.s.open))
            ticker = asyncio.create_task(self.ticker())
            while True:
                try:
                    text = await session.prompt_async(self.prompt, bottom_toolbar=self.toolbar, refresh_interval=0.15)
                except (EOFError, KeyboardInterrupt):
                    break
                text = text.strip()
                if not text:
                    continue
                if text.startswith("/"):
                    if not self.command(text):
                        break
                    continue
                console.print(ui.you(text))
                asyncio.create_task(self.pip("user", self.s.user_says, text))
            ticker.cancel()

def main():
    with console.status(f"[{ui.GOLD}]Waking up Pip…", spinner="dots", spinner_style=ui.GOLD):
        session = Session(say=lambda *_: None)
    note = (f"Pip read her persona and lore in {session.warm_up_seconds:.0f}s (saved, so next time is quick)"
            if session.prompt_was == "read" else None)
    console.print(ui.header(session.save, note))
    console.print()
    try:
        asyncio.run(App(session).run())
    finally:
        with console.status(f"[{ui.GOLD}]Pip is writing in her diary…", spinner="dots", spinner_style=ui.GOLD):
            notes = session.close()
        if notes:
            console.print(ui.diary(notes))
        console.print("[dim]  Pip dreamwalks home. She'll be here when you come back.[/] [flame]✻[/]")
