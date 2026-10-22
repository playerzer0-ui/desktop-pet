"""Where things are and how the model runs: paths, the server's port, the context size."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))  # the desktop-pet folder
PORT = int(os.environ.get("PET_PORT", 8080))  # override if port 8080 is taken
SERVER = f"http://127.0.0.1:{PORT}"  # (not "localhost": on Windows that tries IPv6 ::1 first, where llama-server
                                     #  isn't listening, and every request waited ~2 s for that to fail)
N_CTX = 8192  # context size
MODEL = os.path.join(HERE, "models", "Qwen3.5-4B-Q5_K_M.gguf")
# where setup.ps1 downloads it from, and its checksum (change all three together to switch models)
MODEL_URL = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q5_K_M.gguf"
MODEL_SHA256 = "8814232b85594dcd46c50e5b8b29324a7efe9e746edbe8a3d1df3d3fce7aad39"
CACHE_DIR = os.path.join(HERE, "cache")  # each character's already-read system prompt, saved by the server (see pet.warm_up)
