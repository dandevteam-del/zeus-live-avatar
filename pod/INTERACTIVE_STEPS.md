# Interactive Steps — the parts only you can do (Daniel)

Everything else is scripted. These need a human + an Epic login. There are two
ways to do the MetaHuman work; pick one.

---
## Step 0 — Epic ↔ GitHub (one-time, ~5 min, no GPU cost)
1. Sign in at https://www.epicgames.com and https://github.com with the same person.
2. Link them: https://www.unrealengine.com/en-US/ue-on-github → "Connect account".
   This grants access to `EpicGames/UnrealEngine` and the `ghcr.io/epicgames/*` images.
3. Make a GitHub PAT with scope **`read:packages`** (Settings→Developer settings→Tokens).
   You'll pass it as `GHCR_PAT` to `01_install_ue5.sh`.

---
## MetaHuman: choose Path A or Path B

### Path B — pre-bake the asset (CHEAPEST, recommended) 🟢
Do the MetaHuman creation on **any machine that can run the UE5.4 editor with a GUI**
(your Mac with UE installed, a Windows PC, etc.) — *not* on the billing pod.

1. Create an **original** suited presenter at https://metahuman.unrealengine.com
   (MetaHuman Creator, browser). White male, slicked hair, business suit — our own
   character, **not** a real person and **not** the copyrighted Agent Smith.
2. In a local UE5.4 project: **Window → Quixel Bridge → My MetaHumans → your char →
   Download → Add**. It lands in `Content/MetaHumans/<Name>/`.
3. Zip `Content/MetaHumans/<Name>/` and send it to the pod:
   ```bash
   rsync -avP MetaHumans-Zeus.zip root@<pod-ip>:/workspace/ZeusMetaHuman/Content/
   # on pod: cd /workspace/ZeusMetaHuman/Content && unzip MetaHumans-Zeus.zip
   ```
4. Then the AnimBP wiring below can be done locally too (save before zipping) — if
   you wire it locally, packaging on the pod is **fully headless**, no GUI pod needed.

### Path A — do it on the pod (if you have no local editor)
Provision the pod from a **Desktop/VNC** RunPod template (or attach noVNC), then run
the UE editor there once:
```bash
docker run --rm --gpus all -e HOME=/home/ue4 -v /workspace:/workspace \
  -p 5900:5900 ghcr.io/epicgames/unreal-engine:dev-slim-5.4 \
  /home/ue4/UnrealEngine/Engine/Binaries/Linux/UnrealEditor /workspace/ZeusMetaHuman/ZeusMetaHuman.uproject
```
Sign into Epic + Quixel Bridge in that GUI session and do the import + wiring below.
(GUI pod-hours are billed — Path B avoids them.)

---
## AnimBP wiring (either path — once)
Open `Content/MetaHumans/<Name>/Face/Face_AnimBP`:
1. AnimGraph → add **Live Link Pose** node.
   - **Subject Name:** `ZeusAvatar`  (must match the plugin exactly)
   - Retarget Asset: None (ARKit blendshapes).
2. Connect Live Link Pose → the facial pose output → Output Pose. Compile + Save.
3. Drag the MetaHuman `BP_<Name>` into the **Avatar** map at origin; add a CineCamera
   (50mm, framed mid-chest up) + 3-point lights (see `../ue/ZeusMetaHuman/SETUP.md`).
4. Level Blueprint **BeginPlay**: construct a `ZeusAnimationSource`, call
   `Connect("ws://localhost:8003/ws_anim")`; **EndPlay** → `Disconnect()`.
5. **Save All.** (If on Path B, this is the moment to zip + upload, or zip the whole
   `Content/` so the pod has map + MetaHuman + wiring and packaging is headless.)

---
## After this
On the pod, in order: `01_install_ue5.sh` → `02_bootstrap_project.sh` →
(import/wire per above) → `03_package_pixelstreaming.sh` → `04_run_stream.sh`.
Open `http://<pod-ip>:<mapped-80>/` to see the avatar; point OBS/Zoom at it.
**Stop the pod when done.**
