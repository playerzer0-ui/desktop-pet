"""Where things are and how the model runs: paths, the server's port, the context size."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))  # the desktop-pet folder
PORT = int(os.environ.get("PET_PORT", 8080))  # override if port 8080 is taken
SERVER = f"http://127.0.0.1:{PORT}"  # (not "localhost": on Windows that tries IPv6 ::1 first, where llama-server
                                     #  isn't listening, and every request waited ~2 s for that to fail)
N_CTX = 8192  # context size
MODEL = os.path.join(HERE, "models", "Qwen3.5-4B-Q5_K_M.gguf")
CACHE_DIR = os.path.join(HERE, "cache")  # each character's already-read system prompt, saved by the server (see pet.warm_up)
