#!/bin/sh
# uninstall.sh, in the game's folder (build.sh puts it there): removes Desktop Pet from this computer.
#   1. the game: this folder
#   2. everything it saved: ~/.local/share/desktop-pet (or $XDG_DATA_HOME/desktop-pet): the characters' saves and
#      memories, logs, the prompt cache, and the AI model it downloaded on its first launch, several GB. See config.py.
# Run it from a terminal:  ./uninstall.sh
# It asks first, stops the game if it's running, and only ever deletes a folder that has the game in it, so a copy
# run from somewhere else can't delete the wrong folder.
GAME=$(cd "$(dirname "$0")" && pwd -P)
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/desktop-pet"

if [ ! -f "$GAME/DesktopPet" ] || [ ! -d "$GAME/_internal" ]; then
    echo "This uninstaller only works from inside the Desktop Pet folder (next to DesktopPet)."
    echo "Nothing was removed."
    exit 1
fi

echo
echo "  This removes Desktop Pet from your computer:"
echo
echo "    - the game:      $GAME"
if [ -d "$DATA" ]; then
    echo "    - what it saved: $DATA"
    echo "      (the characters' memories of you, your trust with them, and the AI model it downloaded)"
fi
echo
echo "  This can't be undone."
echo
printf "  Type y and press Enter to uninstall (just Enter cancels): "
read -r answer
case "$answer" in
    y|Y) ;;
    *) echo; echo "  Nothing was removed."; exit 0 ;;
esac

echo
echo "  Closing Desktop Pet if it's running..."
# (only programs from this folder: the game and its llama-server, not another llama-server of yours)
for proc in /proc/[0-9]*; do
    case "$(readlink "$proc/exe" 2>/dev/null)" in
        "$GAME"/*) kill "${proc#/proc/}" 2>/dev/null ;;
    esac
done
sleep 1

cd / || exit 1
if [ -d "$DATA" ]; then
    echo "  Removing what it saved..."
    if ! rm -rf "$DATA"; then
        echo "  Couldn't remove $DATA. Close Desktop Pet if it's still open, then run this again."
        exit 1
    fi
fi
echo "  Removing the game..."
if ! rm -rf "$GAME"; then
    echo "  Some of the game's files couldn't be removed: $GAME"
    exit 1
fi
echo
echo "  Desktop Pet has been removed. Thanks for playing!"
echo
