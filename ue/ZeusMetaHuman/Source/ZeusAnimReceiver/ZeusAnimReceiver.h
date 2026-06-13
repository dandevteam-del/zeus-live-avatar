/**
 * Zeus Animation Receiver
 *
 * Connects to the a2f-bridge WebSocket and pushes facial blendshape data
 * into Unreal Engine's LiveLink system, which drives the MetaHuman facial rig.
 *
 * The a2f-bridge sends JSON frames containing ARKit-compatible blendshape
 * weights (52 blendshapes) plus optional head rotation data. This component
 * parses those frames and creates LiveLink animation frames that the
 * MetaHuman's Animation Blueprint consumes in real time.
 *
 * Usage from Blueprint:
 *   1. Create a UZeusAnimationSource variable
 *   2. Call Connect("ws://a2f-bridge:8003/ws_anim") in BeginPlay
 *   3. Call Disconnect() in EndPlay
 *   4. Configure the MetaHuman's AnimBP to receive LiveLink from subject "ZeusAvatar"
 *
 * Opulent Bots LLC — All rights reserved
 */

#pragma once

#include "CoreMinimal.h"
#include "IWebSocket.h"
#include "LiveLinkTypes.h"
#include "Roles/LiveLinkAnimationRole.h"
#include "ZeusAnimReceiver.generated.h"

/**
 * Zeus Animation Source — WebSocket receiver for real-time facial animation.
 *
 * Receives blendshape weights from the a2f-bridge service over WebSocket
 * and pushes them into UE's LiveLink system as animation frame data.
 */
UCLASS(BlueprintType, Blueprintable, Category = "Zeus")
class ZEUSANIMRECEIVER_API UZeusAnimationSource : public UObject
{
    GENERATED_BODY()

public:
    UZeusAnimationSource();

    /**
     * Connect to the a2f-bridge WebSocket.
     *
     * @param WebSocketURL  Full WebSocket URL, e.g. "ws://localhost:8003/ws_anim"
     */
    UFUNCTION(BlueprintCallable, Category = "Zeus")
    void Connect(const FString& WebSocketURL);

    /** Disconnect from the WebSocket and stop receiving data. */
    UFUNCTION(BlueprintCallable, Category = "Zeus")
    void Disconnect();

    /** Returns true if the WebSocket is currently connected. */
    UFUNCTION(BlueprintCallable, Category = "Zeus")
    bool IsConnected() const;

    /** True when actively receiving animation frames. */
    UPROPERTY(BlueprintReadOnly, Category = "Zeus")
    bool bIsReceiving;

    /** The LiveLink subject name used for this animation source. Default: "ZeusAvatar". */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Zeus")
    FString SubjectName;

    /** Number of frames received since last connect. */
    UPROPERTY(BlueprintReadOnly, Category = "Zeus")
    int32 FramesReceived;

    /** Whether to attempt auto-reconnect on disconnection. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Zeus")
    bool bAutoReconnect;

    /** Delay in seconds between reconnection attempts. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Zeus")
    float ReconnectDelay;

private:
    /** WebSocket connection handle. */
    TSharedPtr<IWebSocket> WebSocket;

    /** WebSocket URL for reconnection. */
    FString CachedURL;

    /** Connection state. */
    bool bConnected;

    /** Timer handle for auto-reconnect. */
    FTimerHandle ReconnectTimerHandle;

    /** Number of consecutive reconnect attempts. */
    int32 ReconnectAttempts;

    /** Maximum reconnect delay (exponential backoff cap). */
    static constexpr float MaxReconnectDelay = 30.0f;

    // ─── WebSocket Callbacks ────────────────────────────────────────

    void OnConnected();
    void OnConnectionError(const FString& Error);
    void OnClosed(int32 StatusCode, const FString& Reason, bool bWasClean);
    void OnMessage(const FString& Message);

    // ─── LiveLink ────────────────────────────────────────────────────

    /**
     * Push a set of blendshape weights and head rotation into LiveLink.
     */
    void PushToLiveLink(
        const TMap<FName, float>& Blendshapes,
        const FRotator& HeadRotation
    );

    /**
     * Register the LiveLink subject with the static data (blendshape names).
     * Called once on first successful connection.
     */
    void RegisterLiveLinkSubject();

    /** Whether the LiveLink subject has been registered. */
    bool bSubjectRegistered;

    // ─── Reconnection ────────────────────────────────────────────────

    void ScheduleReconnect();
    void AttemptReconnect();

    // ─── ARKit Blendshape Names ─────────────────────────────────────

    /** The 52 standard ARKit blendshape names used by MetaHuman. */
    static const TArray<FName>& GetARKitBlendshapeNames();
};
