#!/usr/bin/env bash
set -x
EP=/home/ue4/UnrealEngine/Engine/Plugins/MetaHuman/MetaHumanCharacter
echo "=== full .uplugin (module platform restrictions) ==="
cat "$EP/MetaHumanCharacter.uplugin"
echo "=== MetaHumanCharacterEditor.Build.cs (platform/condition guards) ==="
sed -n '1,80p' "$EP/Source/MetaHumanCharacterEditor/MetaHumanCharacterEditor.Build.cs" 2>/dev/null
echo "diag done"
