// Zeus Live Avatar — Unreal Engine Animation Receiver Build Configuration
// Opulent Bots LLC — All rights reserved

using UnrealBuildTool;

public class ZeusAnimReceiver : ModuleRules
{
    public ZeusAnimReceiver(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[] {
            "Core",
            "CoreUObject",
            "Engine",
            "WebSockets",
            "Json",
            "JsonUtilities",
            "LiveLinkInterface",
            "LiveLinkComponents"
        });

        PrivateDependencyModuleNames.AddRange(new string[] {
            "LiveLink",
            "LiveLinkAnimationCore"
        });
    }
}
