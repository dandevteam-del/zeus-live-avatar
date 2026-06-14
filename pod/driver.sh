#!/usr/bin/env bash
# READ-ONLY: is the UE build toolchain present so we can compile the missing module?
set -x
ENG=/home/ue4/UnrealEngine
echo "=== Build.sh / UBT present? ==="
ls -la "$ENG/Engine/Build/BatchFiles/Linux/Build.sh" 2>&1 | head
ls -la "$ENG/Engine/Binaries/DotNET/UnrealBuildTool/"*.dll 2>&1 | head -3
echo "=== bundled clang toolchain present? ==="
ls -d "$ENG/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/"*/ 2>&1 | head
which clang clang++ 2>&1 | head
echo "=== dotnet present (UBT runtime)? ==="
ls "$ENG/Engine/Binaries/ThirdParty/DotNet/"*/linux* -d 2>&1 | head
"$ENG/Engine/Build/BatchFiles/Linux/RunUBT.sh" -Help >/tmp/ubt.txt 2>&1; head -3 /tmp/ubt.txt
echo "=== free disk for compile intermediates ==="
df -h /workspace / 2>/dev/null | head
echo "diag done"
