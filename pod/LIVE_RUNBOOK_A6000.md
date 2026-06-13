# Bring the Zeus MetaHuman Avatar LIVE — A6000, best quality (full runbook)

Two columns of work: **YOU** = browser/GUI (your Epic login, MetaHuman, viewing).
**CLAUDE** = pod terminal over SSH (provision, install, package, stream). The split
exists because UE-on-cloud needs live iteration — you do the human parts, I drive the rest.

GPU: **RTX A6000 48 GB** (build + live). Region: **US-IL-1** (where the volume lives).
Cost: one-time build ~$3–4 + ~$6/mo volume; live ~$0.79/hr — **stop the pod when idle.**

─────────────────────────────────────────────────────────────────────────────
## PHASE 0 — Accounts (YOU, browser, ~20 min)  ⟵ do these first
─────────────────────────────────────────────────────────────────────────────
**0A. Epic account + link GitHub** (unlocks the UE5.4 engine image)
   1. https://www.epicgames.com/account/connections  → sign in (make a free Epic acct if needed)
   2. **Apps/Connections** tab → **GitHub** → **Connect** → authorize as `dandevteam-del`
   3. Accept the org invite: open the GitHub email *"join @EpicGames"*, or go to
      https://github.com/EpicGames and click the join banner.
   ✅ Done when https://github.com/EpicGames/UnrealEngine loads (not 404).

**0B. GitHub token** (lets the pod pull the engine image)
   1. https://github.com/settings/tokens  → **Generate new token (classic)**
   2. Name `runpod-ue`, expiry 90d, check **`read:packages`**
   3. Generate → copy the `ghp_…` → **paste it to Claude.**  ← unblocks everything

**0C. Create the MetaHuman** (your avatar; free, browser)
   1. https://metahuman.unrealengine.com  → **Start MetaHuman Creator** (Epic login)
   2. Build an ORIGINAL suited presenter matching the 2D face (white male ~40s, slicked
      dark hair, serious). Not a real celebrity.
   3. Name it **`ZeusAgent`** → it auto-saves to **My MetaHumans**.
   ✅ Done when `ZeusAgent` shows in your MetaHumans list.

─────────────────────────────────────────────────────────────────────────────
## PHASE 1 — Provision the A6000 pod (CLAUDE via API, once 0B is done)
─────────────────────────────────────────────────────────────────────────────
I register your `ghp_…` as a RunPod container-registry credential, then deploy:
   • Pod image = `ghcr.io/epicgames/unreal-engine:dev-slim-5.4` (UE already inside — no docker-in-docker)
   • GPU RTX A6000 48 GB · 120 GB container disk · 100 GB network volume @ /workspace
   • Ports: 6080 (noVNC), 5900 (VNC), 80 (signaling), 8888 (WebRTC), 8000/8001/8003 (services)
I send you back: the pod's **noVNC URL** and the **pixel-stream URL**.

(Manual alternative if you'd rather click: console.runpod.io/pods → Deploy → A6000 →
 set the image + ports above + attach the volume. But let me do it — the registry-auth
 + ports are easy to get wrong.)

─────────────────────────────────────────────────────────────────────────────
## PHASE 2 — Install + bootstrap (CLAUDE via SSH, ~30–60 min, A6000 billing on)
─────────────────────────────────────────────────────────────────────────────
On the pod I run:
   git clone https://github.com/dandevteam-del/zeus-live-avatar /workspace/kit
   cd /workspace/kit/pod
   bash 01_install_ue5.sh          # confirms UE in the image / pulls if needed
   bash 02_bootstrap_project.sh    # generates ZeusMetaHuman.uproject + plugin + map
   bash 05_desktop_session.sh      # starts noVNC + opens the UE editor
→ I hand you the **noVNC URL**.

─────────────────────────────────────────────────────────────────────────────
## PHASE 3 — Import the MetaHuman (YOU, in the noVNC browser tab, ~30 min)
─────────────────────────────────────────────────────────────────────────────
Open the noVNC URL I send → you're looking at the UE5 editor on the pod. Then:
   1. **Window → Quixel Bridge** → sign into Epic → **My MetaHumans** → **ZeusAgent** →
      **Download** → **Add** (imports to Content/MetaHumans/ZeusAgent — a few GB).
   2. Open `Content/MetaHumans/ZeusAgent/Face/Face_AnimBP` → AnimGraph → add **Live Link Pose**
      node → Subject **`ZeusAvatar`** → connect to the face pose → Compile + Save.
   3. Drag `BP_ZeusAgent` into the **Avatar** map at origin. Add a CineCamera (50mm, chest-up)
      + 3-point lights (the kit's `ue/ZeusMetaHuman/SETUP.md` has exact values).
   4. Level Blueprint → BeginPlay: `ZeusAnimationSource` → `Connect("ws://localhost:8003/ws_anim")`.
   5. **Save All**, close the editor. (I'm guiding you live through each click.)

─────────────────────────────────────────────────────────────────────────────
## PHASE 4 — Package + GO LIVE (CLAUDE via SSH, package ~1–2 h on A6000)
─────────────────────────────────────────────────────────────────────────────
   bash 03_package_pixelstreaming.sh   # cooks the headless Linux pixel-streaming build
   bash 04_run_stream.sh               # signaling + headless render + STT/TTS/gateway/a2f
→ I send you the **pixel-stream URL**:  `http://<pod-ip>:<mapped-80>/`

**YOU:** open that URL → you'll see ZeusAgent rendered live and lip-syncing to the voice.
To use on calls: capture that window in **OBS** → **Start Virtual Camera** → in
Zoom/Teams/Meet pick "OBS Virtual Camera" as your webcam.

─────────────────────────────────────────────────────────────────────────────
## PHASE 5 — STOP THE POD (YOU or CLAUDE — do it every time you finish)
─────────────────────────────────────────────────────────────────────────────
console.runpod.io/pods → your pod → **Stop**.  Volume persists (~$6/mo) so next time
we skip straight to Phase 4. Leaving it running 24/7 ≈ $569/mo — don't.

## Links, all in one place
- Epic connections:           https://www.epicgames.com/account/connections
- UE-on-GitHub access:        https://www.unrealengine.com/en-US/ue-on-github
- GitHub token:               https://github.com/settings/tokens
- EpicGames org (accept):     https://github.com/EpicGames
- MetaHuman Creator:          https://metahuman.unrealengine.com
- RunPod pods:                https://console.runpod.io/pods
- RunPod storage (volumes):   https://console.runpod.io/user/storage
- The kit:                    https://github.com/dandevteam-del/zeus-live-avatar
