"""A QPainter that always ends, and writes down what went wrong.

An error halfway through a paint used to skip painter.end(): Qt then printed "endPaint() called with active painter"
every frame, and the traceback that explained it scrolled out of the terminal. Now each different error is kept in
logs/paint.log (once per run, with the time), and the painter is always ended.
"""
import contextlib, datetime, os, sys, traceback
from PySide6.QtGui import QPainter
from engine.config import LOG_DIR

PATH = os.path.join(LOG_DIR, "paint.log")
_seen = set()  # tracebacks already written this run (a broken paint fails every frame)

@contextlib.contextmanager
def painter(device, where):
    """with painter(self, "her body") as p: ... An error inside is logged and swallowed: one bad frame
    shouldn't close the game."""
    p = QPainter(device)
    try:
        yield p
    except Exception:
        log(where, traceback.format_exc())
    finally:
        if p.isActive():
            p.end()

def log(where, details):
    if details in _seen:
        return
    _seen.add(details)
    print(f"painting {where} failed (written to {PATH}):\n{details}", file=sys.stderr)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  painting {where}\n{details}\n")
    except OSError:
        pass
