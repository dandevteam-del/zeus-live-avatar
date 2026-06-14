#!/usr/bin/env bash
set -x
echo "=== MetaHumanCharacter* module loads in this 5.7 boot (real log, after 07:17) ==="
awk '/07\.1[7-9]|07\.[2-9][0-9]/{on=1} on' /workspace/ue.log | grep -aiE "MetaHumanCharacter|Mounting.*MetaHuman|MetaHuman.*module|ShaderCompiler.*MetaHuman" | grep -aiE "MetaHumanCharacter" | tail -15
echo "=== plugins mounted (any MetaHuman) this boot ==="
awk '/07\.1[7-9]|07\.[2-9][0-9]/{on=1} on' /workspace/ue.log | grep -aiE "Mounting (Engine|Project) plugin (MetaHuman|RigLogic|LiveLink)" | tail -15
echo "=== plugin failures this boot ==="
awk '/07\.1[7-9]|07\.[2-9][0-9]/{on=1} on' /workspace/ue.log | grep -aiE "unable to load|incompatible|was not found|missing modules" | grep -ai meta | tail
echo "diag done"
