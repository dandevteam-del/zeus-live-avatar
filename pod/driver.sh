#!/usr/bin/env bash
set -x
export DISPLAY=:1
echo "=== engine root ==="
ENG=$(dirname $(dirname $(dirname $(find / -maxdepth 7 -name UnrealEditor -type f 2>/dev/null | head -1))))
echo "ENG=$ENG"
echo "=== ALL MetaHuman / Fab / Bridge / Quixel plugins shipped in the engine ==="
find "$ENG/.." -maxdepth 6 -iname "*.uplugin" 2>/dev/null | grep -iE "metahuman|fab|bridge|quixel|riglogic" | sort
echo "=== anything MetaHuman anywhere under engine plugins ==="
find / -maxdepth 8 -iname "*metahuman*" -type d 2>/dev/null | head -20
echo "=== our project's enabled plugins ==="
cat /workspace/ZeusAvatar/ZeusAvatar.uproject 2>/dev/null
echo "diag done"
