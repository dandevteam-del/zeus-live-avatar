/**
 * Zeus Animation Receiver — Implementation
 *
 * Connects to the a2f-bridge WebSocket, parses JSON blendshape frames,
 * and pushes them into Unreal Engine's LiveLink system for MetaHuman
 * facial animation.
 *
 * Expected JSON frame format from a2f-bridge:
 * {
 *   "type": "animation_frame",
 *   "timestamp": 1234567890.123,
 *   "blendshapes": {
 *     "jawOpen": 0.45,
 *     "mouthSmileLeft": 0.12,
 *     "eyeBlinkLeft": 0.0,
 *     ... (52 ARKit blendshapes)
 *   },
 *   "headRotation": {
 *     "pitch": 0.0,
 *     "yaw": 2.5,
 *     "roll": -1.0
 *   }
 * }
 *
 * Opulent Bots LLC — All rights reserved
 */

#include "ZeusAnimReceiver.h"

#include "ILiveLinkClient.h"
#include "LiveLinkProvider.h"
#include "Roles/LiveLinkAnimationRole.h"
#include "WebSocketsModule.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "TimerManager.h"
#include "Engine/World.h"

DEFINE_LOG_CATEGORY_STATIC(LogZeusAnim, Log, All);

// ─── ARKit Blendshape Names ──────────────────────────────────────────────────

const TArray<FName>& UZeusAnimationSource::GetARKitBlendshapeNames()
{
    static TArray<FName> Names = {
        // Brow
        FName("browDownLeft"),     FName("browDownRight"),
        FName("browInnerUp"),
        FName("browOuterUpLeft"),  FName("browOuterUpRight"),
        // Eye
        FName("eyeBlinkLeft"),     FName("eyeBlinkRight"),
        FName("eyeLookDownLeft"),  FName("eyeLookDownRight"),
        FName("eyeLookInLeft"),    FName("eyeLookInRight"),
        FName("eyeLookOutLeft"),   FName("eyeLookOutRight"),
        FName("eyeLookUpLeft"),    FName("eyeLookUpRight"),
        FName("eyeSquintLeft"),    FName("eyeSquintRight"),
        FName("eyeWideLeft"),      FName("eyeWideRight"),
        // Jaw
        FName("jawForward"),       FName("jawLeft"),
        FName("jawOpen"),          FName("jawRight"),
        // Mouth
        FName("mouthClose"),
        FName("mouthDimpleLeft"),  FName("mouthDimpleRight"),
        FName("mouthFrownLeft"),   FName("mouthFrownRight"),
        FName("mouthFunnel"),
        FName("mouthLeft"),        FName("mouthRight"),
        FName("mouthLowerDownLeft"), FName("mouthLowerDownRight"),
        FName("mouthPressLeft"),   FName("mouthPressRight"),
        FName("mouthPucker"),
        FName("mouthRollLower"),   FName("mouthRollUpper"),
        FName("mouthShrugLower"), FName("mouthShrugUpper"),
        FName("mouthSmileLeft"),   FName("mouthSmileRight"),
        FName("mouthStretchLeft"), FName("mouthStretchRight"),
        FName("mouthUpperUpLeft"), FName("mouthUpperUpRight"),
        // Nose
        FName("noseSneerLeft"),    FName("noseSneerRight"),
        // Cheek
        FName("cheekPuff"),
        FName("cheekSquintLeft"),  FName("cheekSquintRight"),
        // Tongue
        FName("tongueOut"),
    };
    return Names;
}

// ─── Constructor ─────────────────────────────────────────────────────────────

UZeusAnimationSource::UZeusAnimationSource()
    : bIsReceiving(false)
    , SubjectName(TEXT("ZeusAvatar"))
    , FramesReceived(0)
    , bAutoReconnect(true)
    , ReconnectDelay(2.0f)
    , bConnected(false)
    , ReconnectAttempts(0)
    , bSubjectRegistered(false)
{
}

// ─── Connect / Disconnect ────────────────────────────────────────────────────

void UZeusAnimationSource::Connect(const FString& WebSocketURL)
{
    if (bConnected && WebSocket.IsValid())
    {
        UE_LOG(LogZeusAnim, Warning, TEXT("Already connected. Call Disconnect() first."));
        return;
    }

    CachedURL = WebSocketURL;
    ReconnectAttempts = 0;

    // Ensure WebSockets module is loaded
    FModuleManager::Get().LoadModuleChecked<FWebSocketsModule>("WebSockets");

    // Create the WebSocket
    TArray<FString> Protocols;
    Protocols.Add(TEXT("ws"));

    WebSocket = FWebSocketsModule::Get().CreateWebSocket(WebSocketURL, Protocols);

    if (!WebSocket.IsValid())
    {
        UE_LOG(LogZeusAnim, Error, TEXT("Failed to create WebSocket for URL: %s"), *WebSocketURL);
        return;
    }

    // Bind callbacks
    WebSocket->OnConnected().AddUObject(this, &UZeusAnimationSource::OnConnected);
    WebSocket->OnConnectionError().AddUObject(this, &UZeusAnimationSource::OnConnectionError);
    WebSocket->OnClosed().AddUObject(this, &UZeusAnimationSource::OnClosed);
    WebSocket->OnMessage().AddUObject(this, &UZeusAnimationSource::OnMessage);

    UE_LOG(LogZeusAnim, Log, TEXT("Connecting to a2f-bridge: %s"), *WebSocketURL);
    WebSocket->Connect();
}

