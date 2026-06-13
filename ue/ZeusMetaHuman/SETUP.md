# Zeus MetaHuman -- Unreal Engine 5 Setup Guide

Complete step-by-step guide for setting up the Zeus Live Avatar MetaHuman in Unreal Engine 5, connecting it to the Zeus pipeline for real-time facial animation driven by AI-generated speech.

---

## Prerequisites

- **Unreal Engine 5.4+** installed via Epic Games Launcher
- **MetaHuman Plugin** enabled (included with UE5)
- **A MetaHuman character** created at https://metahuman.unrealengine.com
- **GPU**: NVIDIA RTX 3060+ (12GB VRAM recommended) or AMD RX 6800+
- **RAM**: 32GB recommended (16GB minimum)
- **Disk**: 50GB+ free (UE projects + MetaHuman assets are large)

---

## Step 1: Create New UE5 Project

1. Open the Epic Games Launcher
2. Launch Unreal Engine 5.4+
3. Select **Games > Blank** template
4. Choose **Blueprint** project type (C++ is optional but recommended for the animation receiver plugin)
5. Project settings:
   - Project Name: `ZeusMetaHuman`
   - Location: Choose your preferred directory
   - Starter Content: **No** (keep the project lean)
6. Click **Create**

### Enable Required Plugins

After the project opens:

1. Go to **Edit > Plugins**
2. Search for and enable each of the following:
   - **MetaHuman** (should be enabled by default in UE5.4+)
   - **Live Link** -- real-time data streaming for animation
   - **Quixel Bridge** -- for importing MetaHuman characters
   - **Live Link Curve Debug UI** -- helpful for debugging blendshape values
   - **NDI IO Plugin** (optional) -- for NDI video output to OBS
   - **Web Sockets** -- for the animation receiver component
3. Restart the editor when prompted

---

## Step 2: Import MetaHuman

1. Open **Quixel Bridge** from the Content Drawer (or Window > Quixel Bridge)
2. Sign in with your Epic Games account
3. Navigate to **My MetaHumans** section
4. Select your Zeus character and click **Download** then **Add to Project**
5. Wait for the import to complete (MetaHumans are large -- several GB of assets)
6. Your MetaHuman will appear in the Content Browser under `Content/MetaHumans/YourCharacterName/`

### Place MetaHuman in Level

1. Find your MetaHuman Blueprint in the Content Browser:
   `Content/MetaHumans/YourCharacterName/BP_YourCharacterName`
2. Drag it into the level viewport
3. Position it at the origin (0, 0, 0) or wherever you want the camera to frame it
4. The MetaHuman should appear in the viewport with its default pose

---

## Step 3: Set Up Animation Blueprint

The MetaHuman comes with a pre-built Animation Blueprint. We need to modify it to accept LiveLink data for facial animation.

### Locate the Animation Blueprint

1. In Content Browser, navigate to:
   `Content/MetaHumans/YourCharacterName/Face/Face_AnimBP`
2. Double-click to open it

### Add LiveLink Pose Node

1. In the AnimGraph, find the existing facial animation chain
2. Add a **Live Link Pose** node:
   - Right-click in the AnimGraph > Add Node > Live Link Pose
3. Configure the Live Link Pose node:
   - **Subject Name**: `ZeusAvatar` (this must match the LiveLink subject name in our C++ receiver)
   - **Retarget Asset**: Leave as None for ARKit-compatible blendshapes
4. Connect the Live Link Pose node's output to the facial mesh component
5. Compile and Save the Animation Blueprint

### Add Idle Animation Layer

For natural idle behavior (breathing, subtle head movement, eye saccades), add an animation layer:

1. In the AnimGraph, add a **Layered Blend per Bone** node
2. Configure layers:
   - Base Layer: Your idle/breathing animation (or use a simple Additive Pose)
   - Overlay Layer: LiveLink Pose data (facial animation from Zeus)
3. Set blend weight for the overlay to 1.0
4. For the base layer, create a simple looping idle animation or use the MetaHuman's default idle

### Configure Blink and Saccade (Eye Movement)

If LiveLink data does not include eye blink/saccade (our basic A2F bridge may not):

1. Add a **Modify Curve** node in the AnimGraph
2. Drive `EyeBlinkLeft` and `EyeBlinkRight` with a periodic curve (random interval 2-6 seconds)
3. Drive `EyeLookInLeft`, `EyeLookOutLeft`, etc. with subtle random noise for natural eye saccade
4. These will be overridden when LiveLink provides explicit blink/gaze values

---

## Step 4: WebSocket Animation Receiver

The Zeus animation pipeline sends blendshape data over WebSocket from the `a2f-bridge` service. We need a C++ component to receive this data and push it into Unreal's LiveLink system.

### Build the Plugin

Source files are in this repository under `ue/ZeusMetaHuman/Source/ZeusAnimReceiver/`:

1. Copy the `Source/ZeusAnimReceiver/` directory into your UE project's `Source/` folder
2. Add `"ZeusAnimReceiver"` to your project's `.uproject` file under Modules:
   ```json
   {
       "Modules": [
           {
               "Name": "ZeusMetaHuman",
               "Type": "Runtime",
               "LoadingPhase": "Default"
           },
           {
               "Name": "ZeusAnimReceiver",
               "Type": "Runtime",
               "LoadingPhase": "Default"
           }
       ]
   }
   ```
3. Right-click your `.uproject` file > **Generate Visual Studio project files** (Windows) or use the terminal:
   ```bash
   # macOS/Linux
   /path/to/UnrealBuildTool -projectfiles -project="/path/to/ZeusMetaHuman.uproject" -game -engine
   ```
4. Build the project (Build > Build Solution in Visual Studio, or Ctrl+Shift+B)

### Blueprint Usage

After building:
1. In the level Blueprint or your MetaHuman Blueprint:
   - Create a variable of type `UZeusAnimationSource`
   - In Begin Play:
     - Construct a `UZeusAnimationSource` object
     - Call `Connect("ws://a2f-bridge:8003/ws_anim")` (or `ws://localhost:8003/ws_anim` for local dev)
   - In End Play:
     - Call `Disconnect()`

See `Blueprints/BLUEPRINT_SETUP.md` for detailed visual instructions.

---

## Step 5: Audio Playback Setup

Zeus TTS audio needs to play through Unreal Engine so OBS can capture it along with the visual output.

### Option A: System Audio Routing (Simpler)

Route the TTS service audio output to a virtual audio device that OBS captures directly. This bypasses UE audio entirely.

1. TTS service outputs audio to the virtual audio device (see `obs/SETUP.md`)
2. OBS captures the virtual audio device
3. No UE audio configuration needed

### Option B: UE Audio Component (More Control)

For tighter lip-sync or if you want UE to handle audio:

1. Add an **Audio Component** to your MetaHuman Blueprint
2. Create a Blueprint that:
   - Receives audio data via WebSocket (from tts-service)
   - Decodes PCM/WAV audio
   - Plays it through the Audio Component
3. This gives you control over spatialization, volume, etc. in-engine

For most use cases, **Option A is recommended** for simplicity.

---

## Step 6: Camera Setup

Set up a camera that frames the MetaHuman like a webcam for natural video call appearance.

### Create Camera

1. In the level, add a **CineCamera Actor** (Place Actors > Cinematic > CineCamera)
2. Position the camera:
   - Distance from MetaHuman face: approximately 80-120cm
   - Height: eye level of the MetaHuman
   - Angle: straight on (0 degrees) or very slight angle (5-10 degrees)
3. Camera settings:
   - Focal Length: 35-50mm (50mm mimics a webcam focal length)
   - Aperture: f/2.8 to f/4 (moderate depth of field)
   - Focus: Auto-focus on the MetaHuman's face, or manual focus set to the face distance

### Set as Active Camera

1. In the Level Blueprint:
   - On Begin Play, use **Set View Target with Blend** to switch to your camera
   - Or mark the camera as **Auto Activate** in its Details panel

### Viewport Framing

For a natural "webcam" look:
- Frame from roughly mid-chest to above the head
- Center the face in the frame
- Leave a small amount of space above the head
- This mimics how a real person appears on a video call

---

## Step 7: Lighting Setup

Professional-looking 3-point lighting for the MetaHuman:

### Key Light
1. Add a **Rect Light** (or Directional Light)
2. Position: 45 degrees to the left, slightly above eye level
3. Intensity: 5-10 cd/m^2 (adjust to taste)
4. Color temperature: 5500K (daylight) or 4000K (warm office)
5. Soft shadows: enable

### Fill Light
1. Add a second **Rect Light**
2. Position: 45 degrees to the right, at eye level
3. Intensity: 2-4 cd/m^2 (about half of key light)
4. Softer/larger than key light

### Rim/Back Light
1. Add a third light behind and above the MetaHuman
2. Position: behind, 45 degrees above
3. Intensity: 3-5 cd/m^2
4. Creates a subtle edge highlight separating the character from the background

### Background
- Use a simple solid-color background (dark blue, dark gray, or neutral office)
- Or use a virtual environment (office, conference room)
- Or use a **green screen** background in UE for chroma key removal in OBS

---

## Step 8: NDI Output Configuration (Optional)

NDI provides lower-latency video output from UE to OBS compared to window capture.

### Enable NDI Plugin
1. Ensure the **NDI IO Plugin** is enabled (Edit > Plugins)
2. In the level, add an **NDI Broadcast Actor** (search in Place Actors)
3. Configure:
   - Source Name: "Zeus MetaHuman"
   - Resolution: 1920x1080 (or match your OBS canvas)
   - Frame Rate: 30 fps

