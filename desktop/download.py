"""First launch: the model (config.MODEL_URL, ~3 GB) isn't there yet, so a small window downloads it into the
player's data folder (config.DATA/models), once. It resumes where it left off if the game was closed or the
connection dropped, checks there's room first, and checks the SHA-256 before the model is used.

    desktop.download.ensure_model()   True once the model is there (downloading it first if needed), False if the
                                      player closed the window
    fetch(url, path, sha256, size)    the download itself, no window (setup scripts and tests can use it)
"""
import hashlib, os, shutil, threading, time
import requests
from PySide6.QtCore import QEventLoop, QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget
import config

CHUNK = 1 << 20  # 1 MB
ROOM = 200 * 1024 ** 2  # free space to leave over, on top of the model

class Stopped(Exception):
    pass

def fetch(url, path, sha256, size, progress=lambda stage, done, total: None, stop=None):
    """Download url to path (via path + ".part", so a half download is never taken for the model), resuming a
    .part left by an earlier try. progress(stage, done, total) with stage "checking" (hashing what's already
    there) or "downloading". stop = a threading.Event: set it to stop (raises Stopped; the .part is kept)."""
    stop = stop or threading.Event()
    part = path + ".part"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    done = os.path.getsize(part) if os.path.exists(part) else 0
    digest = hashlib.sha256()
    if done:  # resuming: the checksum has to include what's already there
        with open(part, "rb") as f:
            read = 0
            for block in iter(lambda: f.read(CHUNK * 8), b""):
                if stop.is_set():
                    raise Stopped()
                digest.update(block)
                read += len(block)
                progress("checking", read, done)
    free = shutil.disk_usage(os.path.dirname(path)).free
    if free < size - done + ROOM:
        raise OSError(f"Not enough free space in {os.path.dirname(path)}: it needs about "
                      f"{(size - done + ROOM) / 1024 ** 3:.1f} GB, and {free / 1024 ** 3:.1f} GB is free.")
    headers = {"Range": f"bytes={done}-"} if done else {}
    with requests.get(url, headers=headers, stream=True, timeout=30) as r:
        if done and r.status_code == 416:  # (it was all there already)
            pass
        else:
            r.raise_for_status()
            if done and r.status_code != 206:  # the server sent the whole file instead of the rest: start over
                done, digest = 0, hashlib.sha256()
            total = done + int(r.headers.get("Content-Length") or (size - done))
            with open(part, "ab" if done else "wb") as f:
                for chunk in r.iter_content(CHUNK):
                    if stop.is_set():
                        raise Stopped()
                    f.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    progress("downloading", done, total)
    if digest.hexdigest().lower() != sha256.lower():
        os.remove(part)
        raise ValueError("The download was damaged (its checksum doesn't match), so it was thrown away. "
                         "Try again.")
    os.replace(part, path)
    return path

def _size(n):
    return f"{n / 1024 ** 3:.1f} GB" if n >= 1024 ** 3 else f"{n / 1024 ** 2:.0f} MB"

class _Bridge(QObject):  # (the download runs on its own thread; Qt widgets only change on the main one)
    progress = Signal(str, float, float)
    finished = Signal(str)  # "" when done, else what went wrong ("stopped" if the player closed it)

class DownloadWindow(QWidget):
    def __init__(self, name="Pip"):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Desktop Pet: first launch")
        self.setFixedWidth(440)
        self.title = QLabel(f"{name} needs her mind before she can visit.")
        self.title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.text = QLabel(f"It's a one-time download of {_size(config.MODEL_SIZE)}. If it's interrupted, "
                           "it carries on from where it stopped next time.", wordWrap=True)
        self.bar = QProgressBar(maximum=1000, textVisible=False)
        self.status = QLabel("Starting…")
        self.retry, self.cancel = QPushButton("Try again"), QPushButton("Cancel")
        self.retry.hide()
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.retry)
        buttons.addWidget(self.cancel)
        layout = QVBoxLayout(self)
        for w in (self.title, self.text, self.bar, self.status):
            layout.addWidget(w)
        layout.addLayout(buttons)
        self.bridge = _Bridge()
        self.bridge.progress.connect(self._show)
        self.bridge.finished.connect(self._finished)
        self.retry.clicked.connect(self.start)
        self.cancel.clicked.connect(self.close)
        self.stop = threading.Event()
        self.result = None  # True = done, False = closed
        self.done = QEventLoop()
        self._speed = []  # (time, bytes) samples, for the speed and time left

    def start(self):
        self.retry.hide()
        self.status.setText("Starting…")
        self.stop.clear()
        self._speed = []
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            fetch(config.MODEL_URL, config.MODEL, config.MODEL_SHA256, config.MODEL_SIZE,
                  progress=lambda stage, done, total: self.bridge.progress.emit(stage, done, total), stop=self.stop)
            self.bridge.finished.emit("")
        except Stopped:
            self.bridge.finished.emit("stopped")
        except requests.RequestException:
            self.bridge.finished.emit("Couldn't reach the download. Check your internet connection, then try again.")
        except Exception as e:
            self.bridge.finished.emit(str(e))

    def _show(self, stage, done, total):
        self.bar.setValue(int(1000 * done / total) if total else 0)
        if stage == "checking":
            self.status.setText(f"Checking what was already downloaded… {_size(done)} of {_size(total)}")
            return
        now = time.time()
        self._speed = [(t, b) for t, b in self._speed if now - t < 8] + [(now, done)]
        (t0, b0), rate = self._speed[0], 0
        if now - t0 > 1:
            rate = (done - b0) / (now - t0)
        left = f" · about {max(1, round((total - done) / rate / 60))} min left" if rate else ""
        self.status.setText(f"{_size(done)} of {_size(total)}" + (f" · {rate / 1024 ** 2:.1f} MB/s" if rate else "") + left)

    def _finished(self, problem):
        if not problem:
            self.result = True
            self.done.quit()
            self.hide()
        elif problem != "stopped":
            self.status.setText(problem)
            self.retry.show()

    def closeEvent(self, e):
        if self.result is None:
            self.stop.set()
            self.result = False
            self.done.quit()
        super().closeEvent(e)

def ensure_model(name="Pip"):
    """True once the model is there: right away if it already is, else after the download window is done.
    False if the player closed the window (the game should quit then). Needs a QApplication."""
    if os.path.exists(config.MODEL):
        return True
    window = DownloadWindow(name)
    window.show()
    window.start()
    window.done.exec()
    return bool(window.result)
