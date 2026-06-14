#!/usr/bin/env bash
# READ-ONLY diagnostic (no clicks) — safe while editor is open.
set -x
ENG=/home/ue4/UnrealEngine
echo "=== GitDependencies / Setup tooling present? ==="
ls -la "$ENG/Setup.sh" "$ENG/Engine/Build/BatchFiles/Linux/GitDependencies.sh" 2>&1 | head
find "$ENG/Engine" -maxdepth 4 -iname "*.gitdeps.xml" 2>/dev/null | head
echo "=== any existing MetaHuman Creator Core Data already in image? ==="
find "$ENG" -maxdepth 6 -iname "*CoreData*" -o -iname "*MetaHumanCreatorCoreData*" 2>/dev/null | grep -i meta | head
echo "=== what core-data path/name does the plugin look for? (strings) ==="
strings "$ENG/Engine/Plugins/MetaHuman/MetaHumanCharacter/Binaries/Linux/libUnrealEditor-MetaHumanCharacter.so" 2>/dev/null | grep -iE "CoreData|Core Data|requires that|/MetaHuman/|MetaHumanCreator" | sort -u | head -30
echo "=== MetaHumanCharacter plugin folder layout (look for empty/expected dirs) ==="
du -sh "$ENG/Engine/Plugins/MetaHuman/MetaHumanCharacter/Content" 2>/dev/null
ls "$ENG/Engine/Plugins/MetaHuman/MetaHumanCharacter/" 2>/dev/null
echo "=== is there a MetaHumanCharacterPalette 'Optional' or content dir expecting data? ==="
find "$ENG/Engine/Plugins/MetaHuman" -maxdepth 2 -type d 2>/dev/null
echo "diag done"
