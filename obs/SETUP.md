# Zeus Live Avatar -- OBS Setup Guide

Complete setup guide for using OBS Studio to stream the Zeus MetaHuman avatar into Zoom, Google Meet, Microsoft Teams, or any video call application.

## Overview

The pipeline:

```
Unreal Engine (MetaHuman) --> OBS Studio --> Virtual Camera --> Zoom/Meet/Teams
TTS Audio Output ---------> Virtual Audio Device -----------> Zoom Microphone
```

OBS captures the Unreal Engine window (or NDI stream), composites scenes, and outputs through its virtual camera and a virtual audio device. The video call application sees these as a regular webcam and microphone.

---

## Prerequisites

- **OBS Studio 28+** (includes obs-websocket -- no extra plugins needed)
- **Python 3.10+** (for the OBS controller script)
- **Redis** (for event-driven automation; optional for manual control)
- **Unreal Engine 5.4+** running the Zeus MetaHuman project

---

## Step 1: Install OBS Studio

### macOS
```bash
brew install --cask obs
```

### Windows
Download from https://obsproject.com/download

### Linux (Ubuntu/Debian)
```bash
sudo add-apt-repository ppa:obsproject/obs-studio
sudo apt update
sudo apt install obs-studio
```

Verify version is 28+ (obs-websocket is built in):
```bash
obs --version
```

---

## Step 2: Install Virtual Camera

### macOS
OBS 28+ includes a virtual camera by default. No extra installation needed.

### Windows
OBS 28+ includes a virtual camera by default. No extra installation needed.

### Linux
Install v4l2loopback to create a virtual camera device:

```bash
# Install v4l2loopback kernel module
sudo apt install v4l2loopback-dkms v4l2loopback-utils

# Load the module (creates /dev/video10)
sudo modprobe v4l2loopback video_nr=10 card_label="OBS Virtual Camera" exclusive_caps=1

# Verify the device was created
v4l2-ctl --list-devices
```

To load v4l2loopback automatically on boot:
```bash
echo "v4l2loopback" | sudo tee /etc/modules-load.d/v4l2loopback.conf
echo "options v4l2loopback video_nr=10 card_label=\"OBS Virtual Camera\" exclusive_caps=1" | \
    sudo tee /etc/modprobe.d/v4l2loopback.conf
```

---

## Step 3: Install Virtual Audio Device

Zeus TTS audio needs to be routed through a virtual audio device so Zoom/Meet can use it as a microphone input.

### macOS (BlackHole)
```bash
brew install --cask blackhole-2ch
```
After installation:
1. Open Audio MIDI Setup (Applications > Utilities)
2. BlackHole 2ch will appear as an audio device
3. Route TTS audio output to BlackHole
4. In Zoom, select "BlackHole 2ch" as microphone

### Windows (VB-Audio Virtual Cable)
1. Download from https://vb-audio.com/Cable/
2. Install and restart
3. "CABLE Output" appears as a playback device
4. "CABLE Input" appears as a recording device
5. Route TTS audio to "CABLE Output"
6. In Zoom, select "CABLE Input" as microphone

### Linux (PulseAudio)
```bash
# Create a virtual audio sink
pactl load-module module-pipe-sink \
    file=/tmp/zeus-audio-pipe \
    sink_name=zeus_virtual_mic \
    format=s16le \
    rate=22050 \
    channels=1

# Verify it was created
pactl list sinks short | grep zeus
```

### Linux (PipeWire -- recommended for modern distros)
```bash
# Create a virtual audio sink
pw-cli create-node adapter '{
    factory.name=support.null-audio-sink
    node.name=zeus_virtual_mic
    media.class=Audio/Sink/Virtual
    object.linger=true
    audio.position=[FL FR]
}'

# Verify
pw-cli list-objects | grep zeus_virtual_mic
```

To make the virtual sink persistent across reboots (PipeWire):
```bash
mkdir -p ~/.config/pipewire/pipewire.conf.d/
cat > ~/.config/pipewire/pipewire.conf.d/zeus-virtual-mic.conf << 'EOF'
context.objects = [
    { factory = adapter
        args = {
            factory.name = support.null-audio-sink
            node.name = zeus_virtual_mic
            media.class = Audio/Sink/Virtual
            object.linger = true
            audio.position = [ FL FR ]
        }
    }
]
EOF
systemctl --user restart pipewire
```

---

## Step 4: Configure OBS WebSocket

OBS 28+ has obs-websocket built in. Enable and configure it:

1. Open OBS Studio
2. Go to **Tools > obs-websocket Settings**
3. Check **Enable WebSocket server**
4. Set **Server Port**: `4455` (default)
5. Check **Enable Authentication**
6. Set a **Server Password** (use the same value as `OBS_WS_PASSWORD` in your `.env`)
7. Click **Apply**

Note the connection info for your `.env` file:
```bash
OBS_WS_HOST=localhost
OBS_WS_PORT=4455
OBS_WS_PASSWORD=your-password-here
```

---

## Step 5: Import Scene Collection

