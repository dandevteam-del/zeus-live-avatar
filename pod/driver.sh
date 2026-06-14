#!/usr/bin/env bash
# READ-ONLY diagnostic (no xdotool / no clicks) — safe while Daniel has the editor.
set -x
EP=/home/ue4/UnrealEngine/Engine/Plugins/MetaHuman/MetaHumanCharacter
echo "=== MetaHumanCharacter content (asset types / factories hints) ==="
find "$EP" -maxdepth 3 -iname "*.uasset" 2>/dev/null | head
echo "=== strings in editor .so: how the create entry is named ==="
strings "$EP/Binaries/Linux/libUnrealEditor-MetaHumanCharacter.so" 2>/dev/null | grep -iE "MetaHuman Character|Create MetaHuman|New MetaHuman|MetaHumanCharacterFactory|Add a new|MetaHuman$" | sort -u | head -30
echo "=== editor module strings for menu/toolbar entries ==="
strings "$EP/Binaries/Linux/libUnrealEditor-MetaHumanCharacterPaletteEditor.so" 2>/dev/null | grep -iE "MetaHuman Character|Create|New Character" | sort -u | head -20
echo "=== did MetaHumanCharacter editor module load? (from ue.log) ==="
grep -iE "MetaHumanCharacter" /workspace/ue.log | grep -iE "module|mount|load|fail|error" | tail -10
echo "diag done"