void UZeusAnimationSource::Disconnect()
{
    bAutoReconnect = false;  // Prevent reconnect during explicit disconnect

    if (WebSocket.IsValid())
    {
        WebSocket->Close();
        WebSocket.Reset();
    }

    bConnected = false;
    bIsReceiving = false;

    UE_LOG(LogZeusAnim, Log, TEXT("Disconnected from a2f-bridge"));
}

bool UZeusAnimationSource::IsConnected() const
{
    return bConnected && WebSocket.IsValid() && WebSocket->IsConnected();
}

// ─── WebSocket Callbacks ─────────────────────────────────────────────────────

void UZeusAnimationSource::OnConnected()
{
    bConnected = true;
    bIsReceiving = false;
    ReconnectAttempts = 0;
    FramesReceived = 0;

    UE_LOG(LogZeusAnim, Log, TEXT("Connected to a2f-bridge WebSocket"));

    // Register the LiveLink subject on first connection
    if (!bSubjectRegistered)
    {
        RegisterLiveLinkSubject();
    }
}

void UZeusAnimationSource::OnConnectionError(const FString& Error)
{
    bConnected = false;
    bIsReceiving = false;

    UE_LOG(LogZeusAnim, Warning, TEXT("WebSocket connection error: %s"), *Error);

    if (bAutoReconnect)
    {
        ScheduleReconnect();
    }
}

void UZeusAnimationSource::OnClosed(int32 StatusCode, const FString& Reason, bool bWasClean)
{
    bConnected = false;
    bIsReceiving = false;

    UE_LOG(LogZeusAnim, Log, TEXT("WebSocket closed: code=%d reason=%s clean=%d"),
        StatusCode, *Reason, bWasClean);

    if (bAutoReconnect)
    {
        ScheduleReconnect();
    }
}

void UZeusAnimationSource::OnMessage(const FString& Message)
{
    // Parse the JSON message
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);

    if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
    {
        UE_LOG(LogZeusAnim, Verbose, TEXT("Failed to parse animation frame JSON"));
        return;
    }

    // Check message type
    FString MessageType;
    if (JsonObject->TryGetStringField(TEXT("type"), MessageType))
    {
        if (MessageType != TEXT("animation_frame"))
        {
            // Not an animation frame — could be a control message
            UE_LOG(LogZeusAnim, Verbose, TEXT("Received non-animation message: %s"), *MessageType);
            return;
        }
    }

    // Extract blendshapes
    const TSharedPtr<FJsonObject>* BlendshapesObject = nullptr;
    if (!JsonObject->TryGetObjectField(TEXT("blendshapes"), BlendshapesObject) || !BlendshapesObject)
    {
        UE_LOG(LogZeusAnim, Verbose, TEXT("Animation frame missing 'blendshapes' field"));
        return;
    }

    TMap<FName, float> Blendshapes;
    for (const auto& Pair : (*BlendshapesObject)->Values)
    {
        double Value = 0.0;
        if (Pair.Value->TryGetNumber(Value))
        {
            // Clamp to [0, 1] range
            float ClampedValue = FMath::Clamp(static_cast<float>(Value), 0.0f, 1.0f);
            Blendshapes.Add(FName(*Pair.Key), ClampedValue);
        }
    }

    // Extract head rotation (optional)
    FRotator HeadRotation = FRotator::ZeroRotator;
    const TSharedPtr<FJsonObject>* RotationObject = nullptr;
    if (JsonObject->TryGetObjectField(TEXT("headRotation"), RotationObject) && RotationObject)
    {
        double Pitch = 0.0, Yaw = 0.0, Roll = 0.0;
        (*RotationObject)->TryGetNumberField(TEXT("pitch"), Pitch);
        (*RotationObject)->TryGetNumberField(TEXT("yaw"), Yaw);
        (*RotationObject)->TryGetNumberField(TEXT("roll"), Roll);
        HeadRotation = FRotator(Pitch, Yaw, Roll);
    }

    // Push to LiveLink
    PushToLiveLink(Blendshapes, HeadRotation);

    bIsReceiving = true;
    FramesReceived++;
}

// ─── LiveLink Integration ────────────────────────────────────────────────────

