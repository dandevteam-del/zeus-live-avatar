#!/usr/bin/env bash
set -x
export DISPLAY=:1
PROJ=/workspace/ZeusAvatar/ZeusAvatar.uproject
# Enable MetaHumanCharacter (the in-editor MetaHuman Creator) + the full stack.
cat > "$PROJ" <<'JSON'
{
  "FileVersion": 3,
  "EngineAssociation": "5.6",
  "Category": "",
  "Description": "Zeus Avatar — MetaHuman created in-editor (MetaHumanCharacter)",
  "Plugins": [
    { "Name": "LiveLink", "Enabled": true },
    { "Name": "PixelStreaming", "Enabled": true },
    { "Name": "MetaHuman", "Enabled": true, "SupportedTargetPlatforms": ["Win64","Linux"] },
    { "Name": "MetaHumanCharacter", "Enabled": true, "SupportedTargetPlatforms": ["Win64","Linux"] },
    { "Name": "MetaHumanCoreTech", "Enabled": true, "SupportedTargetPlatforms": ["Win64","Linux"] },
    { "Name": "MetaHumanCalibrationProcessing", "Enabled": true, "SupportedTargetPlatforms": ["Win64","Linux"] },
    { "Name": "MetaHumanLiveLink", "Enabled": true },
    { "Name": "RigLogic", "Enabled": true },
    { "Name": "ControlRig", "Enabled": true }
  ]
}
JSON
echo "=== new uproject ==="; cat "$PROJ"
# Restart the editor so it loads MetaHumanCharacter (cloud_init loop relaunches in ~8s).
pkill -f "UnrealEditor.*ZeusAvatar" 2>/dev/null
echo "killed editor -> relaunch loop will restart with MetaHumanCharacter enabled"
