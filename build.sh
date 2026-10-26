#!/usr/bin/env bash
# Builds the Linux game: dist/DesktopPet/DesktopPet (a folder, run it from there), and the same folder packed as
# dist/DesktopPet-linux.tar.gz (what goes on itch.io; a tar keeps the files' "runnable" flag, a zip often loses it).
# build.ps1 is the Windows one. Run it on Linux, after ./setup.sh has worked once:
#     ./build.sh
# The build only runs on Linux versions at least as new as the one it was made on (their C library, glibc), so
# build on an older one (Ubuntu 22.04, say) to reach the most players.
# Steps:
#   1. PyInstaller, into the project's own Python (.venv)
#   2. llama-server's files, copied from the one setup.sh found (only what the game needs)
#   3. the build itself (DesktopPet.spec)
#   4. a check that the built server starts, and that Qt has the system libraries it needs
#   5. the licenses: THIRD_PARTY_NOTICES.txt and licenses/ in the build (build_notices.py)
#   6. the tar.gz
cd "$(dirname "$0")" || exit 1
PYTHON=".venv/bin/python"

step() { printf '\n\033[36m%s\033[0m\n' "$1"; }
note() { printf '     %s\n' "$1"; }
fail() { printf '\033[31m%s\033[0m\n' "$1"; exit 1; }

[ "$(uname -s)" = "Linux" ] || fail "This builds the Linux game, so it has to run on Linux (build.ps1 is the Windows one)."
[ -x "$PYTHON" ] || fail "Run ./setup.sh first (there's no .venv yet)."

step "1/6  PyInstaller"
"$PYTHON" -m pip install --disable-pip-version-check --quiet pyinstaller || fail "Couldn't install PyInstaller."

step "2/6  llama-server"
found=$("$PYTHON" -c "import server; print(server.find_llama_server())" 2>/dev/null) ||
    fail "Can't find llama-server: run ./setup.sh first."
found=$(readlink -f "$found")
from=$(dirname "$found")
to="build/llama-server"
rm -rf "$to"
mkdir -p "$to"
cp "$found" "$to/llama-server"
# Its libraries, and only those (llama.cpp's other tools come with their own, like libllama-cli-impl.so):
#   - the CPU backends (libggml-cpu-haswell.so...): llama.cpp picks the best one for the player's CPU at runtime,
#     from its own folder. Not the GPU (Vulkan) one: the game runs the model on the CPU (-ngl 0), and players' GPU
#     drivers vary.
#   - what the server and those backends link to, by the name they ask for (libllama.so.0, not also libllama.so
#     and libllama.so.0.7.0, the same file under more names): found with ldd, which also finds them where a
#     Homebrew install keeps them (../lib).
#   - libgomp (GCC's OpenMP, which the backends use): on nearly every Linux, but not all, so it comes along.
# (cp -L: copy the file a symlink points to, under the symlink's name.)
for lib in "$from"/libggml-cpu-*.so; do
    [ -e "$lib" ] && cp -L "$lib" "$to/"
done
LD_LIBRARY_PATH="$from" ldd "$found" "$to"/libggml-cpu-*.so 2>/dev/null |
    awk '$2 == "=>" && $3 ~ /^\// && $1 ~ /^lib(llama|ggml|mtmd|gomp)/ {print $1, $3}' | sort -u |
    while read -r name path; do
        [ -e "$to/$name" ] || cp -L "$path" "$to/$name"
    done
for license in "$from"/LICENSE*; do
    [ -e "$license" ] && cp "$license" "$to/"
done
missing=$(LD_LIBRARY_PATH="$to" ldd "$to/llama-server" | grep "not found")
[ -z "$missing" ] || fail "llama-server needs libraries that weren't found:
$missing"
chmod +x "$to/llama-server"
note "$(ls "$to" | wc -l) files from $from"

step "3/6  Building (a minute or two)"
"$PYTHON" -m PyInstaller DesktopPet.spec --noconfirm --clean --distpath dist --workpath build/pyinstaller --log-level WARN ||
    fail "The build failed (see above)."
game="dist/DesktopPet"
chmod +x "$game/DesktopPet" "$game/_internal/server/llama-server"

step "4/6  Checking the build"
if ! version=$(LD_LIBRARY_PATH="$game/_internal/server" "$game/_internal/server/llama-server" --version 2>&1); then
    printf '%s\n' "$version"
    fail "The built llama-server doesn't start (see above)."
fi
note "llama-server: $(printf '%s\n' "$version" | grep -m1 -i version)"
# Qt's X11 plugin (the one the game uses, see main.py) needs a few system libraries that aren't part of Qt, like
# libxcb-cursor0. Missing on this machine means the build left them out, and players without them see nothing.
xcb=$(find "$game/_internal" -name "libqxcb.so" | head -1)
if [ -n "$xcb" ]; then
    qt_missing=$(LD_LIBRARY_PATH="$game/_internal:$game/_internal/PySide6/Qt/lib" ldd "$xcb" | grep "not found")
    if [ -n "$qt_missing" ]; then
        printf '%s\n' "$qt_missing"
        fail "Qt's X11 plugin is missing the libraries above. On Ubuntu / Debian: sudo apt install libxcb-cursor0
(and any other xcb library listed), then run ./build.sh again."
    fi
    note "Qt's X11 plugin has everything it needs"
fi
note "made on $(ldd --version | head -1 | sed 's/^ldd //'): players need this glibc or newer"

step "5/6  Licenses"
"$PYTHON" build_notices.py "$game" || fail "Couldn't write the licenses."

step "6/6  The tar.gz"
archive="dist/DesktopPet-linux.tar.gz"
rm -f "$archive"
tar -czf "$archive" -C dist DesktopPet || fail "Couldn't make the tar.gz."
printf '\n\033[32mDone: %s/DesktopPet (%s), and %s (%s)\033[0m\n' "$game" "$(du -sh "$game" | cut -f1)" \
    "$archive" "$(du -h "$archive" | cut -f1)"
