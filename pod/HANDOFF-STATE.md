# HANDOFF — Zeus 3D MetaHuman Avatar on RunPod (live build state)

_Last updated: 2026-06-14 ~03:25 UTC. Read this + task #19 to resume._

## Goal
Run the interactive **Unreal Engine 5.6 editor** on a RunPod GPU pod (headless, via
noVNC) so Daniel can create an **original MetaHuman** (`ZeusAgent`), then package it
for **Pixel Streaming** to drive a real-time 3D avatar. (2D SadTalker path is the
quick tier — see bottom.)

## Current pod
- **Pod:** `xewb03wbte8arr` — RTX **A5000**, US-IL-1, ~$0.27/hr. **RUNNING.**
- **Volume:** `wgw61k00bb` (100 GB, US-IL-1) — holds the project + DDC; persists across stop/resume.
- **ghcr auth id:** `cmqcqn2li004v6hy2gf0qgsdb` (Daniel's `read:packages` PAT, in zeus/.env as GHCR_PAT).
- **Image:** `ghcr.io/epicgames/unreal-engine:dev-slim-5.6` (Epic↔GitHub link is ACTIVE).
- **Deploy env (critical):** `NVIDIA_DRIVER_CAPABILITIES=all`, `NVIDIA_VISIBLE_DEVICES=all`.
- **dockerArgs:** `bash -lc 'rm -rf /workspace/kit; git clone --depth 1 https://github.com/dandevteam-del/zeus-live-avatar /workspace/kit && bash /workspace/kit/pod/cloud_init.sh; sleep infinity'`
- **noVNC:** https://xewb03wbte8arr-6080.proxy.runpod.net/vnc.html (autoconnect&resize=remote)
- **Logs over HTTPS:** `/boot.log` and `/ue.log` on that same host (e.g. `.../-6080.proxy.runpod.net/ue.log`).

## How the pod self-bootstraps
`pod/cloud_init.sh` (in repo `dandevteam-del/zeus-live-avatar`) runs at container start:
installs noVNC desktop (Xvfb+x11vnc+websockify+openbox), registers the NVIDIA Vulkan
ICD, creates a **content-only** project `/workspace/ZeusAvatar`, then launches the UE
editor in a relaunch loop. All output → `/workspace/web/{boot,ue}.log` (HTTPS-served).
**To apply any cloud_init change: push to the repo, then stop+resume the pod** (resume
re-clones the kit + re-runs cloud_init). Resume keeps the same host/GPU.

## Walls cleared (do NOT re-debug these — fixes are in cloud_init.sh)
1. **apt aborted** — split into core-desktop (must-succeed) + GPU-extras (best-effort); dropped nonexistent `libasound2t64`.
2. **Module compile crash** — use a **content-only** project (no C++ Source/Modules → nothing to compile).
3. **Vulkan couldn't see GPU** (editor hung at "Vulkan Profile check") — `NVIDIA_DRIVER_CAPABILITIES=all` at deploy + write `/usr/share/vulkan/icd.d/nvidia_icd.json`. ✅ now `Creating Vulkan Device … NVIDIA RTX A5000`.
4. **DDC crash** "no writable nodes" (installed engine wants ZenServer, not running) — DefaultEngine.ini overrides `[InstalledDerivedDataBackendGraph]`+`[DerivedDataBackendGraph]` to a **FileSystem** cache at `/workspace/ddc/Local`.
5. **Driver-warning dialog** blocked startup — Daniel clicked **No** once; permanent fix is `-unattended -nopause` on the launch (now in cloud_init).
6. **OOM kill loop (rc=137)** — UE saw host's 252 GB and spawned **64 shader workers** > container RAM → kernel killed it repeatedly. FIX: `-corelimit=6` + `-ini:Engine:[DevOptions.Shaders]:NumUnusedShaderCompilingThreads=60` on the launch + disabled Lumen/RayTracing/Nanite in DefaultEngine.ini. **Worked → now "Using 1 local workers", no new OOM.**

## ⏳ CURRENT STATE / next action
Editor is **compiling shaders with 1 worker (no OOM, but slow)** — log advancing,
not yet "Engine is initialized". Two options next session:
- **(A) Wait it out** — 1 worker is safe; let it finish (could be slow). Watch
  `/ue.log` for `Engine is initialized` / `Bringing up level` → editor window appears.
- **(B) Tune workers up** (faster, recommended): change `-corelimit=6` →
  `-corelimit=8` and try `NumUnusedShaderCompilingThreads=56` (→ ~8 workers). More
  speed without OOM. Push + stop/resume. If OOM returns, step back down.
  (1 worker is over-conservative; the sweet spot for this pod's RAM is ~4–8.)

**Once the editor window shows in noVNC → DANIEL does (only he can — Epic creds):**
Window → **Fab** (Quixel Bridge) → sign in with Epic → add MetaHuman plugin → create
an ORIGINAL suited presenter → name **`ZeusAgent`** → Add to project.
**Then** (Claude): copy the `ZeusAnimReceiver` plugin from `kit/ue/ZeusMetaHuman/Source`
into the project, wire Face_AnimBP LiveLink subject `ZeusAvatar`, package with Pixel
Streaming (`pod/03_package_pixelstreaming.sh` pattern), run the stream.

## Tooling notes
- **ZDAL works** (Chrome JS bridge ON). Drive Daniel's Chrome via
  `python3.13 -m kg_core.construct.zdal.cli dom js '<js>'` from `~/clawd/kg-runtime`.
  Click remote desktop via `control.click(x,y)` (cliclick) + `screencapture` + Read to verify.
  **Caveat:** Daniel actively uses Chrome — coordinate clicks fight his focus & noVNC
  disconnects often. Prefer fixing dialogs at the source (flags/config) over clicking.
- **SSH to pod is unreliable** (proxy flaky; no sshd in image). Use the HTTPS logs +
  stop/resume to apply changes. Don't rely on `ssh ...@ssh.runpod.io`.
- **Deploy/redeploy helper:** `/tmp/mut.json` builder pattern (terminate + podFindAndDeployOnDemand
  across GPU types; volume locked to US-IL-1 so retry across GPUs on SUPPLY_CONSTRAINT).
- **Cost so far** ~$7–8. Pod ~$0.27/hr. **Stop the pod when idle** — volume persists.

## Parallel: 2D SadTalker avatar (quick tier — separate, near-done)
- Endpoint `ulu3rlugwxvqw3` (serverless, scale-to-zero, $0 idle). Image BUILT.
- Worker repo `dandevteam-del/zeus-sadtalker-worker`. Client `video-studio/worker/modules/sadtalker_runpod.py` + `build_agent_demo_sadtalker.py`.
- Reusable character: `outputs/avatars/agent-prime/reference.png` (SDXL, original suited agent). Voice: ElevenLabs `jltZKOiJycU5UUMisQ7N`.
- **Remaining 2D bug:** SadTalker runtime crash at "3DMM Extraction for source image" (face-detect/preprocess). Fix not yet applied. Run via the worker venv: `video-studio/worker/.venv/bin/python build_agent_demo_sadtalker.py "<script>"`.
- 2D LatentSync demo already shipped earlier (`outputs/AGENT-DEMO.mp4`) but lip-sync was poor (still-image limitation) — SadTalker is the replacement.

## Key IDs cheat-sheet
- Pod: `xewb03wbte8arr` · Volume: `wgw61k00bb` · ghcr auth: `cmqcqn2li004v6hy2gf0qgsdb`
- Kit repo: `github.com/dandevteam-del/zeus-live-avatar` (cloud_init.sh = brain)
- RUNPOD_API_KEY in `~/clawd/zeus/.env` (parse: `grep '^RUNPOD_API_KEY=' .env | cut -d= -f2-`)
- IP rule: avatar must be ORIGINAL synthetic (not Hugo Weaving / copyrighted Agent Smith).
