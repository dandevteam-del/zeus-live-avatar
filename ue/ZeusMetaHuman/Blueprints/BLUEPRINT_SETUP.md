# Zeus MetaHuman -- Blueprint Setup Guide

Step-by-step instructions for setting up the Zeus animation receiver and MetaHuman in Unreal Engine Blueprints. This guide assumes you have already completed the steps in `SETUP.md` (project creation, MetaHuman import, plugin configuration, C++ build).

---

## 1. Create a LiveLink Preset

The LiveLink preset tells UE to expect animation data from a source named "ZeusAvatar".

### Steps

1. Open **Window > Virtual Production > Live Link**
2. The Live Link panel will open
3. Click **Add Source > Message Bus Source** (or it may already appear if the C++ module registered it)
4. Verify that "ZeusAvatar" appears as a subject
5. To create a reusable preset:
   - Click **Presets > Save Preset**
   - Name it `ZeusLiveLinkPreset`
   - Location: Save in your project's Content directory

### Auto-Apply Preset on Level Load

1. Open **Project Settings > Live Link**
2. Set **Default Live Link Preset** to `ZeusLiveLinkPreset`
3. This ensures the LiveLink connection is active every time the project loads

---

## 2. Set Up MetaHuman Animation Blueprint

Configure the MetaHuman's face Animation Blueprint to receive LiveLink data.

### Open the Face AnimBP

1. In Content Browser, navigate to:
   ```
   Content/MetaHumans/<YourCharacter>/Face/Face_AnimBP
   ```
2. Double-click to open the Animation Blueprint editor

### Add LiveLink Pose Node

1. In the **AnimGraph** tab, right-click on the graph
2. Search for **Live Link Pose** and add the node
3. Configure the node:
   - **Subject Name**: `ZeusAvatar`
   - **Retarget Asset**: (leave as None for ARKit-compatible data)
4. Connect the **Output Pose** of the Live Link Pose node to the existing facial animation chain
5. If the MetaHuman has existing facial animation logic, insert the Live Link Pose as a blend layer (see section 5 below)

### Compile and Save

1. Click **Compile** in the toolbar
2. Click **Save**
3. Test: when the a2f-bridge is running and sending data, you should see the MetaHuman's face move

---

## 3. Map ARKit Blendshapes to MetaHuman

MetaHuman natively supports ARKit blendshape names. The Zeus animation receiver sends the standard 52 ARKit blendshapes, which map directly to MetaHuman's facial controls.

### Verify Mapping

1. In the Live Link panel, with "ZeusAvatar" selected, you should see all 52 blendshapes listed:
   - `jawOpen`, `mouthSmileLeft`, `mouthSmileRight`, `eyeBlinkLeft`, `eyeBlinkRight`, etc.
2. Enable the **Live Link Curve Debug UI** (Window > Virtual Production > Live Link Curve Debug)
3. This shows real-time blendshape values -- useful for debugging

### Manual Curve Remapping (If Needed)

If blendshape names do not match exactly:

1. Create a **Live Link Remap Asset**:
   - Content Browser > Right-click > Animation > Live Link Remap Asset
2. Map source curves (from a2f-bridge) to target curves (MetaHuman)
3. Set this asset in the Live Link Pose node's **Retarget Asset** property

In most cases, this is not needed because both a2f-bridge and MetaHuman use standard ARKit naming.

---

## 4. Add Audio Component for TTS Playback

If you want TTS audio to play through Unreal Engine (rather than through a separate virtual audio device):

### Add Audio Component

1. Open your MetaHuman Blueprint (or the Level Blueprint)
2. In the Components panel, click **Add Component > Audio**
3. Name it `TTS_Audio`
4. Configure:
   - **Auto Activate**: false (we will trigger playback from code)
   - **Sound Attenuation**: None (we want full volume, no distance fallback)

### Receive Audio via HTTP or WebSocket

For advanced setups, you can create a Blueprint that:
1. Polls or receives audio data from the TTS service
2. Creates a runtime Sound Wave from the PCM data
3. Plays it through the Audio Component

**However, for most setups, it is simpler to use Option A from SETUP.md**: route TTS audio through a virtual audio device that OBS captures directly. This avoids the complexity of real-time audio streaming into UE.

---

## 5. Add Idle Animation Layer

For natural idle behavior when Zeus is not speaking (subtle breathing, micro-movements, blinking):

### Create Idle Layer

1. In the Face AnimBP's AnimGraph:
2. Add a **Layered Blend per Bone** node between your idle source and the Live Link Pose
3. Configure:
   - **Base Pose**: Connect to an idle animation (breathing, micro head movement)
   - **Blend Pose 0**: Connect to the Live Link Pose output
   - **Blend Weight 0**: 1.0 (LiveLink data overrides idle when active)

### Automatic Blink (Fallback)

If the a2f-bridge does not provide blink data:

1. In the AnimGraph, add a **Modify Curve** node after the LiveLink Pose
2. Create an Animation Curve named `EyeBlinkOverride`
3. Drive `eyeBlinkLeft` and `eyeBlinkRight` with a procedural blink pattern:

