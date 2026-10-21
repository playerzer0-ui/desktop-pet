"""Every request to llama-server (the model) goes through here, and nowhere else.

    llm.chat_stream(messages, max_tokens=200, ...)  a reply as it's written: yields the server's chunks
    llm.chat(messages, max_tokens=250, ...)         a whole reply at once (the diary)
    llm.template(messages)                          the exact prompt text these messages become
    llm.read(prompt)                                have the model read a prompt without answering (warm-up)
    llm.save_slot(name) / llm.restore_slot(name)    the server's prompt cache, as a file in cache/
    llm.is_up() / llm.model_path()                  is it running, and with which model (server.py)

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

def chat_stream(messages, **settings):
    """Her reply as it's written: yields each chunk the server sends (a dict with "choices", and "timings" at the end).
    settings = max_tokens, temperature, ... for /v1/chat/completions."""
    response = _post("/v1/chat/completions", {"messages": messages, **settings, **NO_THINKING, "stream": True},
                     stream=True)
    response.raise_for_status()
    try:
        # the server sends the reply as lines like:  data: {...json...}
        for line in response.iter_lines():
            if line.startswith(b"data: ") and line != b"data: [DONE]":
                yield json.loads(line[6:])
    except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.Timeout) as e:
        raise ServerGone(f"llama-server stopped in the middle of a reply: {e}") from e

def chat(messages, **settings):
    """A whole reply at once: the text of the model's answer."""
    response = _post("/v1/chat/completions", {"messages": messages, **settings, **NO_THINKING})
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def template(messages):
    """The exact text these messages become in the model's chat template."""
    response = _post("/apply-template", {"messages": messages, **NO_THINKING})
    response.raise_for_status()
    return response.json()["prompt"]

def read(prompt):
    """Have the model read a prompt (into its cache) without writing anything. False if the server refused."""
    return _post("/completion", {"prompt": prompt, "n_predict": 0, "cache_prompt": True}).ok

def save_slot(name):
    """Save what the model has read so far to cache/<name>. False if it couldn't (then it's just read again
    next time: never a reason to stop)."""
    return _post("/slots/0?action=save", {"filename": name}).ok

def restore_slot(name):
    """Load cache/<name> back in. False if the server couldn't (e.g. a llama-server update made it unreadable)."""
    return _post("/slots/0?action=restore", {"filename": name}).ok

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