1. Copy `scene-collection-example.json` or use it as a reference
2. In OBS, go to **Scene Collection > Import**
3. Select the JSON file
4. Three scenes will be created:
   - **ZeusAvatar** -- Full-screen avatar for normal conversation
   - **ScreenShare** -- Screen share with small avatar overlay (bottom-right)
   - **SplitView** -- Side-by-side avatar and screen share

---

## Step 6: Configure Sources

### Window Capture (default method)
1. In the **ZeusAvatar** scene, select the "Zeus UE Window" source
2. In Properties, select the Unreal Engine window
3. Set capture method to "Auto" (or "Windows Graphics Capture" on Windows)

### NDI Source (alternative -- lower latency)
If you have NDI enabled in Unreal Engine:
1. Install the OBS NDI plugin: https://github.com/obs-ndi/obs-ndi
2. Replace the "Zeus UE Window" source with an NDI Source
3. Select the Zeus MetaHuman NDI feed

### Audio Source
1. Select the "Zeus TTS Audio" source
2. In Properties, select the virtual audio device:
   - macOS: "BlackHole 2ch"
   - Windows: "CABLE Output"
   - Linux: "zeus_virtual_mic"

---

## Step 7: Start Virtual Camera

1. In OBS, click **Start Virtual Camera** (or go to Tools > Start Virtual Camera)
2. The virtual camera is now active and available to other applications

---

## Step 8: Configure Zoom / Google Meet / Teams

### Zoom
1. Open Zoom > Settings > Video
2. Select **OBS Virtual Camera** as your camera
3. Go to Settings > Audio
4. Select the virtual audio device as your microphone:
   - macOS: "BlackHole 2ch"
   - Windows: "CABLE Input"
   - Linux: "zeus_virtual_mic"

### Google Meet
1. Click the three dots > Settings > Video
2. Select **OBS Virtual Camera**
3. Go to Audio tab
4. Select the virtual audio device as microphone

### Microsoft Teams
1. Click your profile > Settings > Devices
2. Select **OBS Virtual Camera** as camera
3. Select virtual audio device as microphone

---

## Step 9: Run the OBS Controller

The OBS controller script automates scene switching, audio muting, and recording based on Zeus events.

```bash
# Install Python dependencies
cd obs/
pip install -r requirements.txt

# Set environment variables (or create .env)
export OBS_WS_HOST=localhost
export OBS_WS_PORT=4455
export OBS_WS_PASSWORD=your-password
export REDIS_HOST=localhost
export REDIS_PORT=6379

# Run the controller
python obs-controller.py
```

The controller:
- Automatically mutes Zeus audio on `STOP_TALKING` events
- Unmutes Zeus audio when Zeus starts speaking
- Mutes Zeus audio on barge-in (user interruption)
- Accepts manual commands via the interactive CLI

Type `help` in the controller for available commands.

---

## Troubleshooting

### Virtual camera not appearing in Zoom
- **macOS**: Restart Zoom after starting OBS virtual camera. Some apps need to be restarted to detect new cameras.
- **Windows**: Make sure OBS is running as the same user (not admin) as Zoom.
- **Linux**: Verify v4l2loopback is loaded: `lsmod | grep v4l2loopback`. If not, reload the module.

### Audio not routing through virtual device
- **macOS (BlackHole)**: Open Audio MIDI Setup, verify BlackHole appears. Use "Multi-Output Device" if you need to hear audio locally too.
- **Linux (PulseAudio)**: Use `pavucontrol` to route the TTS application's output to the virtual sink.
- **Linux (PipeWire)**: Use `qpwgraph` to visually connect TTS output to the virtual sink.

### OBS WebSocket connection refused
- Verify obs-websocket is enabled: Tools > obs-websocket Settings > "Enable WebSocket server"
- Check the port matches your configuration (default: 4455)
- Check the password matches
- Firewall: ensure port 4455 is open for localhost connections

### High CPU/GPU usage
- In OBS Settings > Output, use hardware encoding (NVENC) instead of x264
- Reduce canvas resolution to 1280x720 if 1080p is too demanding
- Set OBS to "Simple" output mode with reasonable bitrate (4000-6000 kbps)
- In Unreal Engine, reduce render quality settings

### v4l2loopback issues (Linux)
```bash
# If the module fails to load, rebuild it
sudo apt install linux-headers-$(uname -r)
sudo apt reinstall v4l2loopback-dkms
sudo modprobe v4l2loopback video_nr=10 card_label="OBS Virtual Camera" exclusive_caps=1

# If device permissions are wrong
sudo chmod 666 /dev/video10
```

### OBS crash on startup with virtual camera
- Update OBS to the latest version
- On Linux, try running with `--disable-shutdown-check` flag
- Check system logs: `journalctl -xe | grep obs`

### NDI source not appearing
- Verify the NDI plugin is installed correctly
- Verify Unreal Engine NDI output is enabled and broadcasting
- Both OBS and UE must be on the same network subnet
- Check firewall rules allow NDI traffic (TCP/UDP 5960+)
