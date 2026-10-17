import atexit, ctypes, glob, os, shutil, subprocess, time, requests
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))  # the desktop-pet folder
PORT = int(os.environ.get("PET_PORT", 8080))  # override if port 8080 is taken
SERVER = f"http://localhost:{PORT}"
N_CTX = 8192  # context size
MODEL = os.path.join(HERE, "models", "Qwen3.5-4B-Q5_K_M.gguf")

def load(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return f.read()

def find_llama_server():
    # 1. a copy inside the project (how the game will ship)
    local = os.path.join(HERE, "server", "llama-server.exe")
    if os.path.exists(local):
        return local
    # 2. on PATH
    if shutil.which("llama-server"):
        return shutil.which("llama-server")
    # 3. the winget install folder (in case this terminal hasn't picked up the new PATH yet)
    found = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\ggml.llamacpp_*\llama-server.exe"))
    if found:
        return found[0]
    raise SystemExit("Can't find llama-server.exe. Install it with: winget install ggml.llamacpp")

def server_is_up():
    try:
        return requests.get(f"{SERVER}/health", timeout=1).status_code == 200
    except requests.ConnectionError:
        return False

def kill_with_python(proc):
    # Windows "job object": when this Python program ends in ANY way (exit, crash,
    # closed terminal window), Windows automatically kills every process in the job.
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

def running_model():
    try:
        return requests.get(f"{SERVER}/props", timeout=2).json().get("model_path", "")
    except requests.RequestException:
        return ""

def start_server():
    global _job
    if server_is_up():  # already running (e.g. started by start-server.bat), just use it...
        model = os.path.basename(running_model())
        if model.lower() != os.path.basename(MODEL).lower():  # ...but only if it has the right model
            raise SystemExit(
                f"A llama-server with a different model ({model}) is already running on port {PORT}.\n"
                f"Close it (or its start-server.bat window) and run this again.")
        return
    log = open(os.path.join(HERE, "server.log"), "w")  # server messages go here, for debugging
    server = subprocess.Popen(
        [find_llama_server(), "-m", MODEL, "-c", str(N_CTX), "-ngl", "0", "--port", str(PORT)],
        stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,  # no extra black window
    )
    atexit.register(server.terminate)  # shut the server down when the pet closes normally
    _job = kill_with_python(server)    # ...and also if the pet crashes or its window is closed

    print("Waking up Pip...")
    for _ in range(120):
        if server_is_up():
            return
        if server.poll() is not None:
            raise SystemExit("llama-server crashed while starting. See server.log for details.")
        time.sleep(0.5)
    raise SystemExit("llama-server took too long to start. See server.log for details.")