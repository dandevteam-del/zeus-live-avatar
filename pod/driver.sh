#!/usr/bin/env bash
# READ-ONLY diagnostic (no clicks).
set -x
EP=/home/ue4/UnrealEngine/Engine/Plugins/MetaHuman/MetaHumanCharacter
echo "=== ALL .so binaries actually present for MetaHumanCharacter ==="
ls -1 "$EP/Binaries/Linux/" 2>/dev/null
echo "=== modules the plugin EXPECTS (from .modules manifest) ==="
cat "$EP/Binaries/Linux/UnrealEditor.modules" 2>/dev/null
echo "=== is MetaHumanCharacterEditor.so present? ==="
ls -la "$EP/Binaries/Linux/"*MetaHumanCharacterEditor*.so 2>&1 | head
echo "=== source for the missing module present (could compile)? ==="
ls "$EP/Source/" 2>/dev/null
echo "=== did the editor log a 'missing module / compile' for MetaHumanCharacter this boot? ==="
grep -aiE "MetaHumanCharacterEditor|MetaHumanDefaultEditorPipeline|MetaHumanCharacterMigrationEditor|could not be loaded|missing modules|Incompatible" /workspace/ue.log | tail -12
echo "diag done"
