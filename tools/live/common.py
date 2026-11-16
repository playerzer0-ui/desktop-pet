"""What every live tool shares: which model to run, a throwaway data folder and a port of its own, so a live run
never touches your real saves or a pet that's already running.

use() must be called before anything from engine/, mind/ or desktop/ is imported: engine.server reads the model,
port and checkpoints from engine.config when it is first imported.
"""
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
for stream in (sys.stdout, sys.stderr):  # her "…" and "’" on a Windows console
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# name -> (file in models/, --ctx-checkpoints). The checkpoint counts are the ones measured in engine/config.py
MODELS = {
    "gemma": ("gemma-3-4b-it-Q5_K_M.gguf", 4),
    "qwen": ("Qwen3.5-4B-Q5_K_M.gguf", 2),
}
PORT = 8091  # (the pet uses 8080: a live run can go while she's on the desktop)

def use(model=None, port=PORT, data=None):
    """Point the game at `model` (a name in MODELS, or None for the one engine/config.py ships), a fresh data
    folder (or `data`) and `port`. Returns engine.config."""
    os.environ["PET_DATA_DIR"] = data or tempfile.mkdtemp(prefix="pet-live-")
    os.environ["PET_PORT"] = str(port)
    if "engine.server" in sys.modules:
        raise RuntimeError("common.use() came too late: engine.server was already imported")
    from engine import config
    if model:
        if model not in MODELS:
            raise SystemExit(f"Unknown model {model!r}. Known: {', '.join(MODELS)}")
        config.MODEL_FILE, config.MODEL_CHECKPOINTS = MODELS[model]
        config.MODEL = config._model()
    if not os.path.exists(config.MODEL):
        raise SystemExit(f"No model file at {config.MODEL}. Put {config.MODEL_FILE} in models/ first.")
    for folder in (config.SAVES_DIR, config.LOG_DIR, config.CACHE_DIR):
        os.makedirs(folder, exist_ok=True)
    return config

def load_scene(path):
    """A scene file (tools/live/scenes/): who, an optional save to start from, and the messages to send."""
    with open(path, encoding="utf-8") as f:
        scene = json.load(f)
    scene["messages"] = [m if isinstance(m, dict) else {"say": m} for m in scene.get("messages", [])]
    return scene

def seed_save(character, save):
    """Start her from this save (a scene's "save"), or from nothing."""
    if os.path.exists(character.save_path):
        os.remove(character.save_path)
    if save:
        os.makedirs(os.path.dirname(character.save_path), exist_ok=True)
        with open(character.save_path, "w", encoding="utf-8") as f:
            json.dump(save, f)

def server_process(port=PORT):
    """The llama-server listening on `port`, as a psutil.Process (None if there isn't one)."""
    import psutil
    for p in psutil.process_iter(["name"]):
        if "llama-server" not in (p.info["name"] or ""):
            continue
        try:
            if any(c.laddr.port == port and c.status == psutil.CONN_LISTEN for c in p.net_connections("tcp")):
                return p
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return None

def memory_mb(process):
    """(working set, private bytes) in MB. Task Manager's "Memory" column is the private one on Windows;
    on Linux both are the resident size."""
    info = process.memory_info()
    private = getattr(info, "private", info.rss)
    return info.rss / 2**20, private / 2**20
