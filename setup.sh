#!/usr/bin/env bash
# Sets up the desktop pet on Linux (setup.ps1 / setup.bat is the Windows one). Run: ./setup.sh
# Safe to run again: every step skips what is already done.
#
#   1. Python 3.11 or newer   (installing it needs your password, so this only tells you how)
#   2. .venv and packages     the project's own Python, with requirements.txt
#   3. llama-server           found the same way the pet looks for it (server.py), or how to get it
#   4. the model              downloads config.MODEL_URL into models/ and checks its SHA-256
#   5. a quick check          the mood lists and the tests (no model needed)
#
# Then start her with ./start.sh
cd "$(dirname "$0")" || exit 1
VENV_PYTHON=".venv/bin/python"

step() { printf '\n\033[33m== %s\033[0m\n' "$1"; }
ok()   { printf '   \033[32m%s\033[0m\n' "$1"; }
note() { printf '   %s\n' "$1"; }
fail() { printf '   \033[31m%s\033[0m\n' "$1"; exit 1; }

# --- 1. Python ---
step "1/5  Python 3.11 or newer"
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [ -x "$VENV_PYTHON" ]; then
    ok "already set up (.venv)"
elif [ -z "$PYTHON" ]; then
    note "Python 3.11 or newer isn't installed. Install it, then run this again, for example:"
    note "  Ubuntu / Debian:  sudo apt install python3 python3-venv"
    note "  Fedora:           sudo dnf install python3"
    note "  Arch:             sudo pacman -S python"
    fail "No Python 3.11+ found."
else
    ok "found: $PYTHON ($("$PYTHON" --version 2>&1))"
fi

# --- 2. .venv and packages ---
step "2/5  The project's Python (.venv) and its packages"
if [ ! -x "$VENV_PYTHON" ]; then
    if ! "$PYTHON" -m venv .venv || [ ! -x "$VENV_PYTHON" ]; then
        rm -rf .venv
        note "On Ubuntu / Debian, venv is a separate package: sudo apt install python3-venv"
        fail "Couldn't create .venv."
    fi
    ok "created .venv"
fi
"$VENV_PYTHON" -m pip install --disable-pip-version-check --quiet -r requirements.txt ||
    fail "Installing requirements.txt failed (see above)."
ok "packages installed"

# --- 3. llama-server ---
step "3/5  llama-server (runs the model)"
if found=$("$VENV_PYTHON" -c "import server; print(server.find_llama_server())" 2>/dev/null); then
    ok "found: $found"
else
    note "llama-server (from llama.cpp) isn't installed. Any one of these works:"
    note "  - Homebrew:  brew install llama.cpp"
    note "  - a ready-made build: https://github.com/ggml-org/llama.cpp/releases (an ubuntu-x64 zip),"
    note "    then put its llama-server (and the files next to it) in this project's server/ folder"
    note "  - or build llama.cpp yourself; ~/llama.cpp/build/bin/llama-server is found too"
    fail "Then run ./setup.sh again."
fi

# --- 4. the model ---
step "4/5  The model"
read -r MODEL_PATH MODEL_URL MODEL_SHA < <("$VENV_PYTHON" -c "import config; print(config.MODEL, config.MODEL_URL, config.MODEL_SHA256)") ||
    fail "Couldn't read MODEL, MODEL_URL and MODEL_SHA256 from config.py."
NAME=$(basename "$MODEL_PATH")
intact() {
    note "Checking $(basename "$1") (takes a little while for a few GB)..."
    [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$(echo "$MODEL_SHA" | tr 'A-F' 'a-f')" ]
}
if [ -f "$MODEL_PATH" ] && intact "$MODEL_PATH"; then
    ok "$NAME is already here and intact"
else
    if [ -f "$MODEL_PATH" ]; then
        note "$NAME is there but doesn't match its checksum (incomplete or a different file): downloading it again."
        rm -f "$MODEL_PATH"
    fi
    mkdir -p "$(dirname "$MODEL_PATH")"
    free_kb=$(df -Pk "$(dirname "$MODEL_PATH")" | awk 'NR == 2 {print $4}')
    if [ "${free_kb:-0}" -lt $((4 * 1024 * 1024)) ]; then
        fail "Not enough free space for the model (about 4 GB needed, $((free_kb / 1024 / 1024)) GB free)."
    fi
    command -v curl >/dev/null 2>&1 || fail "curl is needed to download the model (for example: sudo apt install curl)."
    note "Downloading $NAME from $MODEL_URL"
    note "(If it stops, run ./setup.sh again: it carries on where it left off.)"
    curl --location --fail --continue-at - --progress-bar --output "$MODEL_PATH.part" "$MODEL_URL" ||
        fail "The download stopped (curl exit code $?). Run ./setup.sh again to carry on."
    if ! intact "$MODEL_PATH.part"; then
        rm -f "$MODEL_PATH.part"
        fail "The downloaded file doesn't match its checksum, so it was deleted. Run ./setup.sh again."
    fi
    mv -f "$MODEL_PATH.part" "$MODEL_PATH"
    ok "$NAME downloaded and checked"
fi

# --- 5. a quick check ---
step "5/5  A quick check"
"$VENV_PYTHON" -m desktop.check || fail "The character's files don't agree (see above)."
if output=$("$VENV_PYTHON" -m unittest discover -s tests 2>&1); then
    ok "$(echo "$output" | grep -E '^Ran [0-9]+ tests?' | tail -1): all passed"
    printf '\n\033[32mAll set. Start her with ./start.sh\033[0m\n'
else
    # each problem is "FAIL: <test>" (a check came out wrong) or "ERROR: <test>" (it crashed), then a traceback whose
    # last line says what's wrong and how to fix it (our tests write it that way)
    echo "$output" | awk '
        /^(FAIL|ERROR): / { if (name) print_it(); name = $2; kind = $1; why = ""; under = 1; next }
        name && under && /^-+$/ { under = 0; next }  # (the rule right under the test name, before its traceback)
        name && /^(=+|-+)$/ { print_it(); name = ""; next }
        name && NF { why = $0 }
        END { if (name) print_it() }
        function print_it() { sub(/^AssertionError: /, "", why); sub(/^.* : /, "", why)
                              printf "\n   \033[31m%s %s\033[0m\n            %s\n", (kind == "FAIL:" ? "Failed " : "Crashed"), name, why }'
    printf '\n   \033[31m%s: some failed (above).\033[0m\n' "$(echo "$output" | grep -E '^Ran [0-9]+ tests?' | tail -1)"
    note "The pet may still run. For the full details: .venv/bin/python -m unittest discover -s tests"
    printf '\n\033[33mSet up, but with the test problems above. You can still try ./start.sh\033[0m\n'
fi
