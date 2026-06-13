#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# [ON POD] Bootstrap the ZeusMetaHuman UE5 project from the kit.
#
# Generates:
#   /workspace/ZeusMetaHuman/ZeusMetaHuman.uproject   (5.4, both modules, plugins)
#   …/Source/ZeusMetaHuman/*                          (minimal game module)
#   …/Source/ZeusAnimReceiver/*                       (copied from the kit plugin)
#   …/Config/DefaultEngine.ini                        (LiveLink + Pixel Streaming)
#
# Expects the kit synced to the pod (rsync zeus-live-avatar → /workspace/kit).
# After this, the MetaHuman import + AnimBP wiring is the manual GUI step
# (INTERACTIVE_STEPS.md), then 03_package_pixelstreaming.sh.
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail
KIT="${KIT:-/workspace/kit}"                 # synced zeus-live-avatar
PROJ="${PROJ:-/workspace/ZeusMetaHuman}"
NAME=ZeusMetaHuman
mkdir -p "$PROJ/Source/$NAME" "$PROJ/Config" "$PROJ/Content/Maps"

# ─── .uproject ──────────────────────────────────────────────────────────────────
cat > "$PROJ/$NAME.uproject" <<JSON
{
  "FileVersion": 3,
  "EngineAssociation": "5.4",
  "Category": "",
  "Description": "Zeus Live Avatar — real-time MetaHuman driven by a2f-bridge over LiveLink",
  "Modules": [
    { "Name": "$NAME", "Type": "Runtime", "LoadingPhase": "Default" },
    { "Name": "ZeusAnimReceiver", "Type": "Runtime", "LoadingPhase": "Default" }
  ],
  "Plugins": [
    { "Name": "MetaHuman", "Enabled": true },
    { "Name": "LiveLink", "Enabled": true },
    { "Name": "LiveLinkControlRig", "Enabled": true },
    { "Name": "AppleARKitFaceSupport", "Enabled": true },
    { "Name": "PixelStreaming", "Enabled": true },
    { "Name": "WebSocketNetworking", "Enabled": true },
    { "Name": "Bridge", "Enabled": true }
  ]
}
JSON

# ─── Game module (minimal) ───────────────────────────────────────────────────────
cat > "$PROJ/Source/$NAME/$NAME.Build.cs" <<CS
using UnrealBuildTool;
public class $NAME : ModuleRules {
  public $NAME(ReadOnlyTargetRules Target) : base(Target) {
    PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
    PublicDependencyModuleNames.AddRange(new string[]{ "Core","CoreUObject","Engine","InputCore" });
  }
}
CS
cat > "$PROJ/Source/$NAME/${NAME}.cpp" <<CPP
#include "Modules/ModuleManager.h"
IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, $NAME, "$NAME");
CPP
cat > "$PROJ/Source/$NAME/${NAME}.Target.cs" <<CS
using UnrealBuildTool; using System.Collections.Generic;
public class ${NAME}Target : TargetRules {
  public ${NAME}Target(TargetInfo Target) : base(Target) {
    Type = TargetType.Game;
    DefaultBuildSettings = BuildSettingsVersion.V5;
    IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_4;
    ExtraModuleNames.AddRange(new string[]{ "$NAME","ZeusAnimReceiver" });
  }
}
CS
cat > "$PROJ/Source/$NAME/${NAME}Editor.Target.cs" <<CS
using UnrealBuildTool; using System.Collections.Generic;
public class ${NAME}EditorTarget : TargetRules {
  public ${NAME}EditorTarget(TargetInfo Target) : base(Target) {
    Type = TargetType.Editor;
    DefaultBuildSettings = BuildSettingsVersion.V5;
    IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_4;
    ExtraModuleNames.AddRange(new string[]{ "$NAME","ZeusAnimReceiver" });
  }
}
CS

# ─── Copy the ZeusAnimReceiver plugin source from the kit ────────────────────────
SRC="$KIT/ue/$NAME/Source/ZeusAnimReceiver"
[ -d "$SRC" ] || { echo "✗ plugin source not found at $SRC — sync the kit to $KIT first"; exit 1; }
mkdir -p "$PROJ/Source/ZeusAnimReceiver"
cp -r "$SRC/." "$PROJ/Source/ZeusAnimReceiver/"
echo "✓ copied ZeusAnimReceiver plugin source"

# ─── DefaultEngine.ini — Pixel Streaming + LiveLink ──────────────────────────────
cat > "$PROJ/Config/DefaultEngine.ini" <<INI
[/Script/EngineSettings.GameMapsSettings]
GameDefaultMap=/Game/Maps/Avatar.Avatar
EditorStartupMap=/Game/Maps/Avatar.Avatar

[/Script/Engine.RendererSettings]
r.DefaultFeature.AntiAliasing=2
r.SkinCache.CompileShaders=True

[SystemSettings]
; headless render for pixel streaming
r.PixelStreaming.WebRTC.UseLegacyAudioDevice=False

[/Script/PixelStreaming.PixelStreamingSettings]
PixelStreamingEncoderCodec=H264
INI

echo "✓ project bootstrapped at $PROJ"
echo "  NEXT (manual GUI — INTERACTIVE_STEPS.md): create the MetaHuman, import via"
echo "  Quixel Bridge into Content/MetaHumans/Zeus/, drop it in the Avatar map,"
echo "  wire Face_AnimBP LiveLink subject 'ZeusAvatar', save. THEN 03_package…"
