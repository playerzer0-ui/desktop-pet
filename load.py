import atexit, glob, os, shutil, subprocess, time, requests

HERE = os.path.dirname(os.path.abspath(__file__))  # the desktop-pet folder
PORT = int(os.environ.get("PET_PORT", 8080))  # override if port 8080 is taken
SERVER = f"http://localhost:{PORT}"
N_CTX = 8192  # context size
MODEL = os.path.join(HERE, "models", "Qwen3.5-2B-Q5_K_M.gguf")

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

def start_server():
    if server_is_up():  # already running (e.g. started by start-server.bat), just use it
        return
    log = open(os.path.join(HERE, "server.log"), "w")  # server messages go here, for debugging
    server = subprocess.Popen(
        [find_llama_server(), "-m", MODEL, "-c", str(N_CTX), "-ngl", "0", "--port", str(PORT)],
        stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,  # no extra black window
    )
    atexit.register(server.terminate)  # shut the server down when the pet closes

    print("Waking up Pip...")
    for _ in range(120):
        if server_is_up():
            return
        if server.poll() is not None:
            raise SystemExit("llama-server crashed while starting. See server.log for details.")
        time.sleep(0.5)
    raise SystemExit("llama-server took too long to start. See server.log for details.")