```
Blueprint logic (pseudocode):
  - Timer: every 2-6 seconds (random interval)
  - On timer fire:
    - Animate eyeBlinkLeft from 0 -> 1 -> 0 over 0.15 seconds
    - Animate eyeBlinkRight from 0 -> 1 -> 0 over 0.15 seconds
  - Only apply if LiveLink blink values are near zero
    (to avoid conflicting with A2F blink data)
```

### Eye Saccade (Natural Eye Movement)

For subtle random eye movements:

1. Add a **Modify Curve** node
2. Drive `eyeLookInLeft`, `eyeLookOutLeft`, `eyeLookUpLeft`, `eyeLookDownLeft` (and Right counterparts) with small random values:
   - Amplitude: 0.02 to 0.08
   - Frequency: change every 0.5 to 2 seconds
   - Use `FMath::PerlinNoise1D` or a smoothed random for natural feel

---

## 6. Camera Setup Blueprint

Create a Blueprint that manages the camera for a clean "webcam" look.

### Create Camera Blueprint

1. In Content Browser, create a new Blueprint class derived from **Actor**
2. Name it `BP_ZeusCamera`
3. Add components:
   - **CineCamera Component** (as Root)
   - **Spring Arm Component** (optional, for smooth following)

### Configure Camera

1. Set CineCamera properties:
   - Focal Length: 50mm
   - Aperture: f/2.8
   - Focus Method: Manual (set to distance of MetaHuman's face)
2. Position the camera in the level facing the MetaHuman at eye level

### Post-Process Effects (Optional)

For a polished look:
1. Add a **Post Process Component** to the camera Blueprint
2. Settings:
   - Bloom: subtle (Intensity 0.3)
   - Vignette: subtle (0.2)
   - Color Grading: slight warm shift for skin tones
   - Depth of Field: Bokeh method, moderate (f/2.8 to f/4)

---

## 7. Blueprint for Receiving Audio via WebSocket

For advanced setups where you want UE to handle audio directly:

### Overview

```
TTS Service --(WebSocket)--> UE Blueprint --(Audio Component)--> Speaker
```

### Steps

1. Create a new Blueprint class (or add to Level Blueprint)
2. Use the **WebSocket** plugin nodes (if using the UE WebSocket Blueprint library) or call from C++
3. On BeginPlay:
   - Open WebSocket to `ws://tts-service:8002/ws_audio`
   - Register OnMessage callback
4. On each audio message:
   - Decode the PCM/WAV data
   - Create a **USoundWaveProcedural** (runtime-generated sound wave)
   - Queue audio data into the procedural sound wave
   - Play through the Audio Component

**Note**: This is complex and recommended only when tight audio-visual sync is critical. For most use cases, the virtual audio device approach (audio routed outside UE) is simpler and more reliable.

---

## 8. Level Blueprint: Putting It All Together

### BeginPlay Setup

In the Level Blueprint:

```
Event BeginPlay
  |
  +--> Create UZeusAnimationSource (Construct Object from Class)
  |      Store in variable: ZeusAnimSource
  |
  +--> ZeusAnimSource.Connect("ws://a2f-bridge:8003/ws_anim")
  |
  +--> Set View Target with Blend (to BP_ZeusCamera)
```

### EndPlay Cleanup

```
Event EndPlay
  |
  +--> ZeusAnimSource.Disconnect()
```

### Runtime Monitoring

To display connection status in the editor:

```
Event Tick (or Timer)
  |
  +--> Branch: ZeusAnimSource.IsConnected()
  |      True: Print String("A2F Connected - Frames: " + FramesReceived)
  |      False: Print String("A2F Disconnected")
  |
  +--> Branch: ZeusAnimSource.bIsReceiving
         True: (animation is active)
         False: (no frames arriving - check a2f-bridge)
```

---

## Quick Test Checklist

1. Start the Zeus services (docker-compose up)
2. Verify a2f-bridge is running on port 8003
3. Open the UE project and enter Play mode
4. Check the Live Link panel -- "ZeusAvatar" should show as connected
5. Speak into the microphone (or use the operator console to inject text)
6. Verify the MetaHuman's face animates in response to the audio

### Debugging

- **No animation**: Check the Live Link panel. Is "ZeusAvatar" listed? Are curve values updating?
- **Delayed animation**: Check network latency. Use `ws://localhost:8003/ws_anim` for local testing.
- **Wrong blendshapes**: Enable the Curve Debug UI and compare expected vs. actual values.
- **Jittery animation**: The a2f-bridge should be sending at 60fps. Check `A2F_FPS` in `.env`.

---

## File Reference

| File | Purpose |
|------|---------|
| `Source/ZeusAnimReceiver/ZeusAnimReceiver.Build.cs` | UE build module configuration |
| `Source/ZeusAnimReceiver/ZeusAnimReceiver.h` | C++ header: WebSocket + LiveLink types |
| `Source/ZeusAnimReceiver/ZeusAnimReceiver.cpp` | C++ implementation: parsing + LiveLink push |
| `Blueprints/BLUEPRINT_SETUP.md` | This file |
| `SETUP.md` | Main UE setup guide |
