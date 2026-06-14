#!/usr/bin/env bash
# 5.7 check: does MetaHuman Creator allow Linux now? Is the editor module present/compilable?
set -x
echo "=== engine version ==="
cat /home/ue4/UnrealEngine/Engine/Build/Build.version 2>/dev/null | head -8
EP=/home/ue4/UnrealEngine/Engine/Plugins/MetaHuman/MetaHumanCharacter
echo "=== MetaHumanCharacterEditor module: platform allow list in 5.7 ==="
python3 - <<'PY' 2>/dev/null || grep -A6 -iE '"Name": *"MetaHumanCharacterEditor"' "$EP/MetaHumanCharacter.uplugin"
import json
d=json.load(open("/home/ue4/UnrealEngine/Engine/Plugins/MetaHuman/MetaHumanCharacter/MetaHumanCharacter.uplugin"))
for m in d.get("Modules",[]):
    print(m.get("Name"), "| Type:", m.get("Type"), "| PlatformAllowList:", m.get("PlatformAllowList","<none=all>"))
PY
echo "=== precompiled .so present for editor module in 5.7? ==="
ls -la "$EP/Binaries/Linux/" 2>/dev/null
echo "=== ue.log: did MetaHumanCharacterEditor mount this 5.7 boot? ==="
grep -aiE "Mounting.*MetaHumanCharacter|MetaHumanCharacterEditor" /workspace/ue.log | tail -6
echo "diag done"
