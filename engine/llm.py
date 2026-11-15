"""Every request to llama-server goes through here. slot = which server slot: each character on the desktop
has her own, so her prompt stays read in. If the server is gone, calls raise ServerGone so the caller can
restart it and retry. Every call has a timeout, so a hung server is an error, not a frozen pet.
"""
import json, requests
from engine.config import SERVER

CONNECT_SECONDS = 5
REPLY_SECONDS = 600    # reading a long prompt on CPU is slow
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}  # no hidden <think> step

class ServerGone(Exception):
    pass

def _post(path, payload, stream=False):
    try:
        return requests.post(SERVER + path, json=payload, stream=stream, timeout=(CONNECT_SECONDS, REPLY_SECONDS))
    except (requests.ConnectionError, requests.Timeout) as e:
        raise ServerGone(f"llama-server didn't answer {path}: {e}") from e

_strict = None  # whether the model's chat format refuses two messages in a row from the same side (asked once)

def alternates():
    """True for a model whose chat format needs user and assistant to take turns (Gemma: two user messages in a row,
    her memories and then your message, are refused with an error). Qwen takes them as they are."""
    global _strict
    if _strict is None:
        two = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
        try:
            _strict = not requests.post(SERVER + "/apply-template", json={"messages": two}, timeout=10).ok
        except requests.RequestException:
            return False  # no server to ask yet: ask again next time
    return _strict

def fit(messages):
    """The messages as this model can take them: for one that needs turns to alternate, messages in a row from the
    same side are joined into one."""
    if not alternates():
        return messages
    joined = []
    for m in messages:
        if joined and joined[-1]["role"] == m["role"]:
            joined[-1] = {"role": m["role"], "content": joined[-1]["content"] + "\n\n" + m["content"]}
        else:
            joined.append(dict(m))
    return joined

def chat_stream(messages, slot=0, **settings):
    """Her reply as it's written: yields each chunk the server sends ("timings" in the last)."""
    response = _post("/v1/chat/completions", {"messages": fit(messages), **settings, **NO_THINKING, "stream": True, "id_slot": slot},
                     stream=True)
    response.raise_for_status()
    try:
        for line in response.iter_lines():  # lines like:  data: {...json...}
            if line.startswith(b"data: ") and line != b"data: [DONE]":
                yield json.loads(line[6:])
    except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.Timeout) as e:
        raise ServerGone(f"llama-server stopped in the middle of a reply: {e}") from e

def chat(messages, slot=0, **settings):
    """A whole reply at once (the diary)."""
    response = _post("/v1/chat/completions", {"messages": fit(messages), **settings, **NO_THINKING, "id_slot": slot})
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def pick(messages, words, slot=0):
    """A one-word answer that can only be one of `words`: the server's grammar allows nothing else, so there is
    always an answer and never a made-up one (the judge: mind/judge.py)."""
    grammar = "root ::= " + " | ".join(json.dumps(word) for word in words)
    response = _post("/v1/chat/completions", {"messages": fit(messages), "grammar": grammar, "temperature": 0,
                                              "max_tokens": 4, **NO_THINKING, "id_slot": slot, "cache_prompt": True})
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()

def template(messages):
    """The exact text these messages become in the model's chat template."""
    response = _post("/apply-template", {"messages": fit(messages), **NO_THINKING})
    response.raise_for_status()
    return response.json()["prompt"]

def read(prompt, slot=0):
    """Have the model read a prompt without answering. Returns its size in tokens (0 if refused)."""
    response = _post("/completion", {"prompt": prompt, "n_predict": 0, "cache_prompt": True, "id_slot": slot})
    return response.json().get("tokens_evaluated", 0) if response.ok else 0

def save_slot(name, slot=0):
    """Save what the model has read to cache/<name>. False if it couldn't (it's just read again next time)."""
    return _post(f"/slots/{slot}?action=save", {"filename": name}).ok

def restore_slot(name, slot=0):
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
    """How many slots the running server has (0 if it can't say)."""
    try:
        return int(requests.get(SERVER + "/props", timeout=2).json().get("total_slots", 0))
    except (requests.RequestException, ValueError, TypeError):
        return 0
