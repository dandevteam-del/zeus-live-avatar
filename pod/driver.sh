#!/usr/bin/env bash
set -x
ENG=/home/ue4/UnrealEngine
echo "=== MetaHumanCharacter binaries now ==="
ls -la "$ENG/Engine/Plugins/MetaHuman/MetaHumanCharacter/Binaries/Linux/" 2>/dev/null
echo "=== did MetaHumanCharacterEditor.so get built ANYWHERE (engine or project)? ==="
find "$ENG" /workspace -iname "*MetaHumanCharacterEditor*.so" 2>/dev/null | head
echo "=== all NEW .so built in last 30 min under MetaHuman plugins ==="
find "$ENG/Engine/Plugins/MetaHuman" -name "*.so" -mmin -30 2>/dev/null
echo "=== build.log: was MetaHumanCharacterEditor mentioned as compiled/skipped? ==="
grep -iE "MetaHumanCharacterEditor|MetaHumanCharacter " "$ENG/../"*build.log /workspace/web/build.log 2>/dev/null | head
grep -icE "MetaHumanCharacterEditor" /workspace/web/build.log 2>/dev/null
echo "=== what targets/modules did UBT actually build? (module link lines) ==="
grep -iE "Link .*\.so" /workspace/web/build.log 2>/dev/null | head -40
echo "diag done"