void UZeusAnimationSource::RegisterLiveLinkSubject()
{
    IModularFeatures& ModularFeatures = IModularFeatures::Get();
    if (!ModularFeatures.IsModularFeatureAvailable(ILiveLinkClient::ModularFeatureName))
    {
        UE_LOG(LogZeusAnim, Warning, TEXT("LiveLink client not available"));
        return;
    }

    ILiveLinkClient& LiveLinkClient = ModularFeatures.GetModularFeature<ILiveLinkClient>(
        ILiveLinkClient::ModularFeatureName
    );

    // Create static data with blendshape property names
    FLiveLinkSubjectKey SubjectKey(FLiveLinkSubjectName(*SubjectName), FGuid());

    FLiveLinkStaticDataStruct StaticData(FLiveLinkBaseStaticData::StaticStruct());
    FLiveLinkBaseStaticData* BaseStaticData = StaticData.Cast<FLiveLinkBaseStaticData>();

    if (BaseStaticData)
    {
        const TArray<FName>& Names = GetARKitBlendshapeNames();
        BaseStaticData->PropertyNames.Reserve(Names.Num());
        for (const FName& Name : Names)
        {
            BaseStaticData->PropertyNames.Add(Name);
        }
    }

    // Push the static data to create/update the subject
    LiveLinkClient.PushSubjectStaticData_AnyThread(
        SubjectKey,
        ULiveLinkAnimationRole::StaticClass(),
        MoveTemp(StaticData)
    );

    bSubjectRegistered = true;
    UE_LOG(LogZeusAnim, Log, TEXT("Registered LiveLink subject: %s (%d blendshapes)"),
        *SubjectName, GetARKitBlendshapeNames().Num());
}

void UZeusAnimationSource::PushToLiveLink(
    const TMap<FName, float>& Blendshapes,
    const FRotator& HeadRotation)
{
    IModularFeatures& ModularFeatures = IModularFeatures::Get();
    if (!ModularFeatures.IsModularFeatureAvailable(ILiveLinkClient::ModularFeatureName))
    {
        return;
    }

    ILiveLinkClient& LiveLinkClient = ModularFeatures.GetModularFeature<ILiveLinkClient>(
        ILiveLinkClient::ModularFeatureName
    );

    FLiveLinkSubjectKey SubjectKey(FLiveLinkSubjectName(*SubjectName), FGuid());

    // Create frame data
    FLiveLinkFrameDataStruct FrameData(FLiveLinkBaseFrameData::StaticStruct());
    FLiveLinkBaseFrameData* BaseFrameData = FrameData.Cast<FLiveLinkBaseFrameData>();

    if (!BaseFrameData)
    {
        return;
    }

    // Populate property values in the same order as the static data property names
    const TArray<FName>& Names = GetARKitBlendshapeNames();
    BaseFrameData->PropertyValues.SetNum(Names.Num());

    for (int32 i = 0; i < Names.Num(); i++)
    {
        const float* Value = Blendshapes.Find(Names[i]);
        BaseFrameData->PropertyValues[i] = Value ? *Value : 0.0f;
    }

    // Set world time for synchronization
    BaseFrameData->WorldTime = FLiveLinkWorldTime(FPlatformTime::Seconds());

    // Push the frame data
    LiveLinkClient.PushSubjectFrameData_AnyThread(SubjectKey, MoveTemp(FrameData));
}

// ─── Reconnection ────────────────────────────────────────────────────────────

void UZeusAnimationSource::ScheduleReconnect()
{
    ReconnectAttempts++;

    // Exponential backoff with cap
    float Delay = FMath::Min(
        ReconnectDelay * FMath::Pow(2.0f, static_cast<float>(ReconnectAttempts - 1)),
        MaxReconnectDelay
    );

    UE_LOG(LogZeusAnim, Log, TEXT("Scheduling reconnect in %.1f seconds (attempt %d)"),
        Delay, ReconnectAttempts);

    // Use a world timer if we have a valid world context
    UWorld* World = GetWorld();
    if (World)
    {
        World->GetTimerManager().SetTimer(
            ReconnectTimerHandle,
            this,
            &UZeusAnimationSource::AttemptReconnect,
            Delay,
            false  // Do not loop
        );
    }
    else
    {
        // Fallback: try reconnect on next tick via async
        FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([this](float DeltaTime) -> bool
            {
                AttemptReconnect();
                return false;  // Run once
            }),
            Delay
        );
    }
}

void UZeusAnimationSource::AttemptReconnect()
{
    if (bConnected)
    {
        return;  // Already reconnected
    }

    if (CachedURL.IsEmpty())
    {
        UE_LOG(LogZeusAnim, Warning, TEXT("Cannot reconnect — no cached URL"));
        return;
    }

    UE_LOG(LogZeusAnim, Log, TEXT("Attempting reconnect to: %s"), *CachedURL);

    // Clean up old socket
    if (WebSocket.IsValid())
    {
        WebSocket.Reset();
    }

    // Reconnect
    bool OldAutoReconnect = bAutoReconnect;
    Connect(CachedURL);
    bAutoReconnect = OldAutoReconnect;
}
