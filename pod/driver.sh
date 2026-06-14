#!/usr/bin/env bash
# READ-ONLY diagnostic (no clicks).
set -x
EP=/home/ue4/UnrealEngine/Engine/Plugins/MetaHuman/MetaHumanCharacter
SO="$EP/Binaries/Linux/libUnrealEditor-MetaHumanCharacterEditor.so"
echo "=== factory class names in the editor module ==="
strings "$SO" 2>/dev/null | grep -iE "MetaHumanCharacterFactory|FactoryNew|UMetaHumanCharacter[A-Za-z]*Factory" | sort -u | head
echo "=== python-exposed classes (MetaHumanCharacter*) ==="
strings "$EP"/Binaries/Linux/*.so 2>/dev/null | grep -oE "MetaHumanCharacter[A-Za-z]*" | sort | uniq -c | sort -rn | head -20
echo "=== the core-data gate / warning string ==="
strings "$SO" 2>/dev/null | grep -iE "Core Data|requires that|not installed|additional content|disabled" | sort -u | head
echo "=== did MetaHumanCharacterEditor module load this boot? ==="
grep -aiE "MetaHumanCharacterEditor|MetaHumanCharacter.*module|FMetaHumanCharacterEditorModule" /workspace/ue.log | tail -8
echo "=== any 'Core Data' warning emitted in ue.log? ==="
grep -aiE "core data|MetaHumanCharacter.*(warn|requires|missing)" /workspace/ue.log | tail -8
echo "diag done"
