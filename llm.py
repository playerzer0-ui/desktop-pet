"""Every request to llama-server (the model) goes through here, and nowhere else.

    llm.chat_stream(messages, max_tokens=200, ...)  a reply as it's written: yields the server's chunks
    llm.chat(messages, max_tokens=250, ...)         a whole reply at once (the diary)
    llm.template(messages)                          the exact prompt text these messages become
    llm.read(prompt)                                have the model read a prompt without answering (warm-up)
    llm.save_slot(name) / llm.restore_slot(name)    the server's prompt cache, as a file in cache/
    llm.is_up() / llm.model_path() / llm.slots()    is it running, with which model, and how many slots (server.py)

slot = which of the server's slots to use. Each character on the desktop has their own (Pip 0, her friend 1), so
each one's prompt stays read in, and switching between them doesn't mean reading a whole prompt again.

If the server isn't there (closed, crashed, or owned by another copy of the pet that just quit), every call raises
ServerGone, so the caller can start it again and retry (see Session). Every call has a timeout, so a server that
hangs is an error instead of a pet frozen forever.
"""
import json, requests
from config import SERVER

CONNECT_SECONDS = 5    # to reach the server at all
REPLY_SECONDS = 600    # for an answer (or between two streamed pieces): reading a long prompt on CPU is slow
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}  # answer directly, no hidden <think> step

class ServerGone(Exception):
    """llama-server isn't answering: start it again (server.start_server) and retry."""

def _post(path, payload, stream=False):
    try:
        return requests.post(SERVER + path, json=payload, stream=stream, timeout=(CONNECT_SECONDS, REPLY_SECONDS))
    except (requests.ConnectionError, requests.Timeout) as e:
        raise ServerGone(f"llama-server didn't answer {path}: {e}") from e

def chat_stream(messages, slot=0, **settings):
    """Her reply as it's written: yields each chunk the server sends (a dict with "choices", and "timings" at the end).
    settings = max_tokens, temperature, ... for /v1/chat/completions."""
    response = _post("/v1/chat/completions", {"messages": messages, **settings, **NO_THINKING, "stream": True, "id_slot": slot},
                     stream=True)
    response.raise_for_status()
    try:
        # the server sends the reply as lines like:  data: {...json...}
        for line in response.iter_lines():
            if line.startswith(b"data: ") and line != b"data: [DONE]":
                yield json.loads(line[6:])
    except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.Timeout) as e:
        raise ServerGone(f"llama-server stopped in the middle of a reply: {e}") from e

def chat(messages, slot=0, **settings):
    """A whole reply at once: the text of the model's answer."""
    response = _post("/v1/chat/completions", {"messages": messages, **settings, **NO_THINKING, "id_slot": slot})
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def template(messages):
    """The exact text these messages become in the model's chat template."""
    response = _post("/apply-template", {"messages": messages, **NO_THINKING})
    response.raise_for_status()
    return response.json()["prompt"]

def read(prompt, slot=0):
    """Have the model read a prompt (into its cache) without writing anything. False if the server refused."""
    return _post("/completion", {"prompt": prompt, "n_predict": 0, "cache_prompt": True, "id_slot": slot}).ok

def save_slot(name, slot=0):
    """Save what the model has read so far to cache/<name>. False if it couldn't (then it's just read again
    next time: never a reason to stop)."""
    return _post(f"/slots/{slot}?action=save", {"filename": name}).ok

def restore_slot(name, slot=0):
    """Load cache/<name> back in. False if the server couldn't (e.g. a llama-server update made it unreadable)."""
    return _post(f"/slots/{slot}?action=restore", {"filename": name}).ok

def is_up():
    try:
        return requests.get(SERVER + "/health", timeout=1).status_code == 200
    except requests.RequestException:
        return False

def model_path():
    """The model file the running server has loaded ("" if it can't say)."""
    try:
        return requests.get(SERVER + "/props", timeout=2).json().get("model_path", "")
    except (requests.RequestException, ValueError):
        return ""

def slots():
    """How many conversation slots the running server has (0 if it can't say)."""
    try:
        return int(requests.get(SERVER + "/props", timeout=2).json().get("total_slots", 0))
    except (requests.RequestException, ValueError, TypeError):
        return 0
