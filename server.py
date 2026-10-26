"""Starting llama-server (the model) and making sure it dies with the pet, on Windows and on Linux.

    start_server()   use the one already running on PORT, or start our own and wait until it's ready

Talking to it is llm.py's job; this file only owns the process.
"Dies with the pet" means even when the pet crashes or is killed, so a 3 GB model isn't left running:
    Windows   a job object (kill_with_python): Windows ends the server the moment the pet's process ends
    Linux     a small shell watchdog (WATCHDOG) runs the server, checks every second that the pet is still there,
              and stops the server when it isn't
"""
import atexit, ctypes, glob, os, shutil, subprocess, sys, threading, time
import llm
from config import HERE, LOG_DIR, PORT, N_CTX, MODEL, CACHE_DIR

WINDOWS = os.name == "nt"

def find_llama_server():
    # 1. a copy inside the project (how the game will ship)
    local = os.path.join(HERE, "server", "llama-server.exe" if WINDOWS else "llama-server")
    if os.path.exists(local):
        return local
    # 2. on PATH
    if shutil.which("llama-server"):
        return shutil.which("llama-server")
    if WINDOWS:
        # 3. the winget install folder (in case this terminal hasn't picked up the new PATH yet)
        found = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\ggml.llamacpp_*\llama-server.exe"))
        if found:
            return found[0]
        raise SystemExit("Can't find llama-server.exe. Install it with: winget install ggml.llamacpp")
    # 3. where llama.cpp usually lands on Linux when it isn't on PATH (built from source, or Homebrew)
    for spot in ("~/llama.cpp/build/bin/llama-server", "~/.local/bin/llama-server",
                 "/home/linuxbrew/.linuxbrew/bin/llama-server"):
        if os.access(os.path.expanduser(spot), os.X_OK):
            return os.path.expanduser(spot)
    raise SystemExit("Can't find llama-server. Install llama.cpp (for example: brew install llama.cpp), or download\n"
                     "a release from https://github.com/ggml-org/llama.cpp/releases and put llama-server in the server/\n"
                     "folder or on your PATH.")

# Linux: runs llama-server ("$@") and stops it when the pet (process $parent) is gone, checked every second, or as
# soon as this script is asked to stop (the pet closing normally, atexit). It ends when the server does, with its
# exit code, so start_server still notices a server that crashed while starting.
WATCHDOG = """
parent=$1; shift
"$@" &
child=$!
trap 'kill "$child" 2>/dev/null; wait "$child"; exit 0' TERM INT HUP
while kill -0 "$parent" 2>/dev/null && kill -0 "$child" 2>/dev/null; do sleep 1; done
kill "$child" 2>/dev/null
wait "$child"
"""

def kill_with_python(proc):
    # Windows "job object": when this Python program ends in ANY way (exit, crash,
    # closed terminal window), Windows automatically kills every process in the job.
    from ctypes import wintypes  # (Windows only)
    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC_LIMITS(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD)]

    class EXTENDED_LIMITS(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMITS), ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)

    limits = EXTENDED_LIMITS()
    limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    kernel32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(limits), ctypes.sizeof(limits))
    kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(proc._handle)))
    return job  # must be kept alive: when the handle closes, the server is killed

def server_env(llama_server):
    """Linux: llama-server loads its libraries (libllama.so, libggml*.so) from its own folder. The built game's
    launcher points LD_LIBRARY_PATH at the game's _internal folder (keeping the player's own in
    LD_LIBRARY_PATH_ORIG), so the server gets its own folder first, then whatever the player had."""
    env = dict(os.environ)
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is None:
        original = env.get("LD_LIBRARY_PATH", "") if not hasattr(sys, "frozen") else ""
    env["LD_LIBRARY_PATH"] = os.pathsep.join(p for p in (os.path.dirname(llama_server), original) if p)
    return env

_starting = threading.Lock()  # two characters on the desktop each start their mind: only one may start the server

def start_server(say=print, slots=1):
    """say = how to show the startup message. slots = how many characters will use it at once (one slot each,
    each with the full N_CTX context)."""
    with _starting:
        _start(say, slots)

def _start(say, slots):
    global _job
    if llm.is_up():  # already running (e.g. started by start-server.bat), just use it...
        model = os.path.basename(llm.model_path())
        if model.lower() != os.path.basename(MODEL).lower():  # ...but only if it has the right model
            raise SystemExit(
                f"A llama-server with a different model ({model}) is already running on port {PORT}.\n"
                f"Close it (or its start-server.bat window) and run this again.")
        if llm.slots() < slots:  # ...and enough slots for everyone on the desktop
            raise SystemExit(
                f"The llama-server already running on port {PORT} has {llm.slots()} slot(s), and {slots} characters "
                f"need {slots}.\nClose it (or its start-server.bat window) and run this again.")
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    log = open(os.path.join(LOG_DIR, "server.log"), "w")  # server messages go here, for debugging
    command = [find_llama_server(), "-m", MODEL, "-c", str(N_CTX * slots), "-ngl", "0", "--port", str(PORT),
               "-np", str(slots),  # one conversation slot per character (the context is split between them,
                                   # so each gets N_CTX), and each request names its own (llm.py's slot)
               "--slot-save-path", CACHE_DIR]
    if WINDOWS:
        server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW)  # no extra black window
        _job = kill_with_python(server)  # ...it dies with the pet, even if the pet crashes or is killed
    else:
        server = subprocess.Popen(["sh", "-c", WATCHDOG, "watchdog", str(os.getpid())] + command,
                                  stdout=log, stderr=subprocess.STDOUT, env=server_env(command[0]),
                                  start_new_session=True)  # (Ctrl+C in the terminal reaches only the pet)
    atexit.register(server.terminate)  # shut the server down when the pet closes normally

    say("Waking up...")
    for _ in range(120):
        if llm.is_up():
            return
        if server.poll() is not None:
            raise SystemExit(f"llama-server crashed while starting. See {os.path.join(LOG_DIR, 'server.log')} for details.")
        time.sleep(0.5)
    raise SystemExit(f"llama-server took too long to start. See {os.path.join(LOG_DIR, 'server.log')} for details.")