### Capture from OBS
1. In OBS, install the NDI plugin if not already installed
2. Add an NDI Source
3. Select "Zeus MetaHuman" from the NDI source list
4. NDI streams over the local network, so both apps must be on the same machine or network

---

## Step 9: Window Capture Fallback

If NDI is not available or not desired:

1. In UE, go to **Edit > Project Settings > Engine > General Settings**
2. Set **Default Window Mode** to **Windowed**
3. Set resolution to 1920x1080
4. Position the UE window where OBS can capture it
5. In OBS, add a **Window Capture** source pointing to the Unreal Editor window

### Fullscreen Viewport Mode

For a clean capture without the UE editor UI:

1. In the editor, press **Shift+F11** to enter immersive mode (hides editor chrome)
2. Or use **Play in Standalone Window** (Play > Standalone Game) for a clean game window
3. Capture this window in OBS

---

## Step 10: Performance Tuning

### Resolution and FPS

For video calls, you typically do not need 4K or 60fps:

1. Project Settings > Engine > General Settings:
   - Resolution: 1920x1080 (or 1280x720 for lower GPU usage)
   - Frame Rate: 30fps is sufficient for video calls (set via `t.MaxFPS 30` in console)
2. Console commands (press tilde `~` in editor):
   ```
   t.MaxFPS 30
   r.ScreenPercentage 100
   ```

### Quality Settings

Reduce quality to maintain stable frame rate:

1. **Scalability Settings** (Edit > Project Settings > Engine > Scalability):
   - Anti-Aliasing: Medium or High
   - Shadow Quality: Medium
   - Post Process Quality: Medium
   - Effects Quality: Medium
2. **Disable unnecessary features**:
   - Volumetric fog (if not needed)
   - Ray tracing (unless you have a high-end GPU)
   - Screen space reflections (unless visible in camera)

### GPU Monitoring

Monitor GPU usage to ensure stable performance:
```
stat fps
stat gpu
stat unit
```

Target: stable 30fps with GPU usage under 80%.

---

## Step 11: Green Screen Background Option

If you want OBS to remove the background via chroma key:

1. In UE, create a simple green plane behind the MetaHuman
2. Material: Unlit, pure green color (#00FF00)
3. Make sure the green plane fully covers the camera view behind the character
4. In OBS, enable the **Chroma Key** filter on the Zeus window capture source
5. Configure: Key Color = Green, Similarity = 400, Smoothness = 80

This allows compositing the avatar over any background in OBS (custom backdrop, transparent overlay, etc.).

---

## Audio2Face-3D Integration Options

### Option A: Open-Source A2F Bridge (Default)

The `a2f-bridge` service provides audio-to-blendshape conversion using spectral analysis. It produces ARKit-compatible blendshape weights that drive the MetaHuman facial rig via the WebSocket animation receiver.

- Runs as a Docker container alongside other Zeus services
- No GPU required for inference (CPU-based spectral analysis)
- Quality is acceptable for most use cases
- Zero additional licensing requirements

### Option B: NVIDIA Audio2Face-3D SDK + UE Plugin

NVIDIA provides an Audio2Face-3D SDK with a UE plugin (MIT licensed code, model weights under NVIDIA license). This runs ML-based lip sync directly inside Unreal Engine for higher quality.

To use:
1. Download from: https://developer.nvidia.com/audio2face-3d
2. Install the UE plugin following NVIDIA's instructions
3. The plugin consumes audio directly in UE -- no need for the a2f-bridge service
4. Set `A2F_BACKEND=disabled` in `.env`

License: SDK code is MIT. Model weights are under NVIDIA Open Model License.
See `docs/LICENSES.md` for details.

### Option C: NVIDIA NIM Container

For cloud deployment, NVIDIA offers Audio2Face-3D as a NIM microservice. This provides the highest quality lip sync with GPU-accelerated ML inference.

To use:
1. Obtain NGC credentials from https://ngc.nvidia.com/
2. Set `NGC_API_KEY` in your `.env`
3. Set `A2F_BACKEND=nim` in `.env`
4. Add the NIM container to your docker-compose (see `docker-compose.override.yml`)

---

## Quick Reference

| Setting | Value |
|---------|-------|
| Render resolution | 1920x1080 |
| Target FPS | 30 |
| Camera focal length | 35-50mm |
| LiveLink subject | ZeusAvatar |
| WebSocket URL | ws://a2f-bridge:8003/ws_anim |
| NDI source name | Zeus MetaHuman |
| Key light temp | 5500K |
| Green screen color | #00FF00 |

---

## File Structure

```
ue/ZeusMetaHuman/
  Source/
    ZeusAnimReceiver/
      ZeusAnimReceiver.Build.cs    -- UE build configuration
      ZeusAnimReceiver.h           -- C++ header: WebSocket + LiveLink
      ZeusAnimReceiver.cpp         -- C++ implementation
  Blueprints/
    BLUEPRINT_SETUP.md             -- Step-by-step Blueprint setup guide
  SETUP.md                         -- This file
